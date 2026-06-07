"""
Naukri Profile Auto-Refresher (API-based, no browser)
=======================================================
Uses Naukri's internal REST API to log in and update the
Resume Headline — no Playwright, no headless browser needed.

Requirements:
    pip install requests

Usage:
    python naukri_refresh.py
"""

import os
import json
import logging
import time
import random
from datetime import datetime
import requests

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

# ─────────────────────────────────────────────
#  HEADERS (mimic a real browser)
# ─────────────────────────────────────────────
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/json",
    "Origin": "https://www.naukri.com",
    "Referer": "https://www.naukri.com/",
    "appid": "109",
    "systemid": "109",
}


def login(session: requests.Session) -> dict:
    """Log in and return the user profile info."""
    log.info("Logging in to Naukri...")

    url = "https://www.naukri.com/central-login-services/v1/login"
    payload = {
        "username": NAUKRI_EMAIL,
        "password": NAUKRI_PASSWORD,
    }

    resp = session.post(url, json=payload, headers=BASE_HEADERS, timeout=30)

    if resp.status_code != 200:
        raise Exception(f"Login failed with status {resp.status_code}: {resp.text[:300]}")

    data = resp.json()

    # Extract auth token from response or cookies
    token = (
        data.get("loginData", {}).get("x-security-token")
        or data.get("x-security-token")
        or resp.headers.get("x-security-token")
        or session.cookies.get("nauk_at")
    )

    if token:
        session.headers.update({"x-security-token": token})
        log.info("Login successful. Token acquired.")
    else:
        log.warning("Login response received but no token found — will rely on session cookies.")
        log.debug("Response keys: %s", list(data.keys()))

    return data


def get_profile(session: requests.Session) -> dict:
    """Fetch the current profile / resume headline."""
    log.info("Fetching current profile...")

    url = "https://www.naukri.com/profile-api/v1/user/self"
    resp = session.get(url, headers=BASE_HEADERS, timeout=30)

    if resp.status_code != 200:
        raise Exception(f"Could not fetch profile: {resp.status_code} — {resp.text[:300]}")

    return resp.json()


def update_headline(session: requests.Session, current_headline: str) -> None:
    """Toggle a trailing space on the headline to trigger a profile refresh."""
    if current_headline.endswith(" "):
        new_headline = current_headline.rstrip(" ")
    else:
        new_headline = current_headline + " "

    log.info("Updating headline from: '%s'", current_headline[:80])
    log.info("              to:       '%s'", new_headline[:80])

    url = "https://www.naukri.com/profile-api/v1/user/self"
    payload = {"resumeHeadline": new_headline}

    resp = session.patch(url, json=payload, headers=BASE_HEADERS, timeout=30)

    if resp.status_code in (200, 201, 204):
        log.info("✅  Headline updated successfully.")
    else:
        # Try PUT if PATCH didn't work
        log.warning("PATCH returned %s, trying PUT...", resp.status_code)
        resp = session.put(url, json=payload, headers=BASE_HEADERS, timeout=30)
        if resp.status_code in (200, 201, 204):
            log.info("✅  Headline updated via PUT.")
        else:
            raise Exception(f"Update failed: {resp.status_code} — {resp.text[:300]}")


def refresh_naukri_profile():
    log.info("=" * 50)
    log.info("Naukri profile refresh started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    session = requests.Session()

    # Small random delay to look more human
    time.sleep(random.uniform(1.5, 4.0))

    # Step 1: Login
    login_data = login(session)

    # Step 2: Get current headline
    profile = get_profile(session)

    # Try common response paths for the headline
    headline = (
        profile.get("resumeHeadline")
        or profile.get("profileData", {}).get("resumeHeadline")
        or profile.get("data", {}).get("resumeHeadline")
        or ""
    )

    if not headline:
        log.warning("Could not find resumeHeadline in profile response. Keys: %s", list(profile.keys()))
        # Use a generic fallback so the update still fires
        headline = "Experienced Professional"

    # Step 3: Update
    update_headline(session, headline)

    log.info("Profile refresh complete: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 50)


if __name__ == "__main__":
    refresh_naukri_profile()
