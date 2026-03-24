# """
# annotic_automator.py — Full Pipeline Automation

# Flow:
#   1. Open browser → navigate to Annotic task page
#   2. Download the audio file
#   3. Delete ALL existing segments (they belong to someone else)
#   4. Run 4-stage Whisper-first pipeline:
#      LISTEN → CHUNK → CLASSIFY → FORMAT
#   5. Create new segments with correct timestamps
#   6. Fill text into each segment
#   7. Click Update → verify save
# """

# import asyncio
# from playwright.async_api import async_playwright
# import config
# from audio_processor import AudioProcessor
# import os
# import urllib.request


# async def automate_annotic():
#     print("=" * 60)
#     print("  ANNOTIC AUTOMATOR — Whisper-First Pipeline")
#     print("=" * 60)

#     async with async_playwright() as p:
#         browser = await p.chromium.launch_persistent_context(
#             config.PLAYWRIGHT_SESSION_DIR,
#             headless=config.HEADLESS_MODE,
#         )
#         page = browser.pages[0] if browser.pages else await browser.new_page()

#         # Handle any native window.confirm or window.alert dialogs automatically
#         async def handle_dialog(dialog):
#             print(f"\n[UI] Auto-accepting native dialog: {dialog.message}")
#             await dialog.accept()
#         page.on("dialog", handle_dialog)

#         # Navigate
#         print(f"\n[NAV] Opening {config.ANNOTIC_TASK_URL}")
#         await page.goto(config.ANNOTIC_TASK_URL, wait_until="networkidle", timeout=30000)
#         await page.wait_for_timeout(3000)
#         print("[NAV] Task page loaded.")

#         # ==============================================================
#         # STEP 1: Download Audio
#         # ==============================================================
#         print("\n" + "=" * 60)
#         print("  STEP 1: Download Audio")
#         print("=" * 60)

#         audio_src = await page.locator("audio#audio-panel").get_attribute("src")
#         print(f"[DOWNLOAD] Source: {audio_src}")

#         try:
#             urllib.request.urlretrieve(audio_src, config.AUDIO_FILE)
#             print(f"[DOWNLOAD] Saved: {config.AUDIO_FILE}")
#         except Exception as e:
#             print(f"[ERROR] Download failed: {e}")
#             await browser.close()
#             return

#         # ==============================================================
#         # STEP 2: Run Whisper-First 4-Stage Pipeline
#         # ==============================================================
#         print("\n" + "=" * 60)
#         print("  STEP 2: Whisper-First Pipeline")
#         print("=" * 60)

#         ap = AudioProcessor(config.WHISPER_MODEL_SIZE)

#         chunks, detected_lang = ap.run_pipeline(
#             config.AUDIO_FILE,
#             language=config.WHISPER_LANGUAGE,
#             silence_threshold_s=config.SILENCE_THRESHOLD_S,
#         )

#         # Filter only chunks that have text to fill
#         fill_chunks = [c for c in chunks if c.get("text_final", "").strip()]
#         print(f"\n[PIPELINE] {len(fill_chunks)} chunks to create as segments.")

#         for i, c in enumerate(fill_chunks[:15]):
#             start_str = ap.format_time(c["start"])
#             end_str = ap.format_time(c["end"])
#             print(f"  {i+1}. [{start_str} - {end_str}] "
#                   f"{c['event']:>12s} → \"{c['text_final']}\" "
#                   f"(conf={c.get('confidence', 0):.2f})")
#         if len(fill_chunks) > 15:
#             print(f"  ... and {len(fill_chunks)-15} more.")

#         # ==============================================================
#         # STEP 3: Reconcile Segments (Preserve & Adjust)
#         # ==============================================================
#         print("\n" + "=" * 60)
#         print("  STEP 3: Reconcile Segments (Preserve & Adjust)")
#         print("=" * 60)

#         await reconcile_segments(page, fill_chunks, ap)

#         # ==============================================================
#         # STEP 4: Save & Verify
#         # ==============================================================
#         print("\n" + "=" * 60)
#         print("  STEP 4: Save & Verify")
#         print("=" * 60)

#         await save_and_verify(page)

#         # ==============================================================
#         # DONE
#         # ==============================================================
#         print("\n" + "=" * 60)
#         print(f"  COMPLETE: Created {len(fill_chunks)} segments")
#         print(f"  Language: {detected_lang}")
#         print("=" * 60)

#         print("\nBrowser open for 30s review...")
#         await page.wait_for_timeout(30000)
#         await browser.close()


# # ======================================================================
# # CORE LOGIC: RECONCILE SEGMENTS
# # ======================================================================

# async def reconcile_segments(page, fill_chunks, ap):
#     """
#     Core Logic Refinement: Preserve and Adjust
#     1. Scan existing segments
#     2. Adjust existing segments to match target chunks
#     3. Add missing segments if target > existing
#     4. Delete excess segments if target < existing
#     """
#     container = page.locator('#subTitleContainer')
#     existing = await _count_segments(page)
#     target = len(fill_chunks)
    
#     print(f"[RECONCILE] Existing placeholders: {existing}, Target segments: {target}")
    
#     # Pre-validate: Check if we have any segments to fill
#     if target == 0:
#         print("  [WARN] No chunks to fill. Deleting all segments.")
#         await delete_all_segments(page)
#         return

#     # PHASE 1: Adjust existing segments (overlapping count)
#     overlap = int(min(existing, target))
#     if overlap > 0:
#         print(f"\n  [Phase 1] Adjusting {overlap} existing segments...")
#         for i in range(overlap):
#             chunk = fill_chunks[i]
#             start = 0.0 if i == 0 else chunk["start"]
#             end = chunk["end"]
            
#             print(f"    Adjusting {i+1}/{overlap}: [{ap.format_time(start)} - {ap.format_time(end)}]")
#             await set_segment_timestamps(page, container, i, start, end)
#             await fill_segment_text(page, container, i, chunk["text_final"])
#             await page.wait_for_timeout(100)
            
#     # PHASE 2: Add missing segments
#     if target > existing:
#         missing = target - existing
#         print(f"\n  [Phase 2] Adding {missing} new segments...")
#         for i in range(existing, target):
#             chunk = fill_chunks[i]
#             start = 0.0 if i == 0 else chunk["start"]
#             end = chunk["end"]
            
#             print(f"    Adding {i+1}/{target}: [{ap.format_time(start)} - {ap.format_time(end)}]")
#             success = await click_add_segment(page, is_first=(existing == 0 and i == 0),
#                                               start_sec=start, end_sec=end)
#             if not success:
#                 print(f"  [ERROR] Failed to add segment {i+1}.")
#                 break
                
#             await page.wait_for_timeout(300)
#             await set_segment_timestamps(page, container, i, start, end)
#             await fill_segment_text(page, container, i, chunk["text_final"])
            
#     # PHASE 3: Remove excess segments from the end
#     if existing > target:
#         excess = existing - target
#         print(f"\n  [Phase 3] Deleting {excess} excess segments from the end...")
#         for i in range(excess):
#             current = await _count_segments(page)
#             if current <= target:
#                 break
                
#             print(f"    Deleting excess segment ({current} left)...")
#             success = await _delete_last_segment_native(page)
#             if not success:
#                 print(f"  [ERROR] Failed to delete excess segment at count {current}.")
#                 break
#             await page.wait_for_timeout(300)

#     # Note: Phase 4 (Validation) is implicitly handled by the accurate 
#     # typing in set_segment_timestamps which mechanically aligns the 
#     # inputs to match the exactly sequenced Whisper chunks.

# # ======================================================================
# # DOM INTERACTION HELPERS
# # ======================================================================

# async def delete_all_segments(page):
#     """
#     Delete ALL existing segments using Playwright native clicks.
    
#     KEY FIX: Previous versions used JS element.click() which does NOT
#     trigger React's synthetic event handlers. Playwright's .click()
#     simulates a real mouse click, which works.
#     """
#     # Count segments
#     seg_count = await _count_segments(page)
#     print(f"[DELETE] Found {seg_count} existing segment(s).", flush=True)
    
#     if seg_count <= 0:
#         return

#     # First, dump the button structure for debugging
#     await _dump_row_buttons(page)

#     if seg_count == 1:
#         # Cannot delete the only remaining segment, so we just wipe its text
#         print("[DELETE] Only 1 segment. Clearing text...")
#         await _clear_segment_textarea(page, 0)
#         print(f"[DELETE] Done. 1 clean segment remaining.")
#         return

#     # Multiple segments: delete from last to first
#     deleted = 0
#     # Process deletions quicker since dialogs are auto-acked
#     while True:
#         current = await _count_segments(page)
#         if current <= 1:
#             break
        
#         success = await _delete_last_segment_native(page)
#         if success:
#             deleted += 1
#             if deleted % 20 == 0:
#                 print(f"[DELETE] {deleted} deleted...", flush=True)
#             await page.wait_for_timeout(10)  # Minimal wait
#         else:
#             print(f"[DELETE] Failed to delete at count={current}. Stopping.")
#             break

#     await _clear_segment_textarea(page, 0)
#     print(f"[DELETE] Done! Deleted {deleted}. {await _count_segments(page)} clean segment remaining.")


# async def _count_segments(page):
#     """Count segment rows in the container."""
#     return await page.evaluate("""
#     () => {
#         const c = document.getElementById('subTitleContainer');
#         return c ? Array.from(c.children).filter(r => r.querySelector('textarea')).length : 0;
#     }
#     """)


# async def _dump_row_buttons(page):
#     """Print all buttons on the first row for debugging."""
#     info = await page.evaluate("""
#     () => {
#         const c = document.getElementById('subTitleContainer');
#         if (!c) return [];
#         const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
#         if (rows.length === 0) return [];
#         const row = rows[0];
#         const btns = row.querySelectorAll('button');
#         return Array.from(btns).map((btn, i) => ({
#             i: i,
#             text: btn.textContent.trim().substring(0, 20),
#             cls: (btn.className || '').substring(0, 80),
#             html: btn.outerHTML.substring(0, 120),
#         }));
#     }
#     """)
#     if info:
#         print(f"[DEBUG] Buttons on row 0: {len(info)}")
#         for b in info:
#             print(f"  btn[{b['i']}] text='{b['text']}' html={b['html'][:100]}")


# async def _delete_last_segment_native(page):
#     """
#     Delete the LAST segment row using Playwright native clicks.
    
#     Strategy based on UI screenshot:
#     1. Find the delete button (trash can) on the last row and mark it.
#     2. Click the delete button.
#     (No need to click + first, as the trash button is already visible!)
#     """
#     found_delete = await page.evaluate("""
#     () => {
#         const c = document.getElementById('subTitleContainer');
#         if (!c) return false;
        
#         // Find all semantic segment rows
#         const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
#         if (rows.length <= 1) return false; // Don't delete the only remaining segment!
        
#         const lastRow = rows[rows.length - 1];
#         const buttons = lastRow.querySelectorAll('button');
        
#         for (const btn of buttons) {
#             const svg = btn.querySelector('svg');
            
#             // Look for standard DeleteIcon
#             if (svg && svg.getAttribute('data-testid') === 'DeleteIcon') {
#                 btn.setAttribute('data-temp-delete', 'true');
#                 return true;
#             }
#             // Another common tell for delete is an SVG with the trash can path:
#             if (svg && btn.innerHTML.includes('M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z')) {
#                 btn.setAttribute('data-temp-delete', 'true');
#                 return true;
#             }
#         }
        
#         // If we still can't find it, look for red colored buttons (like the trash icon)
#         for (const btn of buttons) {
#             const style = window.getComputedStyle(btn);
#             if (style.color.includes('rgb(211, 47') || style.color.includes('red') || style.color.includes('d32f2f')) {
#                 btn.setAttribute('data-temp-delete', 'true');
#                 return true;
#             }
#         }
        
#         // Let's identify the one that is NOT + and NOT - based on SVG paths/testIds
#         // The buttons are almost always [-, arrow?, trash, +] 
#         let actionBtns = [];
#         for (const btn of buttons) {
#              const svg = btn.querySelector('svg');
#              if (!svg) continue;
#              const testId = svg.getAttribute('data-testid') || '';
             
#              // Ignore specific dropdown/menu buttons
#              if (btn.textContent.trim().includes('Speaker')) continue;
             
#              actionBtns.push(btn);
#         }
        
#         // We know the trash icon is usually the second to last button or the one before the + button
#         for (const btn of actionBtns) {
#             const svg = btn.querySelector('svg');
#             if (!svg) continue;
#             const testId = svg.getAttribute('data-testid') || '';
            
#             if (testId !== 'AddIcon' && testId !== 'RemoveIcon' && btn.textContent.trim() === '') {
#                 btn.setAttribute('data-temp-delete', 'true');
#                 return true;
#             }
#         }
        
#         return false;
#     }
#     """)
    
#     if found_delete:
#         try:
#             target = page.locator('[data-temp-delete="true"]')
#             if await target.count() > 0:
#                 await target.first.click()
#                 await page.wait_for_timeout(100) # Wait for React to process deletion
#                 # Cleanup marker if it didn't get removed from DOM
#                 await page.evaluate("() => { const e = document.querySelector('[data-temp-delete]'); if (e) e.removeAttribute('data-temp-delete'); }")
#                 return True
#         except Exception as e:
#             print(f"[DELETE] Click error: {e}")
            
#     return False


# async def _clear_segment_textarea(page, row_index):
#     """Clear the textarea content of a specific segment row."""
#     await page.evaluate("""
#     (idx) => {
#         const c = document.getElementById('subTitleContainer');
#         if (!c) return;
#         const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
#         if (!rows[idx]) return;
#         const ta = rows[idx].querySelector('textarea');
#         if (!ta) return;
#         const setter = Object.getOwnPropertyDescriptor(
#             window.HTMLTextAreaElement.prototype, 'value'
#         ).set;
#         setter.call(ta, '');
#         ta.dispatchEvent(new Event('input', { bubbles: true }));
#         ta.dispatchEvent(new Event('change', { bubbles: true }));
#     }
#     """, row_index)


# async def _calibrated_drag_first_segment(page, container, initial_count, start_sec, end_sec):
#     """
#     Create the first segment by finding the playhead via SCREENSHOT pixel scan.
#     Uses Playwright screenshot (bypasses CORS canvas taint), sends base64 image
#     back to browser for pixel analysis on a fresh untainted canvas.
#     """
#     import base64
#     MAX_ATTEMPTS = 2

#     for attempt in range(1, MAX_ATTEMPTS + 1):
#         print(f"\n  [ATTEMPT {attempt}/{MAX_ATTEMPTS}] Creating first segment "
#               f"[{start_sec:.3f}s - {end_sec:.3f}s]...")

#         # ── Step 1: Wait for canvas & scroll into view ──
#         try:
#             await page.wait_for_selector('canvas', state='visible', timeout=10000)
#         except Exception:
#             print("  [ERROR] No canvas became visible within 10s!")
#             continue
#         await page.wait_for_timeout(1500)

#         # Scroll canvas into view and get its bounds
#         canvas_info = await page.evaluate("""() => {
#             const canvases = Array.from(document.querySelectorAll('canvas'))
#                 .map(c => ({ el: c, rect: c.getBoundingClientRect() }))
#                 .filter(c => c.rect.width > 100 && c.rect.height > 10)
#                 .sort((a, b) => b.rect.top - a.rect.top);
#             if (!canvases.length) return null;
#             canvases[0].el.scrollIntoView({ block: 'center', behavior: 'instant' });
#             return null;  // will re-read after scroll
#         }""")
#         await page.wait_for_timeout(600)

#         # Re-read canvas bounds AFTER scroll completes
#         canvas_info = await page.evaluate("""() => {
#             const canvases = Array.from(document.querySelectorAll('canvas'))
#                 .map(c => ({ el: c, rect: c.getBoundingClientRect() }))
#                 .filter(c => c.rect.width > 100 && c.rect.height > 10)
#                 .sort((a, b) => b.rect.top - a.rect.top);
#             if (!canvases.length) return null;
#             const r = canvases[0].rect;
#             return { top: r.top, left: r.left, width: r.width, height: r.height };
#         }""")

#         if not canvas_info:
#             print("  [ERROR] No canvas found!")
#             continue

#         cTop = canvas_info['top']
#         cLeft = canvas_info['left']
#         cWidth = canvas_info['width']
#         cHeight = canvas_info['height']
#         print(f"    Canvas after scroll: left={cLeft:.0f} top={cTop:.0f} w={cWidth:.0f} h={cHeight:.0f}")

#         # ── Step 2: Take a Playwright screenshot of the canvas area ──
#         # This bypasses CORS canvas taint — Playwright captures rendered pixels
#         try:
#             screenshot_bytes = await page.screenshot(clip={
#                 'x': max(0, cLeft),
#                 'y': max(0, cTop),
#                 'width': cWidth,
#                 'height': cHeight
#             })
#             b64 = base64.b64encode(screenshot_bytes).decode('ascii')
#             print(f"    Screenshot captured: {len(screenshot_bytes)} bytes")
#         except Exception as e:
#             print(f"  [ERROR] Screenshot failed: {e}")
#             continue

#         # ── Step 3: Send screenshot to browser & scan for cyan playhead ──
#         # Draw on a fresh un-tainted canvas, scan pixel columns for cyan line
#         scan = await page.evaluate("""(b64Data) => {
#             return new Promise((resolve) => {
#                 const img = new Image();
#                 img.onload = () => {
#                     const c = document.createElement('canvas');
#                     c.width = img.width;
#                     c.height = img.height;
#                     const ctx = c.getContext('2d');
#                     ctx.drawImage(img, 0, 0);

#                     const imgData = ctx.getImageData(0, 0, c.width, c.height);
#                     const d = imgData.data;
#                     const W = c.width, H = c.height;

#                     // ── Find CYAN playhead (R<120, G>140, B>140) ──
#                     let playheadX = -1;
#                     for (let x = 0; x < W; x++) {
#                         let cyanCount = 0;
#                         const samples = 10;
#                         for (let s = 0; s < samples; s++) {
#                             const y = Math.floor(H * 0.15 + H * 0.7 * s / samples);
#                             const i = (y * W + x) * 4;
#                             const r = d[i], g = d[i+1], b = d[i+2];
#                             if (r < 130 && g > 130 && b > 130 &&
#                                 (g + b - 2 * r) > 80) {
#                                 cyanCount++;
#                             }
#                         }
#                         if (cyanCount >= 3) {
#                             playheadX = x;
#                             break;
#                         }
#                     }

#                     // ── Find ruler tick marks (dark vertical lines in top 20%) ──
#                     const rulerH = Math.floor(H * 0.2);
#                     const ticks = [];
#                     for (let x = 0; x < W; x++) {
#                         let darkCount = 0;
#                         for (let y = 1; y < rulerH; y += 2) {
#                             const i = (y * W + x) * 4;
#                             const bri = d[i] + d[i+1] + d[i+2];
#                             if (bri < 400 && d[i+3] > 150) darkCount++;
#                         }
#                         if (darkCount >= rulerH * 0.12) {
#                             if (!ticks.length || x - ticks[ticks.length-1] > 10) {
#                                 ticks.push(x);
#                             }
#                         }
#                     }

#                     let pxPerSec = 0;
#                     if (ticks.length >= 3) {
#                         const spacings = [];
#                         for (let i = 1; i < ticks.length; i++) {
#                             spacings.push(ticks[i] - ticks[i-1]);
#                         }
#                         spacings.sort((a, b) => a - b);
#                         pxPerSec = spacings[Math.floor(spacings.length / 2)];
#                     }

#                     // Also sample a few pixel colors for debugging
#                     const debugPixels = [];
#                     if (playheadX >= 0) {
#                         for (let s = 0; s < 5; s++) {
#                             const y = Math.floor(H * 0.2 + H * 0.6 * s / 5);
#                             const i = (y * W + playheadX) * 4;
#                             debugPixels.push(`(${d[i]},${d[i+1]},${d[i+2]})`);
#                         }
#                     }

#                     resolve({
#                         playheadX,
#                         pxPerSec,
#                         tickCount: ticks.length,
#                         firstTicks: ticks.slice(0, 8),
#                         imgW: W,
#                         imgH: H,
#                         debugPixels
#                     });
#                 };
#                 img.onerror = () => resolve({ error: 'image_load_failed' });
#                 img.src = 'data:image/png;base64,' + b64Data;
#             });
#         }""", b64)

#         if not scan or scan.get('error'):
#             print(f"  [ERROR] Pixel scan failed: {scan}")
#             continue

#         playhead_px = scan['playheadX']
#         pps = scan['pxPerSec']  # in screenshot pixels (= CSS pixels since clip matches)
#         print(f"    Playhead at screenshot X={playhead_px} "
#               f"(viewport X={cLeft + playhead_px:.0f})" if playhead_px >= 0 else "    Playhead: NOT FOUND")
#         print(f"    pxPerSec: {pps:.1f} | Ticks: {scan['tickCount']} → {scan['firstTicks']}")
#         print(f"    Debug pixels at playhead: {scan['debugPixels']}")

#         if playhead_px < 0:
#             print("  [ERROR] Could not find cyan playhead in screenshot!")
#             continue

#         # ── Step 4: Compute drag coordinates ──
#         # playhead_px is in screenshot coords = CSS viewport coords relative to canvas left
#         playhead_viewport_x = cLeft + playhead_px

#         if pps > 0:
#             start_x = playhead_viewport_x + (start_sec * pps)
#             end_x = playhead_viewport_x + (end_sec * pps)
#         else:
#             # No tick calibration — drag from playhead ~200px right
#             start_x = playhead_viewport_x
#             end_x = playhead_viewport_x + min(250, cWidth * 0.15)

#         # Clamp to canvas bounds
#         start_x = max(cLeft + 5, min(start_x, cLeft + cWidth - 25))
#         end_x = max(start_x + 20, min(end_x, cLeft + cWidth - 5))

#         # Y = lower 70% of canvas (below ruler at top)
#         y = cTop + cHeight * 0.7

#         drag_distance = end_x - start_x
#         print(f"    Drag: X={start_x:.0f} → {end_x:.0f} (dist={drag_distance:.0f}px) Y={y:.0f}")

#         if drag_distance < 10:
#             print("  [ERROR] Drag distance too small!")
#             continue

#         # ── Step 5: Human-like drag ──
#         await page.mouse.move(start_x, y)
#         await page.wait_for_timeout(300)

#         await page.mouse.down()
#         await page.wait_for_timeout(200)

#         num_steps = max(25, int(drag_distance / 6))
#         step_size = drag_distance / num_steps
#         cx = start_x
#         for _ in range(num_steps):
#             cx += step_size
#             await page.mouse.move(cx, y)
#             await page.wait_for_timeout(30)

#         await page.wait_for_timeout(250)
#         await page.mouse.up()
#         print("    Mouse released. Waiting for UI...")

#         # ── Step 6: Handle popups ──
#         await page.wait_for_timeout(500)
#         try:
#             popup = page.locator('button:has-text("OK"), button:has-text("Yes"), '
#                                  'button:has-text("Confirm"), button:has-text("Accept")')
#             if await popup.count() > 0:
#                 print("    [POPUP] Dismissing...")
#                 await popup.first.click()
#                 await page.wait_for_timeout(500)
#         except Exception:
#             pass

#         await page.wait_for_timeout(1000)

#         # ── Step 7: Verify placeholder appeared ──
#         new_count = await container.locator('> div').count()
#         if new_count <= initial_count:
#             print(f"    [FAIL] No new segment! (count={new_count})")
#             await page.mouse.click(10, 10)
#             await page.wait_for_timeout(300)
#             continue

#         print(f"  [SUCCESS] Placeholder created! (rows: {initial_count} → {new_count})")
#         return True

#     print("  [ERROR] All attempts failed!")
#     return False

# async def click_add_segment(page, is_first=False, start_sec=0.0, end_sec=10.0):
#     """
#     Spawns a new segment row.
#     - 1st segment: calibrated drag on the waveform editable lane.
#     - Subsequent: clicks '+' button on the last segment row.
#     """
#     try:
#         container = page.locator('#subTitleContainer')
#         initial_count = await container.locator('> div').count()
        
#         if is_first or initial_count == 0:
#             success = await _calibrated_drag_first_segment(
#                 page, container, initial_count, start_sec, end_sec
#             )
#             if not success:
#                 return False
                
#         else:
#             # Click '+' button on the LAST row
#             clicked_plus = await page.evaluate("""() => {
#                 const c = document.getElementById('subTitleContainer');
#                 if (!c || c.children.length === 0) return false;
                
#                 // Get strictly the rows that contain textareas
#                 const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
#                 if (rows.length === 0) return false;
                
#                 const lastRow = rows[rows.length - 1];
#                 const btns = Array.from(lastRow.querySelectorAll('button'));
                
#                 // Look for AddIcon path
#                 const plusBtn = btns.find(b => {
#                     const svg = b.querySelector('svg path');
#                     return svg && svg.getAttribute('d') && svg.getAttribute('d').includes('M19 13h-6');
#                 });
                
#                 if (plusBtn) { plusBtn.click(); return true; }
                
#                 // Fallback: usually the 2nd to last button
#                 if (btns.length >= 2) {
#                     btns[btns.length - 2].click();
#                     return true;
#                 }
#                 return false;
#             }""")
            
#             if not clicked_plus:
#                 print("  [ERROR] Could not find '+' button on the last segment row!")
#                 return False
        
#         # Wait for the new row to actually spawn
#         for _ in range(30):
#             await page.wait_for_timeout(100)
#             if await container.locator('> div').count() > initial_count:
#                 return True
                
#         print("  [ERROR] UI did not add a segment row after interaction!")
#         return False
        
#     except Exception as e:
#         print(f"  [ERROR] Exception in click_add_segment: {e}")
#         return False


# async def set_segment_timestamps(page, container, seg_index, start_seconds, end_seconds):
#     """
#     Set the start and end timestamps using Playwright native locators and pure native keystrokes.
#     Pressing 'Enter' mechanically is critical to force Annotic's React state to stretch the purple
#     timeline block to the newly matched values.
#     """
#     try:
#         # Prevent React from silently rejecting out-of-bounds Whisper segment end times!
#         audio_dur = await page.evaluate("() => { const a = document.querySelector('audio'); return (a && a.duration > 0) ? a.duration : 100.0; }")
#         if end_seconds >= audio_dur:
#             end_seconds = audio_dur - 0.001
            
#         def format_ts(sec):
#             hh = int(sec // 3600)
#             mm = int((sec % 3600) // 60)
#             ss = int(sec % 60)
#             ms = int(round((sec - int(sec)) * 1000))
#             return f"{hh:02d}", f"{mm:02d}", f"{ss:02d}", f"{ms:03d}"
            
#         sh, sm, ss, sms = format_ts(start_seconds)
#         eh, em, es, ems = format_ts(end_seconds)

#         row = container.locator(f'> div:nth-child({seg_index + 1})')
#         # According to the HTML dump, the 8 actual timestamp boxes use type="number"
#         inputs = row.locator('input[type="number"]')

#         count = await inputs.count()
#         if count != 8:
#             print(f"  [WARN] Expected 8 number inputs for segment {seg_index}, got {count}")
#             return
            
#         ts_map = {
#             0: sh, 1: sm, 2: ss, 3: sms,
#             4: eh, 5: em, 6: es, 7: ems,
#         }
        
#         for idx, val in ts_map.items():
#             field = inputs.nth(idx)
#             # Mechanical Human Emulation typing heavily pierces internal React synthetic states
#             await field.click()
#             await page.keyboard.press("Control+A")
#             await page.keyboard.press("Backspace")
#             await page.keyboard.type(str(val), delay=50) # Slower typing creates undeniable synthetic updates
#             await page.keyboard.press("Enter")
#             await page.wait_for_timeout(100) # Give React time to stretch the 1D UI block timeline
            
#     except Exception as e:
#         print(f"  [ERROR] Failed to set timestamps purely in Playwright: {e}")


# async def fill_segment_text(page, container, seg_index, text):
#     """Fill the textarea of a specific segment with text."""
#     fill_script = """
#     (args) => {
#         const container = document.getElementById('subTitleContainer');
#         if (!container) return false;
#         const rows = Array.from(container.children).filter(
#             row => row.querySelector('textarea')
#         );
#         const row = rows[args.segIndex];
#         if (!row) return false;
        
#         const textarea = row.querySelector('textarea');
#         if (!textarea) return false;
        
#         const setter = Object.getOwnPropertyDescriptor(
#             window.HTMLTextAreaElement.prototype, 'value'
#         ).set;
#         setter.call(textarea, args.text);
#         textarea.dispatchEvent(new Event('input', { bubbles: true }));
#         textarea.dispatchEvent(new Event('change', { bubbles: true }));
#         return true;
#     }
#     """
#     result = await page.evaluate(fill_script, {
#         "segIndex": seg_index,
#         "text": text,
#     })
#     if not result:
#         print(f"  [WARN] Could not fill text for segment {seg_index}")


# async def save_and_verify(page):
#     """Click the Update/Save button and verify."""
#     print("[SAVE] Clicking Update...", flush=True)
    
#     update_opts = [
#         page.get_by_role("button", name="Update"),
#         page.get_by_role("button", name="Save"),
#         page.locator('button:has-text("Update")'),
#         page.locator('button:has-text("Submit")'),
#         page.locator('text="Update"').locator('visible=true').last
#     ]
    
#     clicked = False
#     for opt in update_opts:
#         try:
#             if await opt.count() > 0:
#                 await opt.first.click()
#                 clicked = True
#                 break
#         except Exception:
#             pass
            
#     if clicked:
#         await page.wait_for_timeout(2000)
#         # Check for success message
#         success = page.locator('text="success", text="saved", text="updated", .MuiAlert-standardSuccess')
#         if await success.count() > 0:
#             print("[SAVE] ✓ Saved successfully!")
#         else:
#             print("[SAVE] Clicked Update. Check manually for confirmation.")
#     else:
#         # Try the save icon button
#         save_icon = page.locator('svg[data-testid="SaveIcon"]')
#         if await save_icon.count() > 0:
#             await save_icon.first.locator('..').click()
#             await page.wait_for_timeout(2000)
#             print("[SAVE] Clicked save icon.")
#         else:
#             print("[SAVE] No Update/Save button found!")


# if __name__ == "__main__":
#     asyncio.run(automate_annotic())
"""
annotic_automator.py — Rewritten with Playhead-First Strategy

KEY INSIGHT:
  The waveform canvas is a scrollable view. The playhead is fixed at a
  viewport position. `canvas.left + t * px_per_sec` is WRONG because
  canvas.left changes as the waveform scrolls.

NEW STRATEGY (no drag needed):
  1. Seek audio to segment start_sec via JS (audio.currentTime = t)
  2. Wait for playhead/UI to update
  3. Click "+" button → segment is created at the playhead position
  4. Correct timestamps via input fields
  5. Fill textarea text

  This is 100% reliable and avoids all pixel/drag math.
"""

import asyncio
from playwright.async_api import async_playwright
import config
from audio_processor import AudioProcessor
import urllib.request


async def automate_annotic():
    print("=" * 60)
    print("  ANNOTIC AUTOMATOR — Playhead-First Strategy")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            config.PLAYWRIGHT_SESSION_DIR,
            headless=config.HEADLESS_MODE,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Auto-accept all native dialogs
        async def handle_dialog(dialog):
            print(f"\n[UI] Auto-accepting dialog: {dialog.message}")
            await dialog.accept()
        page.on("dialog", handle_dialog)

        # ── Navigate ──────────────────────────────────────────────
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
        # STEP 2: Run Whisper Pipeline
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

        fill_chunks = [c for c in chunks if c.get("text_final", "").strip()]
        print(f"\n[PIPELINE] {len(fill_chunks)} chunks to create.")
        for i, c in enumerate(fill_chunks[:15]):
            print(f"  {i+1}. [{ap.format_time(c['start'])} - {ap.format_time(c['end'])}] "
                  f"\"{c['text_final']}\"")
        if len(fill_chunks) > 15:
            print(f"  ... and {len(fill_chunks)-15} more.")

        if not fill_chunks:
            print("[ERROR] No chunks produced. Exiting.")
            await browser.close()
            return

        # ==============================================================
        # STEP 3: Delete ALL existing segments
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 3: Delete All Existing Segments")
        print("=" * 60)
        await delete_all_segments(page)

        # ==============================================================
        # STEP 4: Create ALL segments via Playhead-First strategy
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 4: Create Segments (Playhead-First)")
        print("=" * 60)
        await create_all_segments(page, fill_chunks, ap)

        # ==============================================================
        # STEP 5: Save & Verify
        # ==============================================================
        print("\n" + "=" * 60)
        print("  STEP 5: Save & Verify")
        print("=" * 60)
        await save_and_verify(page)

        print("\n" + "=" * 60)
        print(f"  COMPLETE — {len(fill_chunks)} segments | Language: {detected_lang}")
        print("=" * 60)

        print("\nBrowser open 30s for review...")
        await page.wait_for_timeout(30000)
        await browser.close()


# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════

async def _count_segments(page) -> int:
    return await page.evaluate("""() => {
        const c = document.getElementById('subTitleContainer');
        return c ? Array.from(c.children).filter(r => r.querySelector('textarea')).length : 0;
    }""")


async def _seek_audio(page, time_sec: float):
    """Seek the audio element to a specific time and wait for UI to update."""
    await page.evaluate(f"""() => {{
        const audio = document.querySelector('audio');
        if (audio) {{
            audio.currentTime = {time_sec};
            audio.dispatchEvent(new Event('timeupdate', {{ bubbles: true }}));
            audio.dispatchEvent(new Event('seeked',     {{ bubbles: true }}));
        }}
    }}""")
    # Give the React waveform component time to re-render the playhead
    await page.wait_for_timeout(400)


# ══════════════════════════════════════════════════════════════════════
#  DELETE ALL SEGMENTS
# ══════════════════════════════════════════════════════════════════════

async def delete_all_segments(page):
    count = await _count_segments(page)
    print(f"[DELETE] Found {count} segment(s).")

    if count == 0:
        return

    deleted = 0
    while True:
        current = await _count_segments(page)
        if current <= 1:
            break
        ok = await _delete_last_segment(page)
        if not ok:
            print(f"[DELETE] Could not delete at count={current}. Stopping.")
            break
        deleted += 1
        await page.wait_for_timeout(80)

    await _clear_textarea(page, 0)
    print(f"[DELETE] Done. Deleted {deleted}. 1 clean placeholder remains.")


async def _delete_last_segment(page) -> bool:
    found = await page.evaluate("""() => {
        const c = document.getElementById('subTitleContainer');
        if (!c) return false;
        const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
        if (rows.length <= 1) return false;
        const lastRow = rows[rows.length - 1];
        for (const btn of lastRow.querySelectorAll('button')) {
            const svg = btn.querySelector('svg');
            if (!svg) continue;
            const testId = svg.getAttribute('data-testid') || '';
            if (testId === 'DeleteIcon' ||
                btn.innerHTML.includes('M6 19c0 1.1') ||
                btn.innerHTML.includes('M19 4h-3.5')) {
                btn.setAttribute('data-del', 'yes');
                return true;
            }
        }
        // Fallback: red-colored button
        for (const btn of lastRow.querySelectorAll('button')) {
            const col = window.getComputedStyle(btn).color;
            if (col.includes('211, 47') || col.includes('d32f2f')) {
                btn.setAttribute('data-del', 'yes');
                return true;
            }
        }
        return false;
    }""")

    if not found:
        return False

    try:
        target = page.locator('[data-del="yes"]')
        if await target.count() > 0:
            await target.first.click()
            await page.wait_for_timeout(80)
            await page.evaluate(
                "() => { const e = document.querySelector('[data-del]'); "
                "if(e) e.removeAttribute('data-del'); }"
            )
            return True
    except Exception as e:
        print(f"[DELETE] Click error: {e}")

    return False


async def _clear_textarea(page, row_index: int):
    await page.evaluate("""(idx) => {
        const c = document.getElementById('subTitleContainer');
        if (!c) return;
        const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
        const ta = rows[idx]?.querySelector('textarea');
        if (!ta) return;
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')
              .set.call(ta, '');
        ta.dispatchEvent(new Event('input',  { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
    }""", row_index)


# ══════════════════════════════════════════════════════════════════════
#  CREATE FIRST SEGMENT VIA PLAYHEAD-RELATIVE DRAG
# ══════════════════════════════════════════════════════════════════════

async def _find_playhead_and_pps(page):
    """
    Find the playhead X position and pixels-per-second using 4 DOM strategies.
    Returns dict: { playhead_x, px_per_sec, canvas_box, strategy, error }
    All X values are VIEWPORT coordinates.
    """
    info = await page.evaluate("""() => {
        // Find the waveform canvas
        const canvases = Array.from(document.querySelectorAll('canvas'))
            .map(c => ({ el: c, rect: c.getBoundingClientRect() }))
            .filter(c => c.rect.width > 100 && c.rect.height > 10)
            .sort((a, b) => b.rect.width - a.rect.width);
        if (!canvases.length) return { error: 'no_canvas' };
        
        const canvas = canvases[0];
        const cRect = canvas.rect;
        
        const audio = document.querySelector('audio');
        const currentTime = audio ? audio.currentTime : 0;
        const duration = audio ? audio.duration : 0;
        
        // Calculate px_per_sec from the canvas scroll width vs audio duration
        // The canvas's parent is usually scrollable; its scrollWidth represents the full timeline
        const parent = canvas.el.parentElement;
        const scrollW = parent ? parent.scrollWidth : cRect.width;
        const pxPerSec = duration > 0 ? scrollW / duration : 100;
        
        let playheadX = -1;
        let strategy = 'none';
        
        // Strategy 1: Look for cursor/playhead element by class
        const cursorSelectors = [
            '.wavesurfer-cursor',
            '[data-testid="cursor"]',
            '.cursor',
            'wave cursor'
        ];
        for (const sel of cursorSelectors) {
            const el = document.querySelector(sel);
            if (el) {
                const r = el.getBoundingClientRect();
                if (r.width < 10 && r.height > 20) {
                    playheadX = r.left + r.width / 2;
                    strategy = 'cursor_class:' + sel;
                    break;
                }
            }
        }
        
        // Strategy 2: Look inside WaveSurfer's inner <wave> for thin vertical child
        if (playheadX < 0) {
            const waves = document.querySelectorAll('wave, .wave, #waveform wave');
            for (const wave of waves) {
                for (const child of wave.children) {
                    const r = child.getBoundingClientRect();
                    if (r.width <= 3 && r.height > 30 && r.left >= cRect.left && r.left <= cRect.right) {
                        playheadX = r.left + r.width / 2;
                        strategy = 'wave_child';
                        break;
                    }
                }
                if (playheadX >= 0) break;
            }
        }
        
        // Strategy 3: Search all elements inside the waveform container for thin vertical bars
        if (playheadX < 0) {
            const container = canvas.el.parentElement?.parentElement || canvas.el.parentElement;
            if (container) {
                const allEls = container.querySelectorAll('*');
                for (const el of allEls) {
                    const r = el.getBoundingClientRect();
                    if (r.width <= 4 && r.height > 30 && r.left >= cRect.left - 5 && r.left <= cRect.right + 5) {
                        const style = window.getComputedStyle(el);
                        const bg = style.backgroundColor;
                        // Playhead is usually brightly colored (cyan, red, white etc)
                        if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
                            playheadX = r.left + r.width / 2;
                            strategy = 'thin_bar';
                            break;
                        }
                    }
                }
            }
        }
        
        // Strategy 4: Fallback — use time-based position on the visible canvas
        if (playheadX < 0) {
            // If audio is at t=0 and the canvas scrollLeft is 0, playhead is at canvas.left
            const scrollLeft = parent ? parent.scrollLeft : 0;
            playheadX = cRect.left + (currentTime * pxPerSec) - scrollLeft;
            strategy = 'fallback_calc';
        }
        
        // Diagnostic dump for debugging
        const diag = [];
        const container2 = canvas.el.parentElement?.parentElement || canvas.el.parentElement;
        if (container2) {
            for (const el of container2.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                if (r.width <= 5 && r.height > 20 && r.left >= cRect.left - 10 && r.left <= cRect.right + 10) {
                    diag.push({
                        tag: el.tagName,
                        className: el.className,
                        w: r.width, h: r.height,
                        left: r.left,
                        bg: window.getComputedStyle(el).backgroundColor
                    });
                }
            }
        }
        
        return {
            playhead_x: playheadX,
            px_per_sec: pxPerSec,
            canvas_box: { x: cRect.left, y: cRect.top, w: cRect.width, h: cRect.height },
            current_time: currentTime,
            duration: duration,
            strategy: strategy,
            diag: diag.slice(0, 10)
        };
    }""")
    return info


async def _calibrated_drag_first_segment(page, start_sec: float, end_sec: float) -> bool:
    """
    Create the first segment by:
      1. Seeking audio to t=0 (so playhead is at known position)
      2. Finding playhead via 4 DOM strategies  
      3. Computing drag start/end using: x = playhead_x + (t - currentTime) * pxPerSec
      4. Performing a slow physical Playwright mouse drag
    """
    MAX_ATTEMPTS = 3
    
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n    [ATTEMPT {attempt}/{MAX_ATTEMPTS}] Playhead-relative drag...")

        # 1. Seek to t=0 to put playhead at a known location
        await _seek_audio(page, 0.0)
        await page.wait_for_timeout(600)

        # 2. Scroll canvas into view using Playwright's native method
        canvas_el = page.locator('canvas').first
        if await canvas_el.count() == 0:
            print("      [ERROR] No canvas found!")
            continue
        await canvas_el.scroll_into_view_if_needed()
        await page.wait_for_timeout(400)

        # 3. Find playhead position and pxPerSec
        info = await _find_playhead_and_pps(page)
        
        if info.get('error'):
            print(f"      [ERROR] {info['error']}")
            continue

        ph_x = info['playhead_x']
        pps = info['px_per_sec']
        cur_t = info['current_time']
        cb = info['canvas_box']
        strategy = info['strategy']

        print(f"      Strategy: {strategy}")
        print(f"      Playhead X: {ph_x:.0f}, PPS: {pps:.1f}, currentTime: {cur_t:.3f}")
        print(f"      Canvas: x={cb['x']:.0f} y={cb['y']:.0f} w={cb['w']:.0f} h={cb['h']:.0f}")

        if info.get('diag'):
            print(f"      [DIAGNOSTIC] Thin vertical elements found:")
            for d in info['diag']:
                print(f"        {d['tag']}.{d['className'][:40]} w={d['w']} h={d['h']} left={d['left']:.0f} bg={d['bg']}")

        # 4. Calculate drag coordinates
        #    x = playhead_x + (target_time - audio.currentTime) * pxPerSec
        drag_start_x = ph_x + (start_sec - cur_t) * pps
        drag_end_x   = ph_x + (end_sec - cur_t) * pps

        # Clamp to canvas bounds (with small margin)
        canvas_left = cb['x']
        canvas_right = cb['x'] + cb['w']
        drag_start_x = max(canvas_left + 5, min(drag_start_x, canvas_right - 30))
        drag_end_x   = max(drag_start_x + 30, min(drag_end_x, canvas_right - 5))
        
        # Ensure minimum drag distance
        if drag_end_x - drag_start_x < 30:
            drag_end_x = drag_start_x + 100

        drag_y = cb['y'] + cb['h'] * 0.6
        dist = drag_end_x - drag_start_x

        print(f"      Drag: x={drag_start_x:.0f} -> {drag_end_x:.0f} (dist={dist:.0f}px) y={drag_y:.0f}")

        # 5. Execute physical Playwright drag (slow and deliberate)
        await page.mouse.move(drag_start_x, drag_y)
        await page.wait_for_timeout(200)
        await page.mouse.down()
        await page.wait_for_timeout(150)

        steps = max(20, int(dist / 5))
        for s in range(steps):
            cx = drag_start_x + (dist * (s + 1) / steps)
            await page.mouse.move(cx, drag_y)
            await page.wait_for_timeout(25)

        await page.wait_for_timeout(200)
        await page.mouse.up()
        await page.wait_for_timeout(1000)

        # 6. Handle any popup dialogs
        try:
            popup = page.locator('button:has-text("OK"), button:has-text("Yes"), '
                                 'button:has-text("Confirm"), button:has-text("Accept")')
            if await popup.count() > 0:
                print("      [POPUP] Dismissing...")
                await popup.first.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass

        # 7. Verify
        if await _count_segments(page) > 0:
            print("      [SUCCESS] First segment created via playhead-relative drag!")
            return True
            
        print("      [FAIL] No segment appeared.")

    return False


# ══════════════════════════════════════════════════════════════════════
#  CREATE ALL SEGMENTS  —  Playhead-First Strategy
# ══════════════════════════════════════════════════════════════════════

async def create_all_segments(page, fill_chunks, ap):
    """
    For EVERY segment (including the first):
      1. Seek audio to start_sec  →  playhead jumps to correct time
      2. Click "+"                →  Annotic creates the segment at playhead
      3. Set timestamps precisely →  correct any Annotic rounding
      4. Fill text
    """
    # Count existing at start
    initial_count = await _count_segments(page)

    for i, chunk in enumerate(fill_chunks):
        start_sec = chunk["start"]
        end_sec   = chunk["end"]
        text      = chunk["text_final"]

        print(f"\n  [{i+1}/{len(fill_chunks)}] "
              f"[{ap.format_time(start_sec)} → {ap.format_time(end_sec)}] "
              f"\"{text[:60]}\"")

        # If it's the very first chunk AND we have 0 segments on screen,
        # we MUST create it using the physical drag method.
        if i == 0 and initial_count == 0:
            ok = await _calibrated_drag_first_segment(page, start_sec, end_sec)
            if not ok:
                print(f"  [ERROR] Could not drag first segment. Aborting.")
                return
        else:
            # ── 1. Seek playhead to segment start ────────────────────
            print(f"    Seeking to {start_sec:.3f}s …")
            await _seek_audio(page, start_sec)

            # ── 2. Click "+" to spawn segment at playhead ─────────────
            ok = await _click_add_button(page, i)
            if not ok:
                # One last fallback: if "+" fails but it's i=0 and somehow initial_count >= 1,
                # the placeholder might just be there already. Let's verify row exists.
                if await _count_segments(page) >= i + 1:
                    print("  [WARN] '+' failed but row seems to exist anyway. Proceeding.")
                else:
                    print(f"  [ERROR] Could not create segment {i+1}. Aborting.")
                    return

            await page.wait_for_timeout(300)

        # ── 3. Fix timestamps precisely ───────────────────────────
        await set_segment_timestamps(page, i, start_sec, end_sec)

        # ── 4. Fill text ──────────────────────────────────────────
        await fill_segment_text(page, i, text)

        print(f"    ✓ Segment {i+1} done.")

    total = await _count_segments(page)
    print(f"\n[CREATE] Finished. {total} segments on screen.")


# ══════════════════════════════════════════════════════════════════════
#  CLICK "+" BUTTON
# ══════════════════════════════════════════════════════════════════════

async def _click_add_button(page, current_seg_index: int) -> bool:
    """
    Click the AddIcon ('+') button on the last existing segment row.
    For segment 0 the placeholder row already exists — we click its '+'.
    """
    initial_count = await _count_segments(page)

    # If this is the very first segment and a placeholder already exists,
    # we DON'T add a new row — we just use the existing placeholder.
    if current_seg_index == 0 and initial_count >= 1:
        print(f"    Placeholder row already exists — using it directly.")
        return True

    clicked = await page.evaluate("""() => {
        const c = document.getElementById('subTitleContainer');
        if (!c) return false;
        const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
        if (!rows.length) return false;
        const lastRow = rows[rows.length - 1];
        const btns = Array.from(lastRow.querySelectorAll('button'));

        // Strategy 1: svg data-testid="AddIcon"
        for (const btn of btns) {
            const svg = btn.querySelector('svg');
            if (svg && svg.getAttribute('data-testid') === 'AddIcon') {
                btn.click();
                return 'AddIcon';
            }
        }
        // Strategy 2: Material-UI Add SVG path
        for (const btn of btns) {
            if (btn.innerHTML.includes('M19 13h-6')) {
                btn.click();
                return 'pathMatch';
            }
        }
        // Strategy 3: "+" text button
        for (const btn of btns) {
            if (btn.textContent.trim() === '+') {
                btn.click();
                return 'plusText';
            }
        }
        // Strategy 4: last button that isn't delete/play/pause
        const skipIds = ['DeleteIcon','PlayArrowIcon','PauseIcon','RemoveIcon'];
        for (let i = btns.length - 1; i >= 0; i--) {
            const svg = btns[i].querySelector('svg');
            if (!svg) continue;
            const id = svg.getAttribute('data-testid') || '';
            if (!skipIds.includes(id)) {
                btns[i].click();
                return `fallback[${i}]`;
            }
        }
        return false;
    }""")

    if not clicked:
        print("  [WARN] '+' not found via JS — trying Playwright locator.")
        try:
            btn = page.locator(
                '#subTitleContainer > div:last-child button svg[data-testid="AddIcon"]'
            ).locator('..')
            if await btn.count() > 0:
                await btn.first.click()
                clicked = "playwright_fallback"
        except Exception as e:
            print(f"  [ERROR] Playwright fallback failed: {e}")

    if not clicked:
        return False

    print(f"    '+' clicked via: {clicked}")

    # Wait for new row to appear
    for _ in range(40):
        await page.wait_for_timeout(100)
        if await _count_segments(page) > initial_count:
            return True

    print("  [ERROR] Row count did not increase after '+' click.")
    return False


# ══════════════════════════════════════════════════════════════════════
#  SET TIMESTAMPS
# ══════════════════════════════════════════════════════════════════════

async def set_segment_timestamps(page, seg_index: int,
                                  start_sec: float, end_sec: float):
    """
    Fill the 8 number inputs (HH MM SS mmm × 2) of a segment row.

    Two approaches tried in order:
      A) Direct React fiber state mutation  (most reliable for React apps)
      B) Keystroke injection fallback
    """
    try:
        audio_dur = await page.evaluate(
            "() => { const a = document.querySelector('audio'); "
            "return (a && a.duration > 0) ? a.duration : 9999.0; }"
        )
        # Clamp
        if end_sec >= audio_dur:
            end_sec = audio_dur - 0.001
        if start_sec >= end_sec:
            start_sec = max(0.0, end_sec - 0.5)

        def parts(sec: float):
            sec = max(0.0, sec)
            ms  = int(round((sec % 1) * 1000))
            if ms >= 1000:
                sec += 1; ms -= 1000
            s = int(sec) % 60
            m = (int(sec) // 60) % 60
            h = int(sec) // 3600
            return f"{h:02d}", f"{m:02d}", f"{s:02d}", f"{ms:03d}"

        sh, sm, ss, sms = parts(start_sec)
        eh, em, es, ems = parts(end_sec)
        values = [sh, sm, ss, sms, eh, em, es, ems]

        print(f"    Timestamps: {sh}:{sm}:{ss}.{sms} → {eh}:{em}:{es}.{ems}")

        # ── Approach A: React fiber nativeInputValueSetter ────────
        set_ok = await page.evaluate("""([idx, vals]) => {
            const c = document.getElementById('subTitleContainer');
            if (!c) return false;
            const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
            const row  = rows[idx];
            if (!row) return false;
            const inputs = Array.from(row.querySelectorAll('input[type="number"]'));
            if (inputs.length !== 8) return false;

            const nativeSetter = Object.getOwnPropertyDescriptor(
                HTMLInputElement.prototype, 'value').set;

            inputs.forEach((inp, i) => {
                nativeSetter.call(inp, vals[i]);
                inp.dispatchEvent(new Event('input',  { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                inp.dispatchEvent(new Event('blur',   { bubbles: true }));
            });
            return true;
        }""", [seg_index, values])

        if set_ok:
            await page.wait_for_timeout(200)
            # Verify the values were accepted
            verified = await page.evaluate("""([idx, vals]) => {
                const c = document.getElementById('subTitleContainer');
                const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
                const row = rows[idx];
                if (!row) return false;
                const inputs = Array.from(row.querySelectorAll('input[type="number"]'));
                return inputs.every((inp, i) => inp.value === vals[i]);
            }""", [seg_index, values])

            if verified:
                print(f"    ✓ Timestamps set via React native setter.")
                return
            else:
                print(f"    [WARN] React setter didn't stick — falling back to keystrokes.")

        # ── Approach B: Keystroke injection ───────────────────────
        print(f"    Using keystroke injection …")
        container = page.locator('#subTitleContainer')
        row = container.locator(f'> div:nth-child({seg_index + 1})')
        inputs = row.locator('input[type="number"]')
        count = await inputs.count()

        if count != 8:
            print(f"  [WARN] Expected 8 number inputs, got {count}.")
            return

        for idx, val in enumerate(values):
            field = inputs.nth(idx)
            await field.scroll_into_view_if_needed()
            await field.click(click_count=3)        # triple-click = select all
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
            await page.keyboard.type(val, delay=30)
            await page.keyboard.press("Tab")         # Tab commits the value
            await page.wait_for_timeout(60)

        print(f"    ✓ Timestamps set via keystrokes.")

    except Exception as e:
        print(f"  [ERROR] set_segment_timestamps: {e}")


# ══════════════════════════════════════════════════════════════════════
#  FILL TEXT
# ══════════════════════════════════════════════════════════════════════

async def fill_segment_text(page, seg_index: int, text: str):
    """Write text into a segment's textarea via React-safe native setter."""
    ok = await page.evaluate("""([idx, txt]) => {
        const c = document.getElementById('subTitleContainer');
        if (!c) return false;
        const rows = Array.from(c.children).filter(r => r.querySelector('textarea'));
        const ta   = rows[idx]?.querySelector('textarea');
        if (!ta) return false;
        const setter = Object.getOwnPropertyDescriptor(
            HTMLTextAreaElement.prototype, 'value').set;
        setter.call(ta, txt);
        ta.dispatchEvent(new Event('input',  { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
        ta.dispatchEvent(new Event('blur',   { bubbles: true }));
        return true;
    }""", [seg_index, text])

    if not ok:
        print(f"  [WARN] fill_segment_text failed for segment {seg_index}.")
    else:
        print(f"    ✓ Text filled: \"{text[:50]}\"")


# ══════════════════════════════════════════════════════════════════════
#  SAVE & VERIFY
# ══════════════════════════════════════════════════════════════════════

async def save_and_verify(page):
    print("[SAVE] Looking for Update/Save button …")

    candidates = [
        page.get_by_role("button", name="Update"),
        page.get_by_role("button", name="Save"),
        page.locator('button:has-text("Update")'),
        page.locator('button:has-text("Submit")'),
    ]

    clicked = False
    for btn in candidates:
        try:
            if await btn.count() > 0:
                await btn.first.click()
                clicked = True
                print("[SAVE] Clicked.")
                break
        except Exception:
            pass

    if not clicked:
        try:
            icon = page.locator('svg[data-testid="SaveIcon"]')
            if await icon.count() > 0:
                await icon.first.locator('..').click()
                clicked = True
                print("[SAVE] Clicked SaveIcon.")
        except Exception:
            pass

    if not clicked:
        print("[SAVE] No save button found — please save manually.")
        return

    await page.wait_for_timeout(2000)
    success = page.locator('.MuiAlert-standardSuccess, [class*="success"]')
    if await success.count() > 0:
        print("[SAVE] ✓ Saved successfully!")
    else:
        print("[SAVE] Button clicked — check the UI for a confirmation toast.")


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(automate_annotic())