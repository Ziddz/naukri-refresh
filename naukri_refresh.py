"""
Naukri Profile Auto-Refresher (cookie-based)
=============================================
Loads a saved login session via cookies — avoids the OTP
that Naukri triggers when logging in from an unknown IP.

Setup (one time):
    1. Run get_cookies.py locally to export your session cookies.
    2. base64-encode the resulting naukri_cookies.json:
           Mac/Linux:  base64 -i naukri_cookies.json | tr -d '\n'
           Windows:    certutil -encode naukri_cookies.json tmp.txt
                       (copy the middle lines, remove line breaks)
    3. Add the base64 string as a GitHub secret: NAUKRI_COOKIES
    4. Keep NAUKRI_EMAIL and NAUKRI_PASSWORD secrets too
       (used as fallback if cookies are expired).

Requirements:
    pip install selenium
"""

import os
import json
import base64
import logging
import time
import random
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
NAUKRI_EMAIL    = os.getenv("NAUKRI_EMAIL", "")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "")
NAUKRI_COOKIES  = os.getenv("NAUKRI_COOKIES", "")   # base64-encoded JSON

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def get_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def load_cookies(driver: webdriver.Chrome) -> bool:
    """
    Decode the base64 NAUKRI_COOKIES secret and inject them.
    Returns True if cookies were loaded, False if secret is missing.
    """
    if not NAUKRI_COOKIES:
        log.warning("NAUKRI_COOKIES secret not set — falling back to password login.")
        return False

    try:
        decoded = base64.b64decode(NAUKRI_COOKIES).decode("utf-8")
        cookies = json.loads(decoded)
    except Exception as e:
        log.error("Failed to decode NAUKRI_COOKIES: %s", e)
        return False

    # Must visit the domain before setting cookies
    driver.get("https://www.naukri.com")
    time.sleep(2)

    for cookie in cookies:
        # Selenium requires 'name' and 'value'; drop unsupported fields
        safe = {k: v for k, v in cookie.items()
                if k in ("name", "value", "domain", "path", "secure", "httpOnly", "expiry")}
        # Fix domain format
        if "domain" in safe and not safe["domain"].startswith("."):
            safe["domain"] = "." + safe["domain"].lstrip(".")
        try:
            driver.add_cookie(safe)
        except Exception as e:
            log.debug("Skipped cookie %s: %s", safe.get("name"), e)

    log.info("Cookies loaded (%d cookies).", len(cookies))
    return True


def is_logged_in(driver: webdriver.Chrome) -> bool:
    """Navigate to profile page and check if we land there or get redirected to login."""
    driver.get("https://www.naukri.com/mnjuser/profile")
    time.sleep(4)
    if "nlogin" in driver.current_url or "login" in driver.current_url.lower():
        log.warning("Cookie session expired or invalid — not logged in.")
        return False
    log.info("Session valid — on profile page: %s", driver.current_url)
    return True


def login_with_password(driver: webdriver.Chrome) -> None:
    """
    Fallback: log in with email/password using send_keys.
    This will trigger OTP from unknown IPs — only use if cookies are unavailable.
    """
    log.info("Attempting password login (may trigger OTP from this IP)...")
    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 30)

    email_field = wait.until(EC.element_to_be_clickable((By.ID, "usernameField")))
    email_field.click()
    email_field.send_keys(NAUKRI_EMAIL)
    time.sleep(0.5)

    pwd_field = driver.find_element(By.ID, "passwordField")
    pwd_field.click()
    pwd_field.send_keys(NAUKRI_PASSWORD)
    time.sleep(0.5)

    driver.find_element(By.CSS_SELECTOR, "button.blue-btn[type='submit']").click()

    try:
        wait.until(lambda d: "nlogin" not in d.current_url)
        log.info("Password login successful.")
    except TimeoutException:
        driver.save_screenshot("/tmp/naukri_error.png")
        raise Exception(
            "Password login failed. If you received an OTP email, "
            "set up the NAUKRI_COOKIES secret instead (see get_cookies.py)."
        )


def update_headline(driver: webdriver.Chrome) -> None:
    """Click Resume Headline edit, toggle trailing space, save."""
    wait = WebDriverWait(driver, 30)

    # The profile page should already be loaded from is_logged_in()
    # but navigate again cleanly just in case
    if "mnjuser/profile" not in driver.current_url:
        driver.get("https://www.naukri.com/mnjuser/profile")
        time.sleep(4)

    log.info("Looking for Resume Headline edit icon...")
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.edit.icon")))
    time.sleep(2)

    # Find the edit icon inside the Resume Headline card
    edit_icons = driver.find_elements(By.CSS_SELECTOR, "span.edit.icon")
    headline_edit = None
    for icon in edit_icons:
        try:
            card = icon.find_element(
                By.XPATH, "./ancestor::div[contains(@class,'card')]"
            )
            card_text = card.text.lower()
            if "resume headline" in card_text:
                headline_edit = icon
                log.info("Found Resume Headline edit icon.")
                break
        except Exception:
            continue

    if headline_edit is None:
        log.warning("Could not isolate headline card — using first edit icon.")
        headline_edit = edit_icons[0]

    driver.execute_script("arguments[0].scrollIntoView(true);", headline_edit)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", headline_edit)

    # Wait for modal URL and textarea
    log.info("Waiting for edit modal...")
    wait.until(EC.url_contains("modalOpen"))
    textarea = wait.until(EC.presence_of_element_located((By.ID, "resumeHeadlineTxt")))
    time.sleep(1)

    current_text = textarea.get_attribute("value") or ""
    log.info("Current headline (%d chars): '%s...'", len(current_text), current_text[:60])

    new_text = (
        current_text.rstrip(" ") if current_text.endswith(" ") else current_text + " "
    )

    # Native setter triggers React's synthetic events correctly
    react_set = """
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value').set;
        setter.call(arguments[0], arguments[1]);
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
    """
    driver.execute_script(react_set, textarea, new_text)
    log.info("Headline updated (%d chars).", len(new_text))
    time.sleep(random.uniform(0.5, 1.0))

    # Save
    save_btn = driver.find_element(
        By.CSS_SELECTOR, "button.btn-dark-ot[type='submit']"
    )
    driver.execute_script("arguments[0].click();", save_btn)
    log.info("Clicked Save. Waiting for modal to close...")

    try:
        wait.until(lambda d: "modalOpen" not in d.current_url)
        log.info("✅  Profile refreshed successfully!")
    except TimeoutException:
        log.warning("Modal close not detected — may still have saved. Check manually.")


def refresh_naukri_profile():
    log.info("=" * 55)
    log.info("Naukri refresh started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    driver = None
    try:
        driver = get_driver()

        # Try cookie-based login first
        cookies_loaded = load_cookies(driver)

        if cookies_loaded and is_logged_in(driver):
            log.info("Using saved cookie session.")
        else:
            # Fallback to password login (will trigger OTP on unknown IPs)
            login_with_password(driver)
            driver.get("https://www.naukri.com/mnjuser/profile")
            time.sleep(4)

        update_headline(driver)

        log.info("Refresh complete: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        log.error("Refresh failed: %s", e)
        if driver:
            try:
                driver.save_screenshot("/tmp/naukri_error.png")
                log.info("Screenshot saved to /tmp/naukri_error.png")
            except Exception:
                pass
        raise
    finally:
        if driver:
            driver.quit()

    log.info("=" * 55)


if __name__ == "__main__":
    refresh_naukri_profile()
