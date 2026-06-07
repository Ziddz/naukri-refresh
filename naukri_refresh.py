"""
Naukri Profile Auto-Refresher (API-based)
==========================================
Uses Naukri's internal REST API to log in and update the
Resume Headline — no browser needed.

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


def make_headers(extra: dict = {}) -> dict:
    base = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json",
        "Origin": "https://www.naukri.com",
        "Referer": "https://www.naukri.com/",
        "appid": "109",
        "systemid": "Naukri",
        "clientid": "d3skt0p",
        "gid": "LOCATION,INDUSTRY,EDUCATION,FAREA_ROLE",
    }
    base.update(extra)
    return base


def login(session: requests.Session) -> str:
    """Log in and return the auth token."""

    # Step 1: Hit the login page first to pick up any session cookies
    log.info("Fetching login page for cookies...")
    session.get(
        "https://www.naukri.com/nlogin/login",
        headers=make_headers({"Accept": "text/html,application/xhtml+xml,*/*"}),
        timeout=20,
        allow_redirects=True,
    )
    time.sleep(random.uniform(0.5, 1.5))

    # Step 2: POST to login API
    log.info("Posting login credentials...")
    url = "https://www.naukri.com/central-login-services/v1/login"

    payload = {
        "username": NAUKRI_EMAIL,
        "password": NAUKRI_PASSWORD,
        "type": "login",
    }

    resp = session.post(
        url,
        data=json.dumps(payload),   # explicit json.dumps to ensure correct encoding
        headers=make_headers(),
        timeout=30,
    )

    log.info("Login response: %s", resp.status_code)

    if resp.status_code == 400:
        log.warning("Got 400 — trying alternate payload format...")
        # Try without 'type' field
        payload2 = {"username": NAUKRI_EMAIL, "password": NAUKRI_PASSWORD}
        resp = session.post(url, data=json.dumps(payload2), headers=make_headers(), timeout=30)
        log.info("Retry response: %s | %s", resp.status_code, resp.text[:200])

    if resp.status_code not in (200, 201):
        raise Exception(
            f"Login failed ({resp.status_code}): {resp.text[:400]}\n"
            f"Response headers: {dict(resp.headers)}"
        )

    data = resp.json()
    log.debug("Login data keys: %s", list(data.keys()))

    # Pull token from multiple possible locations
    token = (
        data.get("loginData", {}).get("x-security-token")
        or data.get("x-security-token")
        or resp.headers.get("x-security-token")
        or data.get("authToken")
        or data.get("token")
    )

    if token:
        session.headers.update({"x-security-token": token})
        log.info("Login successful — token acquired.")
    else:
        log.warning("No token in response — relying on session cookies.")
        log.info("Response body: %s", resp.text[:400])

    return token or ""


def get_profile(session: requests.Session) -> dict:
    """Fetch current profile data."""
    log.info("Fetching profile...")

    endpoints = [
        "https://www.naukri.com/profile-api/v1/user/self",
        "https://www.naukri.com/resume-services/v3/user/self",
        "https://www.naukri.com/profile-api/v2/user/profile",
    ]

    for url in endpoints:
        resp = session.get(url, headers=make_headers(), timeout=30)
        log.info("%s -> %s", url, resp.status_code)
        if resp.status_code == 200:
            return resp.json()

    raise Exception("Could not fetch profile from any endpoint.")


def update_headline(session: requests.Session, current_headline: str) -> None:
    """Toggle trailing space on the headline to mark profile as updated."""
    new_headline = (
        current_headline.rstrip(" ")
        if current_headline.endswith(" ")
        else current_headline + " "
    )

    log.info("Headline: '%s...' -> '%s...'", current_headline[:60], new_headline[:60])

    endpoints_methods = [
        ("PATCH", "https://www.naukri.com/profile-api/v1/user/self"),
        ("PUT",   "https://www.naukri.com/profile-api/v1/user/self"),
        ("PATCH", "https://www.naukri.com/resume-services/v3/user/self"),
    ]

    payload = {"resumeHeadline": new_headline}

    for method, url in endpoints_methods:
        resp = session.request(
            method, url,
            data=json.dumps(payload),
            headers=make_headers(),
            timeout=30,
        )
        log.info("%s %s -> %s", method, url, resp.status_code)
        if resp.status_code in (200, 201, 204):
            log.info("✅  Profile refreshed successfully!")
            return

    raise Exception("Could not update headline via any endpoint.")


def refresh_naukri_profile():
    log.info("=" * 55)
    log.info("Naukri refresh started: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    session = requests.Session()
    time.sleep(random.uniform(1.0, 3.0))

    login(session)
    profile = get_profile(session)

    # Try various paths to find the headline
    headline = (
        profile.get("resumeHeadline")
        or profile.get("profileData", {}).get("resumeHeadline")
        or profile.get("data", {}).get("resumeHeadline")
        or profile.get("result", {}).get("resumeHeadline")
        or ""
    )

    if not headline:
        log.warning("Headline not found in profile. Profile keys: %s", list(profile.keys()))
        headline = "Experienced Professional"

    update_headline(session, headline)
    log.info("Refresh complete: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 55)


if __name__ == "__main__":
    refresh_naukri_profile()
