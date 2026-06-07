"""
Naukri Profile Auto-Refresher
==============================
Logs into Naukri and updates your Resume Headline to bump your profile
to the top of recruiter searches.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python naukri_refresh.py

Scheduling (Linux/Mac - runs daily at 9 AM):
    crontab -e
    0 9 * * * /usr/bin/python3 /path/to/naukri_refresh.py >> /path/to/naukri.log 2>&1

Scheduling (Windows Task Scheduler):
    Action: python C:\path\to\naukri_refresh.py
    Trigger: Daily at preferred time
"""

import asyncio
import os
import random
import logging
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ─────────────────────────────────────────────
#  CONFIGURATION — edit these or set as env vars
# ─────────────────────────────────────────────
NAUKRI_EMAIL    = os.getenv("NAUKRI_EMAIL", "your_email@example.com")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "your_password")
HEADLESS        = True   # Set False to watch the browser in action

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


async def refresh_naukri_profile():
    log.info("Starting Naukri profile refresh...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            # ── Step 1: Log in ──────────────────────────────────────────
            log.info("Navigating to Naukri login page...")
            await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            log.info("Entering credentials...")
            await page.fill("#usernameField", NAUKRI_EMAIL)
            await page.fill("#passwordField", NAUKRI_PASSWORD)
            await page.click("button[type='submit']")

            # Wait for login to complete
            await page.wait_for_url("**/mnjuser/homepage**", timeout=15000)
            log.info("Logged in successfully.")
            await page.wait_for_timeout(2000)

            # ── Step 2: Go to profile page ──────────────────────────────
            log.info("Navigating to profile page...")
            await page.goto(
                "https://www.naukri.com/mnjuser/profile?id=&altresid",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3000)

            # ── Step 3: Edit Resume Headline ────────────────────────────
            log.info("Opening Resume Headline editor...")

            # Click the pencil/edit icon next to Resume Headline
            headline_edit = page.locator(
                "div.widgetHead:has-text('Resume Headline') ~ div .edit, "
                "div.resumeHeadline .edit, "
                "[class*='resumeHeadline'] [class*='edit']"
            ).first

            await headline_edit.click(timeout=10000)
            await page.wait_for_timeout(2000)

            # ── Step 4: Read current headline & make a tiny change ──────
            textarea = page.locator("textarea[name='resumeHeadline'], textarea#resumeHeadline").first
            current_text = await textarea.input_value()
            log.info(f"Current headline: {current_text[:60]}...")

            # Toggle a trailing space to force a change without altering content
            if current_text.endswith(" "):
                new_text = current_text.rstrip(" ")
            else:
                new_text = current_text + " "

            await textarea.fill(new_text)
            await page.wait_for_timeout(1000)

            # ── Step 5: Save ────────────────────────────────────────────
            log.info("Saving updated headline...")
            save_btn = page.locator(
                "button:has-text('Save'), input[value='Save'], button.btn-dark"
            ).first
            await save_btn.click(timeout=8000)
            await page.wait_for_timeout(2000)

            log.info("✅  Profile refreshed successfully at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        except PlaywrightTimeoutError as e:
            log.error("Timeout error — the page layout may have changed: %s", e)
            await page.screenshot(path="naukri_error.png")
            log.info("Screenshot saved as naukri_error.png for debugging.")
            raise

        except Exception as e:
            log.error("Unexpected error: %s", e)
            await page.screenshot(path="naukri_error.png")
            raise

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(refresh_naukri_profile())
