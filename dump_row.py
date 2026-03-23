import asyncio
import os
from playwright.async_api import async_playwright
import config

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
            
            # Wait for container
            container = page.locator('#subTitleContainer')
            await container.wait_for(state='visible', timeout=15000)
            
            # Get first row HTML
            row = container.locator('> div').first
            html = await row.evaluate("el => el.outerHTML")
            
            with open("row_dump.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Successfully dumped row HTML to row_dump.html")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
