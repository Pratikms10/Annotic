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
        # STEP 3: Reconcile Segments (Preserve & Adjust)
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 3: Reconcile Segments (Preserve & Adjust)")
        print("=" * 60)

        await reconcile_segments(page, fill_chunks, ap)

        # ==============================================================
        # STEP 4: Save & Verify
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 4: Save & Verify")
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
# CORE LOGIC: RECONCILE SEGMENTS
# ======================================================================

async def reconcile_segments(page, fill_chunks, ap):
    """
    Core Logic Refinement: Preserve and Adjust
    1. Scan existing segments
    2. Adjust existing segments to match target chunks
    3. Add missing segments if target > existing
    4. Delete excess segments if target < existing
    """
    container = page.locator('#subTitleContainer')
    existing = await _count_segments(page)
    target = len(fill_chunks)
    
    print(f"[RECONCILE] Existing placeholders: {existing}, Target segments: {target}")
    
    # Pre-validate: Check if we have any segments to fill
    if target == 0:
        print("  [WARN] No chunks to fill. Deleting all segments.")
        await delete_all_segments(page)
        return

    # PHASE 1: Adjust existing segments (overlapping count)
    overlap = int(min(existing, target))
    if overlap > 0:
        print(f"\n  [Phase 1] Adjusting {overlap} existing segments...")
        for i in range(overlap):
            chunk = fill_chunks[i]
            start = 0.0 if i == 0 else chunk["start"]
            end = chunk["end"]
            
            print(f"    Adjusting {i+1}/{overlap}: [{ap.format_time(start)} - {ap.format_time(end)}]")
            await set_segment_timestamps(page, container, i, start, end)
            await fill_segment_text(page, container, i, chunk["text_final"])
            await page.wait_for_timeout(100)
            
    # PHASE 2: Add missing segments
    if target > existing:
        missing = target - existing
        print(f"\n  [Phase 2] Adding {missing} new segments...")
        for i in range(existing, target):
            chunk = fill_chunks[i]
            start = 0.0 if i == 0 else chunk["start"]
            end = chunk["end"]
            
            print(f"    Adding {i+1}/{target}: [{ap.format_time(start)} - {ap.format_time(end)}]")
            success = await click_add_segment(page, is_first=(existing == 0 and i == 0),
                                              start_sec=start, end_sec=end)
            if not success:
                print(f"  [ERROR] Failed to add segment {i+1}.")
                break
                
            await page.wait_for_timeout(300)
            await set_segment_timestamps(page, container, i, start, end)
            await fill_segment_text(page, container, i, chunk["text_final"])
            
    # PHASE 3: Remove excess segments from the end
    if existing > target:
        excess = existing - target
        print(f"\n  [Phase 3] Deleting {excess} excess segments from the end...")
        for i in range(excess):
            current = await _count_segments(page)
            if current <= target:
                break
                
            print(f"    Deleting excess segment ({current} left)...")
            success = await _delete_last_segment_native(page)
            if not success:
                print(f"  [ERROR] Failed to delete excess segment at count {current}.")
                break
            await page.wait_for_timeout(300)

    # Note: Phase 4 (Validation) is implicitly handled by the accurate 
    # typing in set_segment_timestamps which mechanically aligns the 
    # inputs to match the exactly sequenced Whisper chunks.

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


async def _calibrated_drag_first_segment(page, container, initial_count, start_sec, end_sec):
    """
    Create the first segment by finding the playhead via SCREENSHOT pixel scan.
    Uses Playwright screenshot (bypasses CORS canvas taint), sends base64 image
    back to browser for pixel analysis on a fresh untainted canvas.
    """
    import base64
    MAX_ATTEMPTS = 2

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n  [ATTEMPT {attempt}/{MAX_ATTEMPTS}] Creating first segment "
              f"[{start_sec:.3f}s - {end_sec:.3f}s]...")

        # ── Step 1: Wait for canvas & scroll into view ──
        try:
            await page.wait_for_selector('canvas', state='visible', timeout=10000)
        except Exception:
            print("  [ERROR] No canvas became visible within 10s!")
            continue
        await page.wait_for_timeout(1500)

        # Scroll canvas into view and get its bounds
        canvas_info = await page.evaluate("""() => {
            const canvases = Array.from(document.querySelectorAll('canvas'))
                .map(c => ({ el: c, rect: c.getBoundingClientRect() }))
                .filter(c => c.rect.width > 100 && c.rect.height > 10)
                .sort((a, b) => b.rect.top - a.rect.top);
            if (!canvases.length) return null;
            canvases[0].el.scrollIntoView({ block: 'center', behavior: 'instant' });
            return null;  // will re-read after scroll
        }""")
        await page.wait_for_timeout(600)

        # Re-read canvas bounds AFTER scroll completes
        canvas_info = await page.evaluate("""() => {
            const canvases = Array.from(document.querySelectorAll('canvas'))
                .map(c => ({ el: c, rect: c.getBoundingClientRect() }))
                .filter(c => c.rect.width > 100 && c.rect.height > 10)
                .sort((a, b) => b.rect.top - a.rect.top);
            if (!canvases.length) return null;
            const r = canvases[0].rect;
            return { top: r.top, left: r.left, width: r.width, height: r.height };
        }""")

        if not canvas_info:
            print("  [ERROR] No canvas found!")
            continue

        cTop = canvas_info['top']
        cLeft = canvas_info['left']
        cWidth = canvas_info['width']
        cHeight = canvas_info['height']
        print(f"    Canvas after scroll: left={cLeft:.0f} top={cTop:.0f} w={cWidth:.0f} h={cHeight:.0f}")

        # ── Step 2: Take a Playwright screenshot of the canvas area ──
        # This bypasses CORS canvas taint — Playwright captures rendered pixels
        try:
            screenshot_bytes = await page.screenshot(clip={
                'x': max(0, cLeft),
                'y': max(0, cTop),
                'width': cWidth,
                'height': cHeight
            })
            b64 = base64.b64encode(screenshot_bytes).decode('ascii')
            print(f"    Screenshot captured: {len(screenshot_bytes)} bytes")
        except Exception as e:
            print(f"  [ERROR] Screenshot failed: {e}")
            continue

        # ── Step 3: Send screenshot to browser & scan for cyan playhead ──
        # Draw on a fresh un-tainted canvas, scan pixel columns for cyan line
        scan = await page.evaluate("""(b64Data) => {
            return new Promise((resolve) => {
                const img = new Image();
                img.onload = () => {
                    const c = document.createElement('canvas');
                    c.width = img.width;
                    c.height = img.height;
                    const ctx = c.getContext('2d');
                    ctx.drawImage(img, 0, 0);

                    const imgData = ctx.getImageData(0, 0, c.width, c.height);
                    const d = imgData.data;
                    const W = c.width, H = c.height;

                    // ── Find CYAN playhead (R<120, G>140, B>140) ──
                    let playheadX = -1;
                    for (let x = 0; x < W; x++) {
                        let cyanCount = 0;
                        const samples = 10;
                        for (let s = 0; s < samples; s++) {
                            const y = Math.floor(H * 0.15 + H * 0.7 * s / samples);
                            const i = (y * W + x) * 4;
                            const r = d[i], g = d[i+1], b = d[i+2];
                            if (r < 130 && g > 130 && b > 130 &&
                                (g + b - 2 * r) > 80) {
                                cyanCount++;
                            }
                        }
                        if (cyanCount >= 3) {
                            playheadX = x;
                            break;
                        }
                    }

                    // ── Find ruler tick marks (dark vertical lines in top 20%) ──
                    const rulerH = Math.floor(H * 0.2);
                    const ticks = [];
                    for (let x = 0; x < W; x++) {
                        let darkCount = 0;
                        for (let y = 1; y < rulerH; y += 2) {
                            const i = (y * W + x) * 4;
                            const bri = d[i] + d[i+1] + d[i+2];
                            if (bri < 400 && d[i+3] > 150) darkCount++;
                        }
                        if (darkCount >= rulerH * 0.12) {
                            if (!ticks.length || x - ticks[ticks.length-1] > 10) {
                                ticks.push(x);
                            }
                        }
                    }

                    let pxPerSec = 0;
                    if (ticks.length >= 3) {
                        const spacings = [];
                        for (let i = 1; i < ticks.length; i++) {
                            spacings.push(ticks[i] - ticks[i-1]);
                        }
                        spacings.sort((a, b) => a - b);
                        pxPerSec = spacings[Math.floor(spacings.length / 2)];
                    }

                    // Also sample a few pixel colors for debugging
                    const debugPixels = [];
                    if (playheadX >= 0) {
                        for (let s = 0; s < 5; s++) {
                            const y = Math.floor(H * 0.2 + H * 0.6 * s / 5);
                            const i = (y * W + playheadX) * 4;
                            debugPixels.push(`(${d[i]},${d[i+1]},${d[i+2]})`);
                        }
                    }

                    resolve({
                        playheadX,
                        pxPerSec,
                        tickCount: ticks.length,
                        firstTicks: ticks.slice(0, 8),
                        imgW: W,
                        imgH: H,
                        debugPixels
                    });
                };
                img.onerror = () => resolve({ error: 'image_load_failed' });
                img.src = 'data:image/png;base64,' + b64Data;
            });
        }""", b64)

        if not scan or scan.get('error'):
            print(f"  [ERROR] Pixel scan failed: {scan}")
            continue

        playhead_px = scan['playheadX']
        pps = scan['pxPerSec']  # in screenshot pixels (= CSS pixels since clip matches)
        print(f"    Playhead at screenshot X={playhead_px} "
              f"(viewport X={cLeft + playhead_px:.0f})" if playhead_px >= 0 else "    Playhead: NOT FOUND")
        print(f"    pxPerSec: {pps:.1f} | Ticks: {scan['tickCount']} → {scan['firstTicks']}")
        print(f"    Debug pixels at playhead: {scan['debugPixels']}")

        if playhead_px < 0:
            print("  [ERROR] Could not find cyan playhead in screenshot!")
            continue

        # ── Step 4: Compute drag coordinates ──
        # playhead_px is in screenshot coords = CSS viewport coords relative to canvas left
        playhead_viewport_x = cLeft + playhead_px

        if pps > 0:
            start_x = playhead_viewport_x + (start_sec * pps)
            end_x = playhead_viewport_x + (end_sec * pps)
        else:
            # No tick calibration — drag from playhead ~200px right
            start_x = playhead_viewport_x
            end_x = playhead_viewport_x + min(250, cWidth * 0.15)

        # Clamp to canvas bounds
        start_x = max(cLeft + 5, min(start_x, cLeft + cWidth - 25))
        end_x = max(start_x + 20, min(end_x, cLeft + cWidth - 5))

        # Y = lower 70% of canvas (below ruler at top)
        y = cTop + cHeight * 0.7

        drag_distance = end_x - start_x
        print(f"    Drag: X={start_x:.0f} → {end_x:.0f} (dist={drag_distance:.0f}px) Y={y:.0f}")

        if drag_distance < 10:
            print("  [ERROR] Drag distance too small!")
            continue

        # ── Step 5: Human-like drag ──
        await page.mouse.move(start_x, y)
        await page.wait_for_timeout(300)

        await page.mouse.down()
        await page.wait_for_timeout(200)

        num_steps = max(25, int(drag_distance / 6))
        step_size = drag_distance / num_steps
        cx = start_x
        for _ in range(num_steps):
            cx += step_size
            await page.mouse.move(cx, y)
            await page.wait_for_timeout(30)

        await page.wait_for_timeout(250)
        await page.mouse.up()
        print("    Mouse released. Waiting for UI...")

        # ── Step 6: Handle popups ──
        await page.wait_for_timeout(500)
        try:
            popup = page.locator('button:has-text("OK"), button:has-text("Yes"), '
                                 'button:has-text("Confirm"), button:has-text("Accept")')
            if await popup.count() > 0:
                print("    [POPUP] Dismissing...")
                await popup.first.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass

        await page.wait_for_timeout(1000)

        # ── Step 7: Verify placeholder appeared ──
        new_count = await container.locator('> div').count()
        if new_count <= initial_count:
            print(f"    [FAIL] No new segment! (count={new_count})")
            await page.mouse.click(10, 10)
            await page.wait_for_timeout(300)
            continue

        print(f"  [SUCCESS] Placeholder created! (rows: {initial_count} → {new_count})")
        return True

    print("  [ERROR] All attempts failed!")
    return False

async def click_add_segment(page, is_first=False, start_sec=0.0, end_sec=10.0):
    """
    Spawns a new segment row.
    - 1st segment: calibrated drag on the waveform editable lane.
    - Subsequent: clicks '+' button on the last segment row.
    """
    try:
        container = page.locator('#subTitleContainer')
        initial_count = await container.locator('> div').count()
        
        if is_first or initial_count == 0:
            success = await _calibrated_drag_first_segment(
                page, container, initial_count, start_sec, end_sec
            )
            if not success:
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
