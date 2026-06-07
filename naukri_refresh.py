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
    wait = WebDriverWait(driver, 20)

    # Enter email
    email_field = wait.until(EC.presence_of_element_located((By.ID, "usernameField")))
    email_field.clear()
    email_field.send_keys(NAUKRI_EMAIL)
    time.sleep(random.uniform(0.3, 0.7))

    # Enter password
    password_field = driver.find_element(By.ID, "passwordField")
    password_field.clear()
    password_field.send_keys(NAUKRI_PASSWORD)
    time.sleep(random.uniform(0.3, 0.7))

    # Click login button
    login_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
    login_btn.click()

    # Wait for successful login (profile icon or redirect away from login page)
    try:
        wait.until(EC.url_changes("https://www.naukri.com/nlogin/login"))
        log.info("Login successful — redirected to: %s", driver.current_url)
    except TimeoutException:
        # Some accounts land on the same URL but show a logged-in state
        log.warning("URL didn't change, checking for logged-in indicators...")
        try:
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".nI-gNb-drawer__icon, [class*='naukri-logo'], #login_Layer")
            ))
            log.info("Login appears successful.")
        except TimeoutException:
            raise Exception("Login may have failed — check credentials or if CAPTCHA appeared.")

    time.sleep(random.uniform(2.0, 3.5))


def update_headline(driver: webdriver.Chrome) -> None:
    """Navigate to profile edit and toggle the resume headline."""
    log.info("Navigating to profile page...")
    driver.get("https://www.naukri.com/mnjuser/profile")

    wait = WebDriverWait(driver, 20)

    # Wait for the Resume Headline edit button
    try:
        headline_edit = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//div[contains(@class,'resumeHeadline')]//span[@class='edit icon']")
        ))
    except TimeoutException:
        # Try alternate selector
        headline_edit = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//section[contains(.,'Resume Headline')]//span[contains(@class,'edit')]")
        ))

    headline_edit.click()
    log.info("Opened Resume Headline editor.")
    time.sleep(random.uniform(1.0, 1.5))

    # Find the textarea
    textarea = wait.until(EC.presence_of_element_located(
        (By.XPATH, "//textarea[@name='resumeHeadline' or @placeholder]"
                   " | //div[@contenteditable='true']")
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
