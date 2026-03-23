"""
probe_ui.py — Opens Annotic HEADFUL and systematically tries EVERY interaction
to discover what actually creates a segment placeholder row.
"""
import asyncio
import config
from playwright.async_api import async_playwright

async def count_segments(page):
    """Count actual segment rows in #subTitleContainer."""
    return await page.evaluate("""() => {
        const c = document.getElementById('subTitleContainer');
        if (!c) return -1;
        return c.children.length;
    }""")

async def dump_all_buttons(page):
    """List every button on the page with its text and aria-label."""
    return await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button'));
        return btns.map(b => ({
            text: b.textContent.trim().substring(0, 50),
            ariaLabel: b.getAttribute('aria-label') || '',
            title: b.getAttribute('title') || '',
            classes: b.className.substring(0, 80),
            visible: b.offsetParent !== null,
            rect: b.getBoundingClientRect()
        }));
    }""")

async def dump_clickable_svgs(page):
    """Find all clickable SVG icons (often used for add/plus buttons)."""
    return await page.evaluate("""() => {
        const svgs = Array.from(document.querySelectorAll('svg'));
        return svgs.filter(s => {
            const parent = s.closest('button, [role="button"], a, [onclick]');
            return parent !== null;
        }).map(s => {
            const parent = s.closest('button, [role="button"], a, [onclick]');
            const paths = Array.from(s.querySelectorAll('path')).map(p => p.getAttribute('d')?.substring(0, 40));
            return {
                parentTag: parent.tagName,
                parentText: parent.textContent.trim().substring(0, 30),
                paths: paths,
                visible: parent.offsetParent !== null,
                rect: parent.getBoundingClientRect()
            };
        });
    }""")

async def dump_waveform_structure(page):
    """Dump the structure around the waveform to understand what elements exist."""
    return await page.evaluate("""() => {
        const canvases = Array.from(document.querySelectorAll('canvas'));
        let info = [];
        canvases.forEach((c, i) => {
            const parent = c.parentElement;
            const grandparent = parent ? parent.parentElement : null;
            info.push({
                index: i,
                canvasSize: `${c.width}x${c.height}`,
                parentTag: parent ? parent.tagName : 'none',
                parentClass: parent ? parent.className.substring(0, 60) : 'none',
                grandparentTag: grandparent ? grandparent.tagName : 'none',
                grandparentClass: grandparent ? grandparent.className.substring(0, 60) : 'none',
                siblings: parent ? Array.from(parent.children).map(c => c.tagName).join(', ') : 'none'
            });
        });
        return info;
    }""")

async def try_interaction(page, name, action_fn):
    """Try an interaction and check if segments changed."""
    before = await count_segments(page)
    print(f"\n  [{name}] Segments before: {before}")
    try:
        await action_fn()
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  [{name}] Error: {e}")
    after = await count_segments(page)
    print(f"  [{name}] Segments after: {after}")
    if after > before:
        print(f"  *** SUCCESS! '{name}' created a segment! ***")
        return True
    return False

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=config.PLAYWRIGHT_SESSION_DIR,
            headless=True,  # Headless to avoid Chrome profile lock
            no_viewport=True
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        try:
            print(f"Navigating to {config.ANNOTIC_TASK_URL}...")
            await page.goto(config.ANNOTIC_TASK_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)
            
            # ========== PHASE 1: DUMP UI STRUCTURE ==========
            print("\n" + "="*60)
            print("PHASE 1: UNDERSTANDING THE UI")
            print("="*60)
            
            seg_count = await count_segments(page)
            print(f"\nCurrent segment count: {seg_count}")
            
            print("\n--- All Buttons ---")
            buttons = await dump_all_buttons(page)
            for b in buttons:
                if b['visible']:
                    print(f"  Button: '{b['text']}' | aria='{b['ariaLabel']}' | title='{b['title']}' | pos=({b['rect']['x']:.0f},{b['rect']['y']:.0f})")
            
            print("\n--- Clickable SVG Icons ---")
            svgs = await dump_clickable_svgs(page)
            for s in svgs:
                if s['visible']:
                    print(f"  SVG in <{s['parentTag']}>: '{s['parentText']}' | paths={s['paths']} | pos=({s['rect']['x']:.0f},{s['rect']['y']:.0f})")
            
            print("\n--- Waveform Structure ---")
            wave_info = await dump_waveform_structure(page)
            for w in wave_info:
                print(f"  Canvas {w['index']}: {w['canvasSize']} | parent=<{w['parentTag']} class='{w['parentClass']}'> | siblings={w['siblings']}")
            
            # ========== PHASE 2: FIND THE WAVEFORM REGION CONTAINER ==========
            print("\n" + "="*60)
            print("PHASE 2: FINDING WAVESURFER REGIONS")
            print("="*60)
            
            regions_info = await page.evaluate("""() => {
                // WaveSurfer stores regions in a specific container
                const regionEls = document.querySelectorAll('[data-id], .wavesurfer-region, [class*="region"]');
                let info = [];
                regionEls.forEach(r => {
                    info.push({
                        tag: r.tagName,
                        class: r.className.substring(0, 80),
                        dataId: r.getAttribute('data-id'),
                        style: r.style.cssText.substring(0, 100)
                    });
                });
                
                // Also check window for WaveSurfer instance
                let wsFound = false;
                let wsKeys = [];
                for (let key of Object.keys(window)) {
                    if (key.toLowerCase().includes('wave') || key.toLowerCase().includes('surfer') || key.toLowerCase().includes('region')) {
                        wsKeys.push(key);
                        wsFound = true;
                    }
                }
                
                return { regions: info, wavesurferKeys: wsKeys, wsFound };
            }""")
            print(f"  WaveSurfer global vars: {regions_info['wavesurferKeys']}")
            print(f"  Region elements found: {len(regions_info['regions'])}")
            for r in regions_info['regions'][:5]:
                print(f"    <{r['tag']} class='{r['class']}' data-id='{r['dataId']}'>")
            
            # ========== PHASE 3: TRY EVERY INTERACTION ==========
            print("\n" + "="*60)
            print("PHASE 3: TRYING EVERY POSSIBLE INTERACTION")
            print("="*60)
            
            canvas = page.locator('canvas').first
            box = await canvas.bounding_box()
            if not box:
                print("ERROR: No canvas bounding box!")
                return
            
            cx = box['x'] + box['width'] * 0.5
            cy = box['y'] + box['height'] * 0.5
            
            # Test 1: Double-click on waveform
            success = await try_interaction(page, "DOUBLE-CLICK on waveform", 
                lambda: page.mouse.dblclick(cx, cy))
            if success: print(">>> DOUBLE-CLICK WORKS! <<<")
            
            # Test 2: Right-click on waveform
            success = await try_interaction(page, "RIGHT-CLICK on waveform",
                lambda: page.mouse.click(cx, cy, button="right"))
            if success: print(">>> RIGHT-CLICK WORKS! <<<")
            
            # Test 3: Single click on waveform
            success = await try_interaction(page, "SINGLE-CLICK on waveform",
                lambda: page.mouse.click(cx, cy))
            if success: print(">>> SINGLE-CLICK WORKS! <<<")
            
            # Test 4: Drag on the PARENT div of the canvas (not the canvas itself)
            parent_box = await page.evaluate("""() => {
                const c = document.querySelector('canvas');
                const p = c ? c.parentElement : null;
                if (!p) return null;
                const r = p.getBoundingClientRect();
                return { x: r.x, y: r.y, width: r.width, height: r.height, tag: p.tagName, cls: p.className };
            }""")
            if parent_box:
                print(f"\n  Canvas parent: <{parent_box['tag']} class='{parent_box['cls'][:50]}'>")
                px = parent_box['x'] + parent_box['width'] * 0.3
                py = parent_box['y'] + parent_box['height'] * 0.5
                
                async def drag_parent():
                    await page.mouse.move(px, py)
                    await page.mouse.down()
                    await page.wait_for_timeout(500)
                    await page.mouse.move(px + 100, py, steps=20)
                    await page.wait_for_timeout(300)
                    await page.mouse.up()
                
                success = await try_interaction(page, "DRAG on canvas PARENT", drag_parent)
                if success: print(">>> DRAG ON PARENT WORKS! <<<")
            
            # Test 5: Look for any "region" or "handle" overlay
            print("\n--- Looking for region overlays to click ---")
            overlay_info = await page.evaluate("""() => {
                // Find any absolutely positioned divs near the waveform
                const canv = document.querySelector('canvas');
                if (!canv) return [];
                const parent = canv.closest('[class*="wave"], [id*="wave"]') || canv.parentElement.parentElement;
                if (!parent) return [];
                const allDivs = Array.from(parent.querySelectorAll('div'));
                return allDivs.filter(d => {
                    const style = window.getComputedStyle(d);
                    return style.position === 'absolute' || style.position === 'relative';
                }).map(d => ({
                    tag: d.tagName,
                    class: d.className.substring(0, 80), 
                    id: d.id,
                    style: `pos:${window.getComputedStyle(d).position} w:${d.offsetWidth} h:${d.offsetHeight}`,
                    rect: d.getBoundingClientRect()
                })).slice(0, 15);
            }""")
            for ov in overlay_info:
                print(f"  <div class='{ov['class']}' id='{ov['id']}'> {ov['style']} pos=({ov['rect']['x']:.0f},{ov['rect']['y']:.0f})")
            
            # Test 6: Click on a waveform region if one exists
            region_el = page.locator('.wavesurfer-region, [data-id]').first
            if await region_el.count() > 0:
                region_box = await region_el.bounding_box()
                if region_box:
                    rx = region_box['x'] + region_box['width'] * 0.5
                    ry = region_box['y'] + region_box['height'] * 0.5
                    
                    success = await try_interaction(page, "DOUBLE-CLICK on existing region",
                        lambda: page.mouse.dblclick(rx, ry))
                    if success: print(">>> DOUBLE-CLICK ON REGION WORKS! <<<")
            
            # Test 7: Check if there's a timeline bar ABOVE the waveform (different from canvas)
            print("\n--- Looking for timeline bar elements ---")
            timeline_info = await page.evaluate("""() => {
                const canv = document.querySelector('canvas');
                if (!canv) return 'no canvas';
                // Go up several levels to find the full waveform container
                let container = canv;
                for (let i = 0; i < 5; i++) {
                    container = container.parentElement;
                    if (!container) break;
                }
                if (!container) return 'no container';
                
                // Find ALL children of this big container
                const children = Array.from(container.querySelectorAll('*'));
                return children.filter(c => {
                    const r = c.getBoundingClientRect();
                    return r.height > 5 && r.height < 50 && r.width > 200;
                }).map(c => ({
                    tag: c.tagName,
                    class: c.className.substring(0, 60),
                    rect: c.getBoundingClientRect(),
                    listeners: c.onclick ? 'has onclick' : 'no onclick'
                })).slice(0, 10);
            }""")
            print(f"  Timeline bars: {timeline_info}")

            # Test 8: Try drag on the TIMELINE BAR (the thin strip with time labels)
            timeline_strip = await page.evaluate("""() => {
                // The timeline is typically a thin horizontal bar with time labels
                const allDivs = Array.from(document.querySelectorAll('div, canvas'));
                // Find element that contains time text like "00:01:20"
                for (const d of allDivs) {
                    const text = d.textContent || '';
                    if (/\d{2}:\d{2}:\d{2}/.test(text) && d.offsetHeight < 40 && d.offsetWidth > 200) {
                        const r = d.getBoundingClientRect();
                        return { x: r.x, y: r.y, width: r.width, height: r.height, tag: d.tagName, class: d.className.substring(0, 60) };
                    }
                }
                return null;
            }""")
            if timeline_strip:
                print(f"\n  Timeline strip: <{timeline_strip['tag']} class='{timeline_strip.get('class', '')}'> at ({timeline_strip['x']:.0f},{timeline_strip['y']:.0f})")
                tx = timeline_strip['x'] + timeline_strip['width'] * 0.3
                ty = timeline_strip['y'] + timeline_strip['height'] * 0.5
                
                async def drag_timeline():
                    await page.mouse.move(tx, ty)
                    await page.mouse.down()
                    await page.wait_for_timeout(500)
                    await page.mouse.move(tx + 100, ty, steps=20)
                    await page.wait_for_timeout(300)
                    await page.mouse.up()
                
                success = await try_interaction(page, "DRAG on TIMELINE strip", drag_timeline)
                if success: print(">>> DRAG ON TIMELINE WORKS! <<<")
            
            # Test 9: Try ABOVE the waveform (maybe there's a hidden overlay)
            above_y = box['y'] - 20  # Just above the canvas
            async def drag_above():
                await page.mouse.move(cx, above_y)
                await page.mouse.down()
                await page.wait_for_timeout(500)
                await page.mouse.move(cx + 100, above_y, steps=20)
                await page.wait_for_timeout(300)
                await page.mouse.up()
            
            success = await try_interaction(page, "DRAG ABOVE waveform", drag_above)
            if success: print(">>> DRAG ABOVE WORKS! <<<")
            
            # Test 10: SLOW drag on canvas with bigger distance
            async def slow_big_drag():
                sx = box['x'] + box['width'] * 0.2
                ex = box['x'] + box['width'] * 0.6
                y = box['y'] + box['height'] * 0.5
                await page.mouse.move(sx, y)
                await page.wait_for_timeout(200)
                await page.mouse.down()
                await page.wait_for_timeout(500)
                # Very slow drag
                for step in range(40):
                    ix = sx + (ex - sx) * (step / 40)
                    await page.mouse.move(ix, y)
                    await page.wait_for_timeout(50)
                await page.wait_for_timeout(500)
                await page.mouse.up()
                
            success = await try_interaction(page, "VERY SLOW BIG DRAG on canvas", slow_big_drag)
            if success: print(">>> SLOW BIG DRAG WORKS! <<<")
            
            print("\n" + "="*60)
            print("PROBE COMPLETE.")
            await page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"FATAL Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
