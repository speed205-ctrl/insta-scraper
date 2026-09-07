"""
Scraping module with dual-engine support:
1. Playwright Chrome Engine (Bypasses TLS/WAF 429 blocks using genuine browser session).
2. Instaloader Engine (Fast fallback for public queries).
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import instaloader

from scrapper.config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)


def parse_views_text(text: str) -> int:
    """Parse human-readable view counts into integers (e.g. '53,9 mil', '119K', '1.5M')."""
    if not text:
        return 0
    t = text.lower().replace("\xa0", " ").strip().replace(",", ".")
    try:
        m_mil = re.search(r"(\d+(?:\.\d+)?)\s*(?:mil|k)\b", t)
        if m_mil:
            return int(float(m_mil.group(1)) * 1_000)
        m_millon = re.search(r"(\d+(?:\.\d+)?)\s*(?:mill[oó]n(?:es)?|m)\b", t)
        if m_millon:
            return int(float(m_millon.group(1)) * 1_000_000)
        digits = re.findall(r"\d+", t)
        return int("".join(digits)) if digits else 0
    except Exception:
        return 0


def fetch_posts_via_playwright(target_username: str, max_posts: int) -> List[Dict[str, Any]]:
    """
    Fetch target user posts/reels using Playwright with saved browser cookies.
    Bypasses Instagram TLS fingerprinting (429 Too Many Requests).
    """
    from playwright.sync_api import sync_playwright
    from scrapper.browser_auth import get_available_channel

    cookies_file = PROJECT_ROOT / "data" / "sessions" / "cookies.json"
    if not cookies_file.exists():
        logger.warning("No se encontró cookies.json. Ejecuta primero: python -m scrapper --login")
        return []

    with open(cookies_file, "r", encoding="utf-8") as f:
        session_data = json.load(f)

    cookies_dict = session_data.get("cookies", {})
    user_agent = session_data.get("user_agent")
    channel = get_available_channel()

    playwright_cookies = [
        {"name": k, "value": v, "domain": ".instagram.com", "path": "/"}
        for k, v in cookies_dict.items()
    ]

    logger.info(f"Conectando Playwright ({channel.upper()}) para consultar Reels de @{target_username}...")

    timeline_metadata: Dict[str, Dict[str, Any]] = {}
    dom_reels: List[Dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=channel if channel != "chromium" else None,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 800},
        )
        context.add_cookies(playwright_cookies)
        page = context.new_page()

        def on_response(resp):
            if "graphql" in resp.url and resp.status == 200:
                try:
                    data = resp.json()
                    edges = (
                        data.get("data", {})
                        .get("xdt_api__v1__feed__user_timeline_graphql_connection", {})
                        .get("edges", [])
                    )
                    for edge in edges:
                        node = edge.get("node", {})
                        code = node.get("code")
                        if code:
                            timeline_metadata[code] = node
                except Exception:
                    pass

        page.on("response", on_response)

        # Navigate directly to reels tab
        reels_url = f"https://www.instagram.com/{target_username}/reels/"
        page.goto(reels_url, wait_until="networkidle", timeout=60000)

        # Dynamically scroll down until we have at least max_posts or reached the end of profile
        seen_items: Dict[str, Dict[str, str]] = {}
        no_new_cycles = 0
        last_count = 0

        while len(seen_items) < max_posts and no_new_cycles < 5:
            dom_items = page.evaluate("""() => {
                const items = [];
                const links = document.querySelectorAll("a[href*='/reel/']");
                for (const a of links) {
                    const href = a.href;
                    const text = a.innerText.trim();
                    const parts = href.split("/reel/");
                    if (parts.length > 1) {
                        const code = parts[1].replace(/\\//g, "");
                        items.push({ code, href, text });
                    }
                }
                return items;
            }""")
            for it in dom_items:
                seen_items[it["code"]] = it

            if len(seen_items) >= max_posts:
                break

            if len(seen_items) == last_count:
                no_new_cycles += 1
            else:
                no_new_cycles = 0
            last_count = len(seen_items)

            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.8)

        dom_reels = list(seen_items.values())
        browser.close()


    results: List[Dict[str, Any]] = []
    seen_codes = set()

    for item in dom_reels:
        code = item["code"]
        if code in seen_codes:
            continue
        seen_codes.add(code)

        views = parse_views_text(item["text"])
        node = timeline_metadata.get(code, {})
        likes = int(node.get("like_count") or 0)
        comments = int(node.get("comment_count") or 0)
        
        caption_obj = node.get("caption")
        caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""
        
        ts = node.get("taken_at")
        published_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
        duration = float(node.get("video_duration", 0.0) or 0.0)

        results.append({
            "shortcode": code,
            "url": item["href"],
            "views": views,
            "likes": likes,
            "comments": comments,
            "shares": 0,
            "duration_secs": duration,
            "caption": caption,
            "is_video": True,
            "video_url": None,
            "published_at": published_at,
        })

        if len(results) >= max_posts:
            break

    logger.info(f"Playwright extrajo exitosamente {len(results)} Reels de @{target_username}.")
    return results


class InstagramScraper:
    """Scraper that prioritizes Playwright engine with saved session, falling back to Instaloader."""

    def __init__(self, session_file_dir: Optional[Path] = None):
        self.session_dir = session_file_dir or (PROJECT_ROOT / "data" / "sessions")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )
        self._is_logged_in = False
        self._setup_session()

    def _setup_session(self) -> None:
        """Attempt to load saved session for Instaloader fallback."""
        json_file = self.session_dir / "cookies.json"
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cookies_dict = data.get("cookies", {})
                active_user = data.get("username", "default")
                ua = data.get("user_agent")
                if cookies_dict:
                    self.loader.context.load_session(active_user, cookies_dict)
                    if ua:
                        self.loader.context._session.headers["User-Agent"] = ua
                    self._is_logged_in = True
                    return
            except Exception as e:
                logger.warning(f"Could not load cookies.json for Instaloader: {e}")

        # Check for pickle session files
        for s_file in self.session_dir.glob("session-*"):
            user_part = s_file.name.replace("session-", "")
            try:
                self.loader.load_session_from_file(user_part, str(s_file))
                self._is_logged_in = True
                return
            except Exception as e:
                logger.warning(f"Could not load session file {s_file.name}: {e}")


    def fetch_posts(self, target_username: str, max_posts: Optional[int] = None) -> List[Dict[str, Any]]:
        clean_username = target_username.lstrip("@").strip()
        limit = max_posts or settings.max_posts_per_account

        # 1. Prioritize Playwright engine with browser session
        cookies_file = self.session_dir / "cookies.json"
        if cookies_file.exists():
            try:
                posts = fetch_posts_via_playwright(clean_username, limit)
                if posts:
                    return posts
            except Exception as e:
                logger.warning(f"Playwright fetch falló ({e}). Intentando Instaloader como fallback...")

        # 2. Fallback to Instaloader
        try:
            profile = instaloader.Profile.from_username(self.loader.context, clean_username)
            results = []
            for post in profile.get_posts():
                if len(results) >= limit:
                    break
                is_video = bool(getattr(post, "is_video", False))
                views = int(getattr(post, "video_view_count", 0) or getattr(post, "likes", 0) or 0)
                results.append({
                    "shortcode": post.shortcode,
                    "url": f"https://www.instagram.com/p/{post.shortcode}/",
                    "views": views,
                    "likes": post.likes,
                    "comments": post.comments,
                    "shares": 0,
                    "duration_secs": getattr(post, "video_duration", 0.0) or 0.0,
                    "caption": post.caption or "",
                    "is_video": is_video,
                    "video_url": getattr(post, "video_url", None),
                    "published_at": post.date_utc,
                })
            return results
        except Exception as err:
            logger.error(f"Error final obteniendo posts de @{clean_username}: {err}")
            raise
