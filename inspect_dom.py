"""Quick DOM inspection script — runs with existing Playwright session."""
import asyncio
from playwright.async_api import async_playwright
import config
import json

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            config.PLAYWRIGHT_SESSION_DIR,
            headless=False,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto(config.ANNOTIC_TASK_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # First, click the "+" button on the first row to reveal controls
        print("=== Clicking '+' to reveal controls ===")
        click_result = await page.evaluate("""
        () => {
            const container = document.getElementById('subTitleContainer');
            if (!container) return 'NO CONTAINER';
            const rows = Array.from(container.children);
            for (const row of rows) {
                const buttons = row.querySelectorAll('button, [role="button"]');
                for (const btn of buttons) {
                    if (btn.textContent.trim() === '+') {
                        btn.click();
                        return 'Clicked + with text';
                    }
                }
            }
            // Try SVG-based + button
            for (const row of rows) {
                const buttons = row.querySelectorAll('button, [role="button"]');
                for (const btn of buttons) {
                    const svg = btn.querySelector('svg');
                    if (svg && btn.innerHTML.includes('Add')) {
                        btn.click();
                        return 'Clicked + via SVG';
                    }
                }
            }
            return 'NO + FOUND';
        }
        """)
        print(f"Result: {click_result}")
        await page.wait_for_timeout(1000)

        # Now inspect the DOM
        print("\n=== Inspecting segment row buttons ===")
        result = await page.evaluate("""
        () => {
            const container = document.getElementById('subTitleContainer');
            if (!container) return 'NO CONTAINER';
            const rows = Array.from(container.children);
            const output = [];
            
            for (let i = 0; i < Math.min(3, rows.length); i++) {
                const row = rows[i];
                const rowData = {
                    index: i,
                    tag: row.tagName,
                    class: (row.className || '').substring(0, 100),
                    hasTextarea: !!row.querySelector('textarea'),
                    innerText: row.innerText.substring(0, 200),
                };
                
                // Get ALL buttons
                const buttons = row.querySelectorAll('button');
                rowData.buttonCount = buttons.length;
                rowData.buttons = [];
                
                buttons.forEach((btn, idx) => {
                    const svg = btn.querySelector('svg');
                    const svgPaths = [];
                    if (svg) {
                        svg.querySelectorAll('path').forEach(p => {
                            svgPaths.push((p.getAttribute('d') || '').substring(0, 60));
                        });
                    }
                    
                    rowData.buttons.push({
                        idx: idx,
                        text: btn.textContent.trim().substring(0, 30),
                        class: (btn.className || '').substring(0, 100),
                        title: btn.title || '',
                        ariaLabel: btn.getAttribute('aria-label') || '',
                        type: btn.type || '',
                        disabled: btn.disabled,
                        hasSvg: !!svg,
                        svgClass: svg ? (svg.className?.baseVal || '') : '',
                        svgTestId: svg ? (svg.getAttribute('data-testid') || '') : '',
                        svgPaths: svgPaths,
                        color: window.getComputedStyle(btn).color,
                        bgColor: window.getComputedStyle(btn).backgroundColor,
                        outerHTML: btn.outerHTML.substring(0, 200),
                    });
                });
                
                output.push(rowData);
            }
            
            return JSON.stringify(output, null, 2);
        }
        """)
        
        print(result)
        
        # Also check: what does the + button look like?
        print("\n=== Looking for +/- buttons specifically ===")
        plus_check = await page.evaluate("""
        () => {
            const container = document.getElementById('subTitleContainer');
            if (!container) return 'NO CONTAINER';
            const all = container.querySelectorAll('*');
            const found = [];
            for (const el of all) {
                const text = el.textContent.trim();
                if ((text === '+' || text === '-' || text === '−') && el.tagName !== 'DIV' && el.tagName !== 'SPAN') {
                    found.push({
                        tag: el.tagName,
                        text: text,
                        class: (el.className || '').substring(0, 80),
                        parent: el.parentElement ? el.parentElement.tagName : '',
                        outerHTML: el.outerHTML.substring(0, 150),
                    });
                }
            }
            return JSON.stringify(found, null, 2);
        }
        """)
        print(plus_check)
        
        await page.wait_for_timeout(5000)
        await browser.close()

asyncio.run(inspect())
