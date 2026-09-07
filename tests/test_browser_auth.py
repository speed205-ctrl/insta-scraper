"""
Unit tests for browser authentication utilities and session saving/loading.
"""

import json
import pickle
from pathlib import Path
import pytest
from scrapper.browser_auth import get_available_channel
from scrapper.scraper import InstagramScraper


def test_get_available_channel():
    channel = get_available_channel()
    assert channel in ["chrome", "msedge", "chromium"]


def test_scraper_loads_pickle_session(tmp_path: Path):
    # Create fake pickled session file
    session_file = tmp_path / "session-testuser"
    fake_cookies = {
        "sessionid": "test_session_12345",
        "ds_user_id": "99999",
        "csrftoken": "test_csrf_token",
    }
    with open(session_file, "wb") as f:
        pickle.dump(fake_cookies, f)

    scraper = InstagramScraper(session_file_dir=tmp_path)
    assert scraper._is_logged_in is True
    assert scraper.loader.context._session.cookies.get("sessionid") == "test_session_12345"


def test_scraper_loads_json_cookies(tmp_path: Path):
    # Create fake json cookies file
    json_file = tmp_path / "cookies.json"
    fake_data = {
        "username": "testuser_json",
        "sessionid": "json_sessionid_abc",
        "csrftoken": "json_csrf_xyz",
        "cookies": {
            "sessionid": "json_sessionid_abc",
            "csrftoken": "json_csrf_xyz",
            "ds_user_id": "88888",
        },
        "user_agent": "Mozilla/5.0 Custom User Agent",
    }
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(fake_data, f)

    scraper = InstagramScraper(session_file_dir=tmp_path)
    assert scraper._is_logged_in is True
    assert scraper.loader.context._session.cookies.get("sessionid") == "json_sessionid_abc"
    assert scraper.loader.context._session.headers.get("User-Agent") == "Mozilla/5.0 Custom User Agent"
