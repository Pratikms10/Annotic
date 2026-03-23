import asyncio
import config
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=config.PLAYWRIGHT_SESSION_DIR,
            headless=False, # Show the browser so the user sees what's happening
            no_viewport=True
        )
        page = await browser.new_page()
        try:
            print(f"Navigating to {config.ANNOTIC_TASK_URL}...")
            await page.goto(config.ANNOTIC_TASK_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)
            
            container = page.locator('#subTitleContainer')
            
            # Wipe starting segments if any
            while await container.locator('> div').count() > 0:
                print("Clearing existing segments first...")
                await page.evaluate("""() => {
                    const c = document.getElementById('subTitleContainer');
                    if(c && c.children.length > 0) {
                        const last = c.children[c.children.length-1];
                        const delBtn = last.querySelector('button[title*="Delete"], button[aria-label*="Delete"]');
                        if (delBtn) delBtn.click();
                    }
                }""")
                await page.wait_for_timeout(1000)
                
            # Find the best target
            target = page.locator('#waveform, .waveform, [data-testid="waveform"]').first
            if await target.count() == 0:
                print("Could not find #waveform, targeting first canvas wrapper.")
                target = page.locator('canvas').first.locator('..')
                
            box = await target.bounding_box()
            if not box:
                print("No bounding box for target.")
                return
                
            y = box['y'] + (box['height'] * 0.5)
            start_x = box['x'] + (box['width'] * 0.4)
            end_x = start_x + 200
            
            strategies = [
                ("Normal Drag", []),
                ("Shift + Drag", ["Shift"]),
                ("Control + Drag", ["Control"]),
                ("Alt + Drag", ["Alt"]),
            ]
            
            for name, modifiers in strategies:
                print(f"\\n--- Trying: {name} ---")
                
                for mod in modifiers:
                    await page.keyboard.down(mod)
                
                await page.mouse.move(start_x, y)
                await page.mouse.down()
                await page.mouse.move(end_x, y, steps=20)
                await page.mouse.up()
                
                for mod in modifiers:
                    await page.keyboard.up(mod)
                    
                await page.wait_for_timeout(1000)
                
                if await container.locator('> div').count() > 0:
                    print(f">>> SUCCESS! '{name}' successfully created a segment!")
                    return
                else:
                    print(f"FAILED: '{name}' did not create a segment.")
                    
            print("\\nAll strategies failed to create a segment through drag.")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
