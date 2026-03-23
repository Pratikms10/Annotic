"""
annotic_automator.py — Full Pipeline Automation

Flow:
  1. Open browser → navigate to Annotic task page
  2. Download the audio file
  3. Delete ALL existing segments (they belong to someone else)
  4. Run 4-stage Whisper-first pipeline:
     LISTEN → CHUNK → CLASSIFY → FORMAT
  5. Create new segments with correct timestamps
  6. Fill text into each segment
  7. Click Update → verify save
"""

import asyncio
from playwright.async_api import async_playwright
import config
from audio_processor import AudioProcessor
import os
import urllib.request


async def automate_annotic():
    print("=" * 60)
    print("  ANNOTIC AUTOMATOR — Whisper-First Pipeline")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            config.PLAYWRIGHT_SESSION_DIR,
            headless=config.HEADLESS_MODE,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Handle any native window.confirm or window.alert dialogs automatically
        async def handle_dialog(dialog):
            print(f"\n[UI] Auto-accepting native dialog: {dialog.message}")
            await dialog.accept()
        page.on("dialog", handle_dialog)

        # Navigate
        print(f"\n[NAV] Opening {config.ANNOTIC_TASK_URL}")
        await page.goto(config.ANNOTIC_TASK_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        print("[NAV] Task page loaded.")

        # ==============================================================
        # STEP 1: Download Audio
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 1: Download Audio")
        print("=" * 60)

        audio_src = await page.locator("audio#audio-panel").get_attribute("src")
        print(f"[DOWNLOAD] Source: {audio_src}")

        try:
            urllib.request.urlretrieve(audio_src, config.AUDIO_FILE)
            print(f"[DOWNLOAD] Saved: {config.AUDIO_FILE}")
        except Exception as e:
            print(f"[ERROR] Download failed: {e}")
            await browser.close()
            return

        # ==============================================================
        # STEP 2: Run Whisper-First 4-Stage Pipeline
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 2: Whisper-First Pipeline")
        print("=" * 60)

        ap = AudioProcessor(config.WHISPER_MODEL_SIZE)

        chunks, detected_lang = ap.run_pipeline(
            config.AUDIO_FILE,
            language=config.WHISPER_LANGUAGE,
            silence_threshold_s=config.SILENCE_THRESHOLD_S,
        )

        # Filter only chunks that have text to fill
        fill_chunks = [c for c in chunks if c.get("text_final", "").strip()]
        print(f"\n[PIPELINE] {len(fill_chunks)} chunks to create as segments.")

        for i, c in enumerate(fill_chunks[:15]):
            start_str = ap.format_time(c["start"])
            end_str = ap.format_time(c["end"])
            print(f"  {i+1}. [{start_str} - {end_str}] "
                  f"{c['event']:>12s} → \"{c['text_final']}\" "
                  f"(conf={c.get('confidence', 0):.2f})")
        if len(fill_chunks) > 15:
            print(f"  ... and {len(fill_chunks)-15} more.")

        # ==============================================================
        # STEP 3: Delete ALL Existing Segments
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 3: Delete All Existing Segments")
        print("=" * 60)

        await delete_all_segments(page)

        # ==============================================================
        # STEP 4: Create New Segments & Fill
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 4: Create Segments & Fill Text")
        print("=" * 60)

        container = page.locator('#subTitleContainer')

        # To spawn segments cleanly natively as the user requested, we perform
        # physical Playwright click-and-drags on the audio canvas timeline!
        audio_elem = page.locator('audio').first
        audio_dur = 100.0
        if await audio_elem.count() > 0:
            audio_dur = await page.evaluate("() => { const a = document.querySelector('audio'); return (a && a.duration) ? a.duration : 100.0; }")
            
        waveform = page.locator('canvas, #waveform, .waveform, #wave-timeline').last
        box = None
        if await waveform.count() > 0:
            box = await waveform.bounding_box()

        if not box:
            print("  [WARN] Cannot find timeline canvas! Physical mouse drag to spawn segments won't work.")
            
        initial_count = await container.locator('> div').count()
        # If user deleted everything, current rows in DOM is 0

        for i, chunk in enumerate(fill_chunks):
            start_sec = 0.0 if i == 0 else chunk["start"]
            end_sec   = chunk["end"]
            text      = chunk["text_final"]

            print(f"\n  Creating segment {i+1}/{len(fill_chunks)}: "
                  f"[{ap.format_time(start_sec)} - {ap.format_time(end_sec)}] "
                  f"→ \"{text}\"")

            # 1. Spawn the segment row natively using the correct buttons
            success = await click_add_segment(page, is_first=(i == 0 and initial_count == 0))
            if not success:
                print(f"  [ERROR] Failed to spawn segment {i+1}. Stopping.")
                break
                
            # Wait a tiny bit for the UI to settle
            await page.wait_for_timeout(300)

            # 2. Instantly mathematically tune the exact Whisper boundaries
            await set_segment_timestamps(page, container, initial_count + i, start_sec, end_sec)

            # 3. Fill the textarea
            await fill_segment_text(page, container, initial_count + i, text)

        # ==============================================================
        # STEP 5: Save (Click Update)
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 5: Save & Verify")
        print("=" * 60)

        await save_and_verify(page)

        # ==============================================================
        # DONE
        # ==============================================================
        print("\n" + "=" * 60)
        print(f"  COMPLETE: Created {len(fill_chunks)} segments")
        print(f"  Language: {detected_lang}")
        print("=" * 60)

        print("\nBrowser open for 30s review...")
        await page.wait_for_timeout(30000)
        await browser.close()


# ======================================================================
# DOM INTERACTION HELPERS
# ======================================================================

async def delete_all_segments(page):
    """
    Delete ALL existing segments using Playwright native clicks.
    
    KEY FIX: Previous versions used JS element.click() which does NOT
    trigger React's synthetic event handlers. Playwright's .click()
    simulates a real mouse click, which works.
    """
    # Count segments
    seg_count = await _count_segments(page)
    print(f"[DELETE] Found {seg_count} existing segment(s).", flush=True)
    
    if seg_count <= 0:
        return

    # First, dump the button structure for debugging
    await _dump_row_buttons(page)

    if seg_count == 1:
        # Cannot delete the only remaining segment, so we just wipe its text
        print("[DELETE] Only 1 segment. Clearing text...")
        await _clear_segment_textarea(page, 0)
        print(f"[DELETE] Done. 1 clean segment remaining.")
        return

    # Multiple segments: delete from last to first
    deleted = 0
    # Process deletions quicker since dialogs are auto-acked
    while True:
        current = await _count_segments(page)
        if current <= 1:
            break
        
        success = await _delete_last_segment_native(page)
        if success:
            deleted += 1
            if deleted % 20 == 0:
                print(f"[DELETE] {deleted} deleted...", flush=True)
            await page.wait_for_timeout(10)  # Minimal wait
        else:
            print(f"[DELETE] Failed to delete at count={current}. Stopping.")
            break

    await _clear_segment_textarea(page, 0)
    print(f"[DELETE] Done! Deleted {deleted}. {await _count_segments(page)} clean segment remaining.")


async def _count_segments(page):
    """Count segment rows in the container."""
    return await page.evaluate("""
    () => {
        const c = document.getElementById('subTitleContainer');
        return c ? Array.from(c.children).filter(r => r.querySelector('textarea')).length : 0;
    }
    """)


async def _dump_row_buttons(page):
    """Print all buttons on the first row for debugging."""
    info = await page.evaluate("""
    () => {
        const c = document.getElementById('subTitleContainer');
        if (!c) return [];
        const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
        if (rows.length === 0) return [];
        const row = rows[0];
        const btns = row.querySelectorAll('button');
        return Array.from(btns).map((btn, i) => ({
            i: i,
            text: btn.textContent.trim().substring(0, 20),
            cls: (btn.className || '').substring(0, 80),
            html: btn.outerHTML.substring(0, 120),
        }));
    }
    """)
    if info:
        print(f"[DEBUG] Buttons on row 0: {len(info)}")
        for b in info:
            print(f"  btn[{b['i']}] text='{b['text']}' html={b['html'][:100]}")


async def _delete_last_segment_native(page):
    """
    Delete the LAST segment row using Playwright native clicks.
    
    Strategy based on UI screenshot:
    1. Find the delete button (trash can) on the last row and mark it.
    2. Click the delete button.
    (No need to click + first, as the trash button is already visible!)
    """
    found_delete = await page.evaluate("""
    () => {
        const c = document.getElementById('subTitleContainer');
        if (!c) return false;
        
        // Find all semantic segment rows
        const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
        if (rows.length <= 1) return false; // Don't delete the only remaining segment!
        
        const lastRow = rows[rows.length - 1];
        const buttons = lastRow.querySelectorAll('button');
        
        for (const btn of buttons) {
            const svg = btn.querySelector('svg');
            
            // Look for standard DeleteIcon
            if (svg && svg.getAttribute('data-testid') === 'DeleteIcon') {
                btn.setAttribute('data-temp-delete', 'true');
                return true;
            }
            // Another common tell for delete is an SVG with the trash can path:
            if (svg && btn.innerHTML.includes('M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z')) {
                btn.setAttribute('data-temp-delete', 'true');
                return true;
            }
        }
        
        // If we still can't find it, look for red colored buttons (like the trash icon)
        for (const btn of buttons) {
            const style = window.getComputedStyle(btn);
            if (style.color.includes('rgb(211, 47') || style.color.includes('red') || style.color.includes('d32f2f')) {
                btn.setAttribute('data-temp-delete', 'true');
                return true;
            }
        }
        
        // Let's identify the one that is NOT + and NOT - based on SVG paths/testIds
        // The buttons are almost always [-, arrow?, trash, +] 
        let actionBtns = [];
        for (const btn of buttons) {
             const svg = btn.querySelector('svg');
             if (!svg) continue;
             const testId = svg.getAttribute('data-testid') || '';
             
             // Ignore specific dropdown/menu buttons
             if (btn.textContent.trim().includes('Speaker')) continue;
             
             actionBtns.push(btn);
        }
        
        // We know the trash icon is usually the second to last button or the one before the + button
        for (const btn of actionBtns) {
            const svg = btn.querySelector('svg');
            if (!svg) continue;
            const testId = svg.getAttribute('data-testid') || '';
            
            if (testId !== 'AddIcon' && testId !== 'RemoveIcon' && btn.textContent.trim() === '') {
                btn.setAttribute('data-temp-delete', 'true');
                return true;
            }
        }
        
        return false;
    }
    """)
    
    if found_delete:
        try:
            target = page.locator('[data-temp-delete="true"]')
            if await target.count() > 0:
                await target.first.click()
                await page.wait_for_timeout(100) # Wait for React to process deletion
                # Cleanup marker if it didn't get removed from DOM
                await page.evaluate("() => { const e = document.querySelector('[data-temp-delete]'); if (e) e.removeAttribute('data-temp-delete'); }")
                return True
        except Exception as e:
            print(f"[DELETE] Click error: {e}")
            
    return False


async def _clear_segment_textarea(page, row_index):
    """Clear the textarea content of a specific segment row."""
    await page.evaluate("""
    (idx) => {
        const c = document.getElementById('subTitleContainer');
        if (!c) return;
        const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
        if (!rows[idx]) return;
        const ta = rows[idx].querySelector('textarea');
        if (!ta) return;
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value'
        ).set;
        setter.call(ta, '');
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
    }
    """, row_index)


async def click_add_segment(page, is_first=False):
    """
    Spawns a new segment row using the exact configuration a human uses:
    - 1st segment: slides/drags on the audio timeline.
    - Subsequent: clicks '+' button on the last segment row.
    """
    try:
        container = page.locator('#subTitleContainer')
        initial_count = await container.locator('> div').count()
        
        if is_first or initial_count == 0:
            print("  [INFO] First segment: simulating human-speed mouse drag on bottom waveform...")
            
            # ── Find the BOTTOM-MOST canvas (the actual waveform at the bottom of the page) ──
            canvases = page.locator('canvas')
            num_canvases = await canvases.count()
            if num_canvases == 0:
                print("  [ERROR] Could not find any canvas elements!")
                return False
            
            # Collect all canvas bounding boxes and pick the one closest to the bottom
            canvas_boxes = []
            for idx in range(num_canvases):
                c = canvases.nth(idx)
                b = await c.bounding_box()
                if b and b['width'] > 50 and b['height'] > 10:
                    canvas_boxes.append((idx, b))
                    print(f"    [SCAN] Canvas {idx}: x={b['x']:.0f} y={b['y']:.0f} w={b['width']:.0f} h={b['height']:.0f}")
            
            if not canvas_boxes:
                print("  [ERROR] No usable canvas found!")
                return False
            
            # Sort by Y position descending — bottom-most first
            canvas_boxes.sort(key=lambda item: item[1]['y'], reverse=True)
            
            success = False
            for idx, box in canvas_boxes:
                print(f"    [TARGET] Using canvas {idx} at Y={box['y']:.0f} (bottom-most)")
                
                # Drag from ~5% to ~30% of the canvas width (partial drag like the green rectangle in screenshot)
                start_x = box['x'] + (box['width'] * 0.05)
                end_x   = box['x'] + (box['width'] * 0.30)
                
                drag_distance = end_x - start_x
                
                # Drag at the vertical CENTER of this canvas
                y = box['y'] + (box['height'] * 0.5)
                
                print(f"    -> Human-speed drag at Y={y:.1f} from X={start_x:.0f} to X={end_x:.0f}...")
                
                # ── HUMAN-LIKE DRAG: slow, stepped, realistic ──
                
                # 1. Move to starting position (hovering)
                await page.mouse.move(start_x, y)
                await page.wait_for_timeout(300)
                
                # 2. Press mouse down and hold briefly
                await page.mouse.down()
                await page.wait_for_timeout(200)
                
                # 3. Drag slowly in small increments
                num_steps = 50
                step_size = drag_distance / num_steps
                current_x = start_x
                
                for step in range(num_steps):
                    current_x += step_size
                    await page.mouse.move(current_x, y)
                    await page.wait_for_timeout(30)
                
                # 4. Pause at end position
                await page.wait_for_timeout(300)
                
                # 5. Release mouse
                await page.mouse.up()
                
                # 6. Wait for UI to react
                await page.wait_for_timeout(1500)
                
                if await container.locator('> div').count() > initial_count:
                    print(f"  [SUCCESS] Created segment by dragging on bottom waveform canvas {idx}!")
                    success = True
                    break
                else:
                    print(f"    [INFO] No segment appeared on canvas {idx}, trying next...")
            
            if not success:
                print("  [ERROR] Dragged on all canvases but no segment appeared!")
                return False
                
        else:
            # Click '+' button on the LAST row
            clicked_plus = await page.evaluate("""() => {
                const c = document.getElementById('subTitleContainer');
                if (!c || c.children.length === 0) return false;
                
                // Get strictly the rows that contain textareas
                const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
                if (rows.length === 0) return false;
                
                const lastRow = rows[rows.length - 1];
                const btns = Array.from(lastRow.querySelectorAll('button'));
                
                // Look for AddIcon path
                const plusBtn = btns.find(b => {
                    const svg = b.querySelector('svg path');
                    return svg && svg.getAttribute('d') && svg.getAttribute('d').includes('M19 13h-6');
                });
                
                if (plusBtn) { plusBtn.click(); return true; }
                
                // Fallback: usually the 2nd to last button
                if (btns.length >= 2) {
                    btns[btns.length - 2].click();
                    return true;
                }
                return false;
            }""")
            
            if not clicked_plus:
                print("  [ERROR] Could not find '+' button on the last segment row!")
                return False
        
        # Wait for the new row to actually spawn
        for _ in range(30):
            await page.wait_for_timeout(100)
            if await container.locator('> div').count() > initial_count:
                return True
                
        print("  [ERROR] UI did not add a segment row after interaction!")
        return False
        
    except Exception as e:
        print(f"  [ERROR] Exception in click_add_segment: {e}")
        return False


async def set_segment_timestamps(page, container, seg_index, start_seconds, end_seconds):
    """
    Set the start and end timestamps using Playwright native locators and pure native keystrokes.
    Pressing 'Enter' mechanically is critical to force Annotic's React state to stretch the purple
    timeline block to the newly matched values.
    """
    try:
        # Prevent React from silently rejecting out-of-bounds Whisper segment end times!
        audio_dur = await page.evaluate("() => { const a = document.querySelector('audio'); return (a && a.duration > 0) ? a.duration : 100.0; }")
        if end_seconds >= audio_dur:
            end_seconds = audio_dur - 0.001
            
        def format_ts(sec):
            hh = int(sec // 3600)
            mm = int((sec % 3600) // 60)
            ss = int(sec % 60)
            ms = int(round((sec - int(sec)) * 1000))
            return f"{hh:02d}", f"{mm:02d}", f"{ss:02d}", f"{ms:03d}"
            
        sh, sm, ss, sms = format_ts(start_seconds)
        eh, em, es, ems = format_ts(end_seconds)

        row = container.locator(f'> div:nth-child({seg_index + 1})')
        # According to the HTML dump, the 8 actual timestamp boxes use type="number"
        inputs = row.locator('input[type="number"]')

        count = await inputs.count()
        if count != 8:
            print(f"  [WARN] Expected 8 number inputs for segment {seg_index}, got {count}")
            return
            
        ts_map = {
            0: sh, 1: sm, 2: ss, 3: sms,
            4: eh, 5: em, 6: es, 7: ems,
        }
        
        for idx, val in ts_map.items():
            field = inputs.nth(idx)
            # Mechanical Human Emulation typing heavily pierces internal React synthetic states
            await field.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(str(val), delay=50) # Slower typing creates undeniable synthetic updates
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(100) # Give React time to stretch the 1D UI block timeline
            
    except Exception as e:
        print(f"  [ERROR] Failed to set timestamps purely in Playwright: {e}")


async def fill_segment_text(page, container, seg_index, text):
    """Fill the textarea of a specific segment with text."""
    fill_script = """
    (args) => {
        const container = document.getElementById('subTitleContainer');
        if (!container) return false;
        const rows = Array.from(container.children).filter(
            row => row.querySelector('textarea')
        );
        const row = rows[args.segIndex];
        if (!row) return false;
        
        const textarea = row.querySelector('textarea');
        if (!textarea) return false;
        
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value'
        ).set;
        setter.call(textarea, args.text);
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }
    """
    result = await page.evaluate(fill_script, {
        "segIndex": seg_index,
        "text": text,
    })
    if not result:
        print(f"  [WARN] Could not fill text for segment {seg_index}")


async def save_and_verify(page):
    """Click the Update/Save button and verify."""
    print("[SAVE] Clicking Update...", flush=True)
    
    update_opts = [
        page.get_by_role("button", name="Update"),
        page.get_by_role("button", name="Save"),
        page.locator('button:has-text("Update")'),
        page.locator('button:has-text("Submit")'),
        page.locator('text="Update"').locator('visible=true').last
    ]
    
    clicked = False
    for opt in update_opts:
        try:
            if await opt.count() > 0:
                await opt.first.click()
                clicked = True
                break
        except Exception:
            pass
            
    if clicked:
        await page.wait_for_timeout(2000)
        # Check for success message
        success = page.locator('text="success", text="saved", text="updated", .MuiAlert-standardSuccess')
        if await success.count() > 0:
            print("[SAVE] ✓ Saved successfully!")
        else:
            print("[SAVE] Clicked Update. Check manually for confirmation.")
    else:
        # Try the save icon button
        save_icon = page.locator('svg[data-testid="SaveIcon"]')
        if await save_icon.count() > 0:
            await save_icon.first.locator('..').click()
            await page.wait_for_timeout(2000)
            print("[SAVE] Clicked save icon.")
        else:
            print("[SAVE] No Update/Save button found!")


if __name__ == "__main__":
    asyncio.run(automate_annotic())
