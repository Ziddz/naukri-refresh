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

Scheduling via GitHub Actions (see naukri_refresh.yml)
"""

import asyncio
import os
import logging
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ─────────────────────────────────────────────
#  CONFIGURATION — edit these or set as env vars
# ─────────────────────────────────────────────
NAUKRI_EMAIL    = os.getenv("NAUKRI_EMAIL", "your_email@example.com")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "your_password")
HEADLESS        = True

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


async def find_and_fill(page, selectors: list, value: str, label: str):
    """Try multiple selectors until one works."""
    for selector in selectors:
        try:
            await page.wait_for_selector(selector, timeout=5000)
            await page.fill(selector, value)
            log.info(f"Filled {label} using selector: {selector}")
            return
        except Exception:
            continue
    raise Exception(f"Could not find {label} field. Tried: {selectors}")


async def find_and_click(page, selectors: list, label: str):
    """Try multiple selectors until one works."""
    for selector in selectors:
        try:
            await page.wait_for_selector(selector, timeout=5000)
            await page.click(selector)
            log.info(f"Clicked {label} using selector: {selector}")
            return
        except Exception:
            continue
    raise Exception(f"Could not find {label} button. Tried: {selectors}")


async def refresh_naukri_profile():
    log.info("Starting Naukri profile refresh...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )

        # Hide webdriver fingerprint
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        try:
            # ── Step 1: Log in ──────────────────────────────────────────
            log.info("Navigating to Naukri login page...")
            await page.goto(
                "https://www.naukri.com/nlogin/login",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(3000)

            # Save screenshot for debugging
            await page.screenshot(path="before_login.png")
            log.info("Screenshot saved: before_login.png")

            # ── Step 2: Fill email ──────────────────────────────────────
            log.info("Entering email...")
            await find_and_fill(page, [
                "#usernameField",
                "input[placeholder*='Email']",
                "input[placeholder*='email']",
                "input[type='email']",
                "input[name='username']",
                "input[name='email']",
                "input[id*='user']",
                "input[id*='email']",
            ], NAUKRI_EMAIL, "email")

            await page.wait_for_timeout(500)

            # ── Step 3: Fill password ───────────────────────────────────
            log.info("Entering password...")
            await find_and_fill(page, [
                "#passwordField",
                "input[type='password']",
                "input[placeholder*='Password']",
                "input[placeholder*='password']",
                "input[name='password']",
                "input[id*='password']",
                "input[id*='pass']",
            ], NAUKRI_PASSWORD, "password")

            await page.wait_for_timeout(500)

            # ── Step 4: Click login button ──────────────────────────────
            log.info("Clicking login button...")
            await find_and_click(page, [
                "button[type='submit']",
                "button:has-text('Login')",
                "button:has-text('Sign in')",
                "input[type='submit']",
                ".loginButton",
                "[class*='login']button",
            ], "login button")

            # ── Step 5: Wait for redirect after login ───────────────────
            log.info("Waiting for login to complete...")
            await page.wait_for_timeout(5000)
            await page.screenshot(path="after_login.png")
            log.info(f"Post-login URL: {page.url}")

            if "login" in page.url.lower():
                raise Exception("Login may have failed — still on login page. Check credentials.")

            log.info("Logged in successfully.")

            # ── Step 6: Go to profile page ──────────────────────────────
            log.info("Navigating to profile page...")
            await page.goto(
                "https://www.naukri.com/mnjuser/profile?id=&altresid",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(4000)
            await page.screenshot(path="profile_page.png")

            # ── Step 7: Edit Resume Headline ────────────────────────────
            log.info("Opening Resume Headline editor...")
            await find_and_click(page, [
                "div.widgetHead:has-text('Resume Headline') ~ div .edit",
                "[class*='resumeHeadline'] [class*='edit']",
                "[data-ga-track*='resumeHeadline'] .edit",
                "section[class*='headline'] .edit",
                ".headline .edit",
                "#resumeHeadline ~ .edit",
                "[class*='edit'][title*='headline' i]",
            ], "Resume Headline edit button")

            await page.wait_for_timeout(2000)

            # ── Step 8: Update headline with tiny whitespace toggle ──────
            textarea = None
            for sel in [
                "textarea[name='resumeHeadline']",
                "textarea#resumeHeadline",
                "textarea[placeholder*='headline' i]",
                "div[class*='headline'] textarea",
                ".popupContent textarea",
                "textarea",
            ]:
                try:
                    await page.wait_for_selector(sel, timeout=4000)
                    textarea = page.locator(sel).first
                    break
                except Exception:
                    continue

            if not textarea:
                raise Exception("Could not find Resume Headline textarea.")

            current_text = await textarea.input_value()
            log.info(f"Current headline: {current_text[:80]}")

            new_text = current_text.rstrip(" ") if current_text.endswith(" ") else current_text + " "
            await textarea.fill(new_text)
            await page.wait_for_timeout(1000)

            # ── Step 9: Save ────────────────────────────────────────────
            log.info("Saving...")
            await find_and_click(page, [
                "button:has-text('Save')",
                "input[value='Save']",
                ".saveButton",
                "button.btn-dark",
                "[class*='save']",
            ], "Save button")

            await page.wait_for_timeout(2000)
            log.info("✅  Profile refreshed at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        except Exception as e:
            log.error("Error: %s", e)
            await page.screenshot(path="naukri_error.png")
            log.info("Screenshot saved: naukri_error.png")
            raise

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(refresh_naukri_profile())
