import asyncio
from playwright.async_api import async_playwright
import config
import os

async def extract_dom():
    print("Starting DOM Extractor...")
    
    async with async_playwright() as p:
        user_data_dir = "./playwright_session"
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir, 
            headless=config.HEADLESS_MODE,
            args=["--start-maximized"]
        )
        page = await browser.new_page()

        print(f"Navigating to {config.ANNOTIC_TASK_URL}")
        await page.goto(config.ANNOTIC_TASK_URL)
        
        try:
            await page.wait_for_selector("text=Task #", timeout=15000)
            print("Successfully reached the transcription task page.")
            await page.wait_for_timeout(5000) # Wait for segments to load
            
            # Save the entire DOM
            html = await page.content()
            with open("dom.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("DOM successfully saved to dom.html. You can close the browser now.")
        except Exception as e:
            print(f"Error: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(extract_dom())
