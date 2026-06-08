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
    driver = webdriver.Chrome(options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def login(driver: webdriver.Chrome) -> None:
    """Log in to Naukri using the known field IDs from the real HTML."""
    log.info("Navigating to login page...")
    driver.get("https://www.naukri.com/nlogin/login")
    wait = WebDriverWait(driver, 30)

    # Wait for the email field — confirmed ID from real HTML: #usernameField
    log.info("Waiting for email field...")
    email_field = wait.until(
        EC.presence_of_element_located((By.ID, "usernameField"))
    )

    # Use the React native input value setter so React's synthetic event system
    # registers the value — plain JS .value assignment doesn't update React state.
    react_set_value = """
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(arguments[0], arguments[1]);
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
    """

    driver.execute_script("arguments[0].scrollIntoView(true);", email_field)
    driver.execute_script(react_set_value, email_field, NAUKRI_EMAIL)
    log.info("Email entered.")
    time.sleep(random.uniform(0.5, 1.0))

    # Password field — confirmed ID: #passwordField
    password_field = driver.find_element(By.ID, "passwordField")
    driver.execute_script(react_set_value, password_field, NAUKRI_PASSWORD)
    log.info("Password entered.")
    time.sleep(random.uniform(0.5, 1.0))

    # Click the Login button — first submit button in the form (not OTP button)
    # Confirmed class: .blue-btn with type="submit"
    login_btn = driver.find_element(By.CSS_SELECTOR, "button.blue-btn[type='submit']")
    driver.execute_script("arguments[0].click();", login_btn)
    log.info("Login button clicked. Waiting for redirect...")

    # Only reliable success signal: URL leaves the /nlogin path
    try:
        wait.until(lambda d: "nlogin" not in d.current_url)
        log.info("Login successful — redirected to: %s", driver.current_url)
    except TimeoutException:
        log.error("Login FAILED. Still on: %s", driver.current_url)
        log.error("Page title: %s", driver.title)
        try:
            err_el = driver.find_element(By.CSS_SELECTOR, ".erLbl")
            log.error("Form error text: '%s'", err_el.text)
        except Exception:
            pass
        driver.save_screenshot("/tmp/naukri_error.png")
        raise Exception(
            "Login failed — still on login page after 30s. "
            "Check: (1) NAUKRI_EMAIL and NAUKRI_PASSWORD secrets are correct, "
            "(2) account doesn't require OTP/CAPTCHA from this IP."
        )

    time.sleep(random.uniform(2.0, 3.0))


def update_headline(driver: webdriver.Chrome) -> None:
    """Click the Resume Headline edit icon, toggle a trailing space, and save."""
    log.info("Navigating to profile page...")
    driver.get("https://www.naukri.com/mnjuser/profile")
    wait = WebDriverWait(driver, 30)

    # Wait for the Resume Headline widget to appear
    # Confirmed: .widgetTitle text = "Resume headline", edit icon = span.edit.icon
    log.info("Waiting for Resume Headline widget...")
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.edit.icon")))
    time.sleep(2)  # let React fully render

    # Find the edit pencil inside the Resume Headline card
    # There may be multiple .edit.icon spans — find the one in the headline widget
    edit_icons = driver.find_elements(By.CSS_SELECTOR, "span.edit.icon")
    headline_edit = None
    for icon in edit_icons:
        try:
            # Walk up to the card and check if it contains "Resume headline"
            card = icon.find_element(By.XPATH, "./ancestor::div[contains(@class,'card')]")
            if "Resume headline" in card.text or "resume headline" in card.text.lower():
                headline_edit = icon
                log.info("Found Resume Headline edit icon.")
                break
        except Exception:
            continue

    if headline_edit is None:
        # Fallback: just use the first edit icon
        log.warning("Could not identify headline card specifically — using first edit icon.")
        headline_edit = edit_icons[0]

    driver.execute_script("arguments[0].scrollIntoView(true);", headline_edit)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", headline_edit)
    log.info("Clicked edit icon. Waiting for textarea...")

    # Wait for the edit form — confirmed textarea ID: #resumeHeadlineTxt
    wait.until(EC.url_contains("modalOpen"))
    textarea = wait.until(
        EC.presence_of_element_located((By.ID, "resumeHeadlineTxt"))
    )
    time.sleep(1)

    current_text = textarea.get_attribute("value") or ""
    log.info("Current headline (%d chars): '%s...'", len(current_text), current_text[:60])

    # Toggle trailing space
    new_text = (
        current_text.rstrip(" ") if current_text.endswith(" ") else current_text + " "
    )

    # Use native textarea value setter so React's synthetic events fire correctly
    react_set_textarea = """
        var nativeTextareaSetter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value').set;
        nativeTextareaSetter.call(arguments[0], arguments[1]);
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
    """
    driver.execute_script(react_set_textarea, textarea, new_text)
    log.info("New headline set (%d chars).", len(new_text))
    time.sleep(random.uniform(0.5, 1.0))

    # Click Save — confirmed selector: button.btn-dark-ot[type='submit']
    save_btn = driver.find_element(
        By.CSS_SELECTOR, "button.btn-dark-ot[type='submit']"
    )
    driver.execute_script("arguments[0].click();", save_btn)
    log.info("Clicked Save. Waiting for modal to close...")

    # Success: URL returns to base profile page (no modalOpen)
    try:
        wait.until(lambda d: "modalOpen" not in d.current_url)
        log.info("✅  Profile refreshed successfully!")
    except TimeoutException:
        log.warning("Modal may still be open — save might have failed. Check profile manually.")


def refresh_naukri_profile():
    log.info("=" * 55)
    log.info("Naukri refresh started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    driver = None
    try:
        driver = get_driver()
        time.sleep(random.uniform(1.0, 2.0))

        login(driver)
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
