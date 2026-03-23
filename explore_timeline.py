import asyncio
import json
import config
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=config.PLAYWRIGHT_SESSION_DIR,
            headless=True,
            no_viewport=True
        )
        page = await browser.new_page()
        try:
            print(f"Navigating to {config.ANNOTIC_TASK_URL}...")
            await page.goto(config.ANNOTIC_TASK_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)
            
            print("\n--- Examining Window Variables ---")
            vars = await page.evaluate("""() => {
                let keys = Object.keys(window).filter(k => k.toLowerCase().includes('wave') || k.toLowerCase().includes('surfer') || k.toLowerCase().includes('audio') || k.toLowerCase().includes('region'));
                return keys;
            }""")
            print(f"Window Audio/Wave variables: {vars}")

            print("\n--- Examining React Fiber on Container ---")
            fiber_info = await page.evaluate("""() => {
                const c = document.getElementById('subTitleContainer') || document.querySelector('canvas');
                if (!c) return "No SubTitleContainer or canvas!";
                
                const key = Object.keys(c).find(k => k.startsWith('__reactFiber$'));
                if (!key) return "No React Fiber found on element.";
                
                let fiber = c[key];
                let out = [];
                let depth = 0;
                while (fiber && depth < 5) {
                    let name = fiber.type ? (typeof fiber.type === 'string' ? fiber.type : fiber.type.name || 'AnonymousComponent') : 'Unknown';
                    out.push(`Depth ${depth}: ${name}`);
                    
                    // Look for interesting props
                    if (fiber.memoizedProps) {
                        const pKeys = Object.keys(fiber.memoizedProps).filter(k => typeof fiber.memoizedProps[k] === 'function');
                        if (pKeys.length > 0) {
                            out.push(`  Functions: ${pKeys.join(', ')}`);
                        }
                        
                        // Check for region or audio props
                        const stateKeys = Object.keys(fiber.memoizedProps).filter(k => typeof fiber.memoizedProps[k] === 'object');
                        if (stateKeys.length > 0) {
                             out.push(`  Objects: ${stateKeys.join(', ')}`);
                        }
                    }
                    fiber = fiber.return;
                    depth++;
                }
                return out.join('\\n');
            }""")
            print(fiber_info)

            print("\n--- Finding Audio Scale and Duration ---")
            audio_info = await page.evaluate("""() => {
                const a = document.querySelector('audio');
                if (!a) return "No audio element";
                return `Duration: ${a.duration}, CurrentTime: ${a.currentTime}`;
            }""")
            print(audio_info)
            
            print("\n--- Testing Seek and Playhead Offset ---")
            # Set time to 60s
            await page.evaluate("() => { const a = document.querySelector('audio'); if(a) a.currentTime = 60.0; }")
            await page.wait_for_timeout(1000)
            
            playhead_info = await page.evaluate("""() => {
                const wave = document.querySelector('wave wave');
                const canvas = document.querySelector('canvas');
                let info = [];
                if (wave) info.push(`Wave width (playhead x): ${wave.offsetWidth}px`);
                if (canvas) {
                     const box = canvas.getBoundingClientRect();
                     info.push(`Canvas width: ${box.width}px`);
                }
                // Look for common cursor elements
                const cursor = document.querySelector('.cursor, .wavesurfer-cursor');
                if (cursor) {
                     const cbox = cursor.getBoundingClientRect();
                     info.push(`Cursor X: ${cbox.x}px`);
                }
                return info.join(' | ');
            }""")
            print(playhead_info)

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
