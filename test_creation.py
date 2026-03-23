import sys
sys.stdout = open('test_creation.log', 'w')
sys.stderr = sys.stdout

import asyncio
import config
from playwright.async_api import async_playwright
from annotic_automator import click_add_segment

async def main():
    print("STARTING TEST SCRIPT...", flush=True)
    async with async_playwright() as p:
        print("LAUNCHING PLAYWRIGHT...", flush=True)
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=config.PLAYWRIGHT_SESSION_DIR,
            headless=True,
            no_viewport=True
        )
        print("BROWSER LAUNCHED SUCCESS.", flush=True)

        page = await browser.new_page()
        try:
            print(f"Navigating to {config.ANNOTIC_TASK_URL}...")
            await page.goto(config.ANNOTIC_TASK_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)
            
            # Wipe starting segments
            container = page.locator('#subTitleContainer')
            
            print("\n--- Testing Button Workflow ---")
            for i in range(5):
                print(f"Adding segment {i+1}...")
                success = await click_add_segment(page, is_first=(i==0))
                print(f"Success: {success}.")
                await page.wait_for_timeout(1000)
                count = await container.locator('> div').count()
                print(f"Current DOM rows: {count}")
                
            print("\nDONE.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
