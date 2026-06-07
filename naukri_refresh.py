"""
Naukri Profile Auto-Refresher (Selenium-based)
===============================================
Uses a headless Chrome browser to log in and update the
Resume Headline — works reliably despite API changes.

Requirements:
    pip install selenium

Usage:
    python naukri_refresh.py
"""

import os
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
NAUKRI_EMAIL    = os.getenv("NAUKRI_EMAIL", "your_email@example.com")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "your_password")

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
    """Set up a headless Chrome driver."""
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

    # Selenium 4.6+ includes selenium-manager which auto-downloads
    # the correct chromedriver — no webdriver-manager needed.
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def login(driver: webdriver.Chrome) -> None:
    """Log in to Naukri."""
    log.info("Navigating to login page...")
    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 30)

    # Wait for the email field — try multiple known selectors
    log.info("Waiting for email field...")
    email_field = wait.until(EC.presence_of_element_located((
        By.CSS_SELECTOR,
        "input[type='text'][placeholder*='Email'], "
        "input[type='email'], "
        "input[placeholder*='Email'], "
        "input[placeholder*='Username'], "
        "#usernameField, "
        "input[name='username']"
    )))
    email_field.clear()
    email_field.send_keys(NAUKRI_EMAIL)
    log.info("Email entered.")
    time.sleep(random.uniform(0.4, 0.8))

    # Password field
    password_field = driver.find_element(
        By.CSS_SELECTOR,
        "input[type='password'], #passwordField, input[name='password']"
    )
    password_field.clear()
    password_field.send_keys(NAUKRI_PASSWORD)
    log.info("Password entered.")
    time.sleep(random.uniform(0.4, 0.8))

    # Click the Login button (not Register)
    login_btn = driver.find_element(
        By.CSS_SELECTOR,
        "button[type='submit']"
    )
    login_btn.click()
    log.info("Login button clicked.")

    # Wait for actual redirect away from the login page
    try:
        wait.until(EC.url_contains("naukri.com"))
        wait.until(lambda d: "nlogin" not in d.current_url)
        log.info("Login successful — now at: %s", driver.current_url)
    except TimeoutException:
        # Last resort: check for a logged-in nav element that never appears on login page
        try:
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".nI-gNb-sb__icon-wrapper, .view-profile-wrapper, [class*='user-name']")
            ))
            log.info("Login confirmed via nav element.")
        except TimeoutException:
            driver.save_screenshot("/tmp/naukri_error.png")
            raise Exception(
                f"Login failed — still on: {driver.current_url}. "
                "Check credentials or if Naukri is showing a CAPTCHA/OTP."
            )

    time.sleep(random.uniform(2.0, 3.5))


def update_headline(driver: webdriver.Chrome) -> None:
    """Navigate to profile edit and toggle the resume headline."""
    log.info("Navigating to profile page...")
    driver.get("https://www.naukri.com/mnjuser/profile")

    wait = WebDriverWait(driver, 30)

    # Wait for profile page to load — look for any edit pencil
    log.info("Waiting for profile page to load...")
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='edit'], [class*='pencil']")))
    time.sleep(2)  # let the React components fully render

    # Find the Resume Headline section edit icon — try multiple selectors
    headline_edit = None
    selectors = [
        # Most common pattern: edit icon inside the headline widget
        "//div[contains(@class,'resumeHeadline')]//span[contains(@class,'edit')]",
        "//div[contains(@class,'headline')]//span[contains(@class,'edit')]",
        # Section-based
        "//section[.//h2[contains(text(),'Resume Headline')]]//span[contains(@class,'edit')]",
        "//section[.//span[contains(text(),'Resume Headline')]]//span[contains(@class,'edit')]",
        # Widget header edit button
        "//div[contains(text(),'Resume Headline')]//following-sibling::*//span[contains(@class,'edit')]",
        "//span[contains(text(),'Resume Headline')]//ancestor::div[1]//span[contains(@class,'edit')]",
    ]

    for xpath in selectors:
        try:
            headline_edit = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            log.info("Found headline edit button with: %s", xpath)
            break
        except TimeoutException:
            continue

    if headline_edit is None:
        driver.save_screenshot("/tmp/naukri_error.png")
        raise Exception(
            "Could not find Resume Headline edit button. "
            "Screenshot saved — the page structure may have changed."
        )

    driver.execute_script("arguments[0].scrollIntoView(true);", headline_edit)
    time.sleep(0.5)
    headline_edit.click()
    log.info("Opened Resume Headline editor.")
    time.sleep(random.uniform(1.0, 1.5))

    # Find the textarea
    textarea = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR,
         "textarea[name='resumeHeadline'], "
         "textarea[placeholder], "
         "div[contenteditable='true']")
    ))

    current_text = textarea.get_attribute("value") or textarea.text or ""
    log.info("Current headline (first 60 chars): '%s...'", current_text[:60])

    # Toggle trailing space
    new_text = current_text.rstrip(" ") if current_text.endswith(" ") else current_text + " "

    # Clear and re-type
    textarea.clear()
    time.sleep(0.3)
    textarea.send_keys(new_text)
    time.sleep(random.uniform(0.5, 1.0))

    # Save
    save_btn = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[normalize-space()='Save' or normalize-space()='SAVE']")
    ))
    save_btn.click()
    log.info("Clicked Save.")

    # Confirm save (wait for editor to close or success toast)
    try:
        wait.until(EC.invisibility_of_element_located(
            (By.XPATH, "//button[normalize-space()='Save' or normalize-space()='SAVE']")
        ))
        log.info("✅  Profile refreshed successfully!")
    except TimeoutException:
        log.warning("Save confirmation not detected — it may still have saved.")


def refresh_naukri_profile():
    log.info("=" * 55)
    log.info("Naukri refresh started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    driver = None
    try:
        driver = get_driver()
        time.sleep(random.uniform(1.0, 2.5))

        login(driver)
        update_headline(driver)

        log.info("Refresh complete: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        log.error("Refresh failed: %s", e)
        if driver:
            # Save a screenshot for debugging
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
