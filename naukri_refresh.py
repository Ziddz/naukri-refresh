"""
Naukri Profile Auto-Refresher
==============================
Logs in via Selenium. If Naukri triggers OTP, automatically
reads it from Gmail and submits it.

One-time setup:
    See GMAIL_SETUP.md for how to get GMAIL_CREDENTIALS_B64 secret.

GitHub Secrets required:
    NAUKRI_EMAIL           — your Naukri login email
    NAUKRI_PASSWORD        — your Naukri password
    GMAIL_CREDENTIALS_B64  — base64-encoded Gmail OAuth credentials JSON

Requirements:
    pip install selenium google-auth google-auth-oauthlib google-api-python-client
"""

import os
import json
import base64
import logging
import time
import random
import re
from datetime import datetime, timezone

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
NAUKRI_EMAIL           = os.getenv("NAUKRI_EMAIL", "")
NAUKRI_PASSWORD        = os.getenv("NAUKRI_PASSWORD", "")
GMAIL_CREDENTIALS_B64  = os.getenv("GMAIL_CREDENTIALS_B64", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  GMAIL OTP READER
# ─────────────────────────────────────────────

def get_gmail_service():
    """Build Gmail API service from base64-encoded credentials in GitHub secret."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds_json = base64.b64decode(GMAIL_CREDENTIALS_B64).decode("utf-8")
    creds_data = json.loads(creds_json)
    creds = Credentials.from_authorized_user_info(creds_data)
    return build("gmail", "v1", credentials=creds)


def fetch_naukri_otp(max_wait=90) -> str:
    """
    Poll Gmail for a Naukri OTP email that arrived after this function was called.
    Skips old emails from previous runs. Retries for up to max_wait seconds.
    Returns the 6-digit OTP string.
    """
    log.info("Waiting for Naukri OTP email in Gmail...")
    service = get_gmail_service()
    start = time.time()
    start_ms = int(start * 1000)  # Gmail internalDate is in milliseconds

    while time.time() - start < max_wait:
        try:
            results = service.users().messages().list(
                userId="me",
                q="from:info@naukri.com newer_than:10m",
                maxResults=5,
            ).execute()

            messages = results.get("messages", [])
            log.info("Gmail search returned %d messages.", len(messages))

            for msg_ref in messages:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="full",
                ).execute()

                internal_date_ms = int(msg.get("internalDate", 0))
                headers = msg.get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "")
                age_s = (time.time() * 1000 - internal_date_ms) / 1000
                log.info("Email — From: %s | Subject: %s | Age: %.0fs", sender, subject, age_s)

                # Skip emails that arrived before we started waiting (old runs)
                if internal_date_ms < start_ms - 30000:
                    log.info("Skipping old email (%.0fs before OTP request).", (start_ms - internal_date_ms) / 1000)
                    continue

                body = extract_email_body(msg)
                log.info("Body snippet: %s", body[:300].replace("\n", " "))
                otp = re.search(r"\b(\d{6})\b", body)
                if otp:
                    log.info("OTP found: %s", otp.group(1))
                    return otp.group(1)
                else:
                    log.warning("No 6-digit OTP found in email body.")

        except Exception as e:
            log.warning("Gmail poll error: %s", e)

        time.sleep(5)

    raise Exception("OTP not received in Gmail within 90 seconds.")


def extract_email_body(msg) -> str:
    """Extract text from a Gmail message, stripping HTML if needed."""
    payload = msg.get("payload", {})

    def decode_part(part):
        data = part.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return ""

    def get_all_parts(payload):
        """Recursively collect all parts from nested multipart messages."""
        parts = []
        if "parts" in payload:
            for part in payload["parts"]:
                parts.extend(get_all_parts(part))
        else:
            parts.append(payload)
        return parts

    all_parts = get_all_parts(payload)

    # Prefer plain text
    for part in all_parts:
        if part.get("mimeType") == "text/plain":
            text = decode_part(part)
            if text.strip():
                return text

    # Fallback: use HTML and strip tags
    for part in all_parts:
        if part.get("mimeType") == "text/html":
            html = decode_part(part)
            if html.strip():
                # Strip HTML tags to get plain text
                import re as _re
                text = _re.sub(r'<[^>]+>', ' ', html)
                text = _re.sub(r'&amp;', '&', text)
                text = _re.sub(r'&lt;', '<', text)
                text = _re.sub(r'&gt;', '>', text)
                text = _re.sub(r'&#[0-9]+;', ' ', text)
                text = _re.sub(r'\s+', ' ', text)
                return text

    # Last resort: decode whatever is there
    if all_parts:
        return decode_part(all_parts[0])
    return ""


# ─────────────────────────────────────────────
#  BROWSER
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
#  LOGIN
# ─────────────────────────────────────────────

def login(driver: webdriver.Chrome) -> None:
    log.info("Navigating to login page...")
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
    log.info("Login submitted.")

    # Wait up to 30s — either redirect (success) or OTP screen appears
    for _ in range(30):
        time.sleep(1)
        url = driver.current_url
        if "nlogin" not in url:
            log.info("Logged in directly — no OTP needed.")
            return
        # Check if OTP screen is showing
        if _is_otp_screen(driver):
            log.info("OTP screen detected — fetching OTP from Gmail...")
            _submit_otp(driver, wait)
            return

    driver.save_screenshot("/tmp/naukri_error.png")
    raise Exception("Login failed — neither redirected nor OTP screen appeared.")


def _is_otp_screen(driver) -> bool:
    """Check if the OTP input screen is currently showing."""
    try:
        return driver.find_element(
            By.CSS_SELECTOR, "input[type='text'][maxlength='1'], .otpContainer, [class*='otp']"
        ).is_displayed()
    except Exception:
        return False


def _submit_otp(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """Read OTP from Gmail and type it into the Naukri OTP fields."""
    otp = fetch_naukri_otp(max_wait=90)

    # Naukri uses 6 individual single-character input boxes for OTP
    otp_inputs = driver.find_elements(
        By.CSS_SELECTOR, "input[type='text'][maxlength='1']"
    )

    if len(otp_inputs) >= 6:
        # Individual boxes
        for i, digit in enumerate(otp[:6]):
            otp_inputs[i].click()
            otp_inputs[i].send_keys(digit)
            time.sleep(0.1)
    else:
        # Single input box fallback
        otp_input = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[type='text'], input[type='number']")
        ))
        otp_input.send_keys(otp)

    log.info("OTP entered. Submitting...")
    time.sleep(1)

    # Click Verify button
    try:
        verify_btn = driver.find_element(
            By.XPATH, "//button[contains(text(),'Verify') or contains(text(),'VERIFY') or contains(text(),'Submit')]"
        )
        verify_btn.click()
    except Exception:
        # Sometimes submits automatically after last digit
        pass

    # Wait for redirect after OTP
    try:
        wait.until(lambda d: "nlogin" not in d.current_url)
        log.info("OTP verified — logged in successfully.")
    except TimeoutException:
        driver.save_screenshot("/tmp/naukri_error.png")
        raise Exception("OTP submission failed — still on login page.")


# ─────────────────────────────────────────────
#  HEADLINE UPDATE
# ─────────────────────────────────────────────

def update_headline(driver: webdriver.Chrome) -> None:
    wait = WebDriverWait(driver, 30)

    if "mnjuser/profile" not in driver.current_url:
        driver.get("https://www.naukri.com/mnjuser/profile")
        time.sleep(4)

    log.info("Looking for Resume Headline edit icon...")
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.edit.icon")))
    time.sleep(2)

    edit_icons = driver.find_elements(By.CSS_SELECTOR, "span.edit.icon")
    headline_edit = None
    for icon in edit_icons:
        try:
            card = icon.find_element(By.XPATH, "./ancestor::div[contains(@class,'card')]")
            if "resume headline" in card.text.lower():
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

    log.info("Waiting for edit modal...")
    wait.until(EC.url_contains("modalOpen"))
    textarea = wait.until(EC.presence_of_element_located((By.ID, "resumeHeadlineTxt")))
    time.sleep(1)

    current_text = textarea.get_attribute("value") or ""
    log.info("Current headline (%d chars): '%s...'", len(current_text), current_text[:60])

    new_text = current_text.rstrip(" ") if current_text.endswith(" ") else current_text + " "

    react_set = """
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value').set;
        setter.call(arguments[0], arguments[1]);
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
    """
    driver.execute_script(react_set, textarea, new_text)
    log.info("Headline updated (%d chars).", len(new_text))
    time.sleep(random.uniform(0.5, 1.0))

    save_btn = driver.find_element(By.CSS_SELECTOR, "button.btn-dark-ot[type='submit']")
    driver.execute_script("arguments[0].click();", save_btn)
    log.info("Clicked Save. Waiting for modal to close...")

    try:
        wait.until(lambda d: "modalOpen" not in d.current_url)
        log.info("✅  Profile refreshed successfully!")
    except TimeoutException:
        log.warning("Modal close not detected — may still have saved.")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def refresh_naukri_profile():
    log.info("=" * 55)
    log.info("Naukri refresh started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    driver = None
    try:
        driver = get_driver()
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
