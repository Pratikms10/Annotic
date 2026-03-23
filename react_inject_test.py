"""
react_inject_test.py — directly inject segment rows into Annotic by
walking the React fiber tree and triggering the internal state dispatcher.
"""
import asyncio
import config
from playwright.async_api import async_playwright

INJECT_JS = """
() => {
    // ============================================================
    // PHASE 1: Enable WaveSurfer in settings (click the gear, check the box)
    // ============================================================
    
    // ============================================================
    // PHASE 2: Walk the React Fiber tree to find the component
    //          that manages the #subTitleContainer state
    // ============================================================
    const container = document.getElementById('subTitleContainer');
    if (!container) return { error: 'No #subTitleContainer found' };
    
    // Find the React Fiber key  
    const fiberKey = Object.keys(container).find(k => 
        k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$')
    );
    if (!fiberKey) return { error: 'No React Fiber found on #subTitleContainer' };
    
    let fiber = container[fiberKey];
    let results = [];
    let depth = 0;
    let foundDispatcher = null;
    let foundSetState = null;
    
    // Walk UP the fiber tree (toward root) looking for state with segment data
    while (fiber && depth < 30) {
        let info = {
            depth: depth,
            type: 'unknown',
            hasState: false,
            stateKeys: [],
            hasFunctions: false,
            functionNames: []
        };
        
        // Get component name
        if (fiber.type) {
            if (typeof fiber.type === 'string') {
                info.type = fiber.type;
            } else if (fiber.type.name) {
                info.type = fiber.type.name;
            } else if (fiber.type.displayName) {
                info.type = fiber.type.displayName;
            } else {
                info.type = 'Anonymous';
            }
        }
        
        // Check memoizedProps for relevant data
        if (fiber.memoizedProps) {
            const pKeys = Object.keys(fiber.memoizedProps);
            info.propKeys = pKeys.slice(0, 20);
            
            // Look for functions that add segments
            pKeys.forEach(k => {
                const val = fiber.memoizedProps[k];
                if (typeof val === 'function') {
                    info.hasFunctions = true;
                    info.functionNames.push(k);
                }
                // Look for arrays that might be segment data
                if (Array.isArray(val) && val.length >= 0) {
                    if (val.length > 0 && val[0] && (val[0].start !== undefined || val[0].text !== undefined || val[0].startTime !== undefined)) {
                        info.segmentArrayKey = k;
                        info.segmentCount = val.length;
                        info.sampleSegment = JSON.stringify(val[0]).substring(0, 200);
                    }
                }
            });
        }
        
        // Check memoizedState for hooks
        if (fiber.memoizedState) {
            info.hasState = true;
            let state = fiber.memoizedState;
            let hookIdx = 0;
            while (state && hookIdx < 20) {
                let ms = state.memoizedState;
                if (ms !== null && ms !== undefined) {
                    if (Array.isArray(ms)) {
                        // Could be a useState with array value (segments!)
                        if (ms.length > 0 && typeof ms[0] === 'object' && ms[0] !== null) {
                            const sample = ms[0];
                            if (sample.start !== undefined || sample.text !== undefined || sample.startTime !== undefined) {
                                info.stateKeys.push(`hook[${hookIdx}]: SEGMENTS ARRAY! count=${ms.length}`);
                                foundDispatcher = {depth, hookIdx, fiber: fiber};
                            }
                        }
                    } else if (typeof ms === 'object' && ms !== null && !ms.current) {
                        const keys = Object.keys(ms).slice(0, 10);
                        if (keys.length > 0) {
                            info.stateKeys.push(`hook[${hookIdx}]: object with keys ${keys.join(',')}`);
                        }
                        // Check if this object has segment-like data
                        if (ms.subtitles || ms.segments || ms.regions || ms.annotations) {
                            info.stateKeys.push(`hook[${hookIdx}]: HAS SUBTITLE/SEGMENT DATA!`);
                            foundDispatcher = {depth, hookIdx, fiber: fiber, key: Object.keys(ms).find(k => ['subtitles','segments','regions','annotations'].includes(k))};
                        }
                    } else if (typeof ms === 'function') {
                        info.stateKeys.push(`hook[${hookIdx}]: FUNCTION (likely dispatcher)`);
                    }
                }
                
                // Check queue for dispatch function
                if (state.queue && state.queue.dispatch) {
                    info.stateKeys.push(`hook[${hookIdx}]: HAS DISPATCH! (setState equivalent)`);
                    if (!foundSetState) {
                        foundSetState = {depth, hookIdx, dispatch: state.queue.dispatch, state: state};
                    }
                }
                
                state = state.next;
                hookIdx++;
            }
        }
        
        results.push(info);
        fiber = fiber.return;
        depth++;
    }
    
    return {
        totalDepth: depth,
        fiberTree: results.filter(r => r.hasFunctions || r.hasState || r.stateKeys.length > 0),
        foundDispatcher: foundDispatcher ? { depth: foundDispatcher.depth, hookIdx: foundDispatcher.hookIdx } : null,
        foundSetState: foundSetState ? { depth: foundSetState.depth, hookIdx: foundSetState.hookIdx } : null
    };
}
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=None,
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        # Copy cookies from persistent session to this context
        import glob, json as jsonmod
        cookie_files = glob.glob(config.PLAYWRIGHT_SESSION_DIR + "/**/Cookies", recursive=True)
        print(f"Looking for cookies in {config.PLAYWRIGHT_SESSION_DIR}... found {len(cookie_files)} files")

        try:
            print(f"Navigating to {config.ANNOTIC_TASK_URL}...")
            await page.goto(config.ANNOTIC_TASK_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)
            
            # First enable WaveSurfer via Settings gear
            print("\n--- Enabling WaveSurfer in Settings ---")
            gear = page.locator('button').filter(has=page.locator('svg')).nth(1)  # Settings is 2nd icon
            # Actually just use the evaluate to check and enable
            await page.evaluate("""() => {
                // Find the settings gear and click it
                const btns = Array.from(document.querySelectorAll('button'));
                const settingsBtn = btns.find(b => {
                    const svg = b.querySelector('svg path');
                    return svg && svg.getAttribute('d') && svg.getAttribute('d').includes('19.14');
                });
                if (settingsBtn) settingsBtn.click();
            }""")
            await page.wait_for_timeout(1000)
            
            print("\n--- Walking React Fiber Tree ---")
            result = await page.evaluate(INJECT_JS)
            
            import json
            print(json.dumps(result, indent=2, default=str))
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
