import asyncio
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
            
            print("Looking for waveform canvas or container...")
            # Usually wavesurfer uses a canvas inside a specific div
            # Just look for the first canvas tag
            canvas = page.locator('canvas').first
            if await canvas.count() > 0:
                box = await canvas.bounding_box()
                if box:
                    print(f"Found canvas bounding box: {box}")
                    
                    # Try a dummy drag from 10% to 20% of the canvas
                    start_x = box['x'] + (box['width'] * 0.1)
                    end_x = box['x'] + (box['width'] * 0.2)
                    y = box['y'] + (box['height'] / 2)
                    
                    # Count rows before drag
                    container = page.locator('#subTitleContainer')
                    rows_before = await container.locator('> div').count()
                    print(f"Rows before drag: {rows_before}")
                    
                    # Perform drag
                    print(f"Simulating mouse drag from X:{start_x} to X:{end_x}...")
                    await page.mouse.move(start_x, y)
                    await page.mouse.down()
                    await page.mouse.move(end_x, y, steps=10)
                    await page.mouse.up()
                    
                    await page.wait_for_timeout(2000)
                    
                    # Count rows after drag
                    rows_after = await container.locator('> div').count()
                    print(f"Rows after drag: {rows_after}")
                    
                    if rows_after > rows_before:
                        print("SUCCESS! Mouse drag created a new segment placeholder natively!")
                    else:
                        print("FAILED. Dragging didn't create a segment, or coordinates were wrong.")
                else:
                    print("Could not get bounding box for canvas.")
            else:
                print("No <canvas> found on page. It might use divs for the waveform.")
                # Print all divs with obvious waveform sounding classes
                print("Checking for waveform divs...")
                divs = await page.evaluate("() => Array.from(document.querySelectorAll('div')).map(d => d.className).filter(c => typeof c === 'string' && c.toLowerCase().includes('wave'))")
                print(f"Waveform divs found: {list(set(divs))}")
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
