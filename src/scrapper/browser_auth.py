"""
Interactive browser authentication for Instagram using Playwright.
Launches a real browser window (Chrome or Edge) for the user to log in manually,
and automatically extracts and saves session cookies for Instaloader and API requests.
"""

import json
import logging
import pickle
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from scrapper.config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)
console = Console()


def get_available_channel() -> str:
    """Detect whether Google Chrome or Microsoft Edge is available."""
    chrome_paths = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ]
    for p in chrome_paths:
        if p.exists():
            return "chrome"

    edge_paths = [
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    ]
    for p in edge_paths:
        if p.exists():
            return "msedge"

    return "chromium"


def interactive_browser_login(
    target_username: Optional[str] = None,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """
    Open a visible browser window for the user to log in manually to Instagram.
    Captures session cookies once login is successful and stores them.

    Args:
        target_username: Optional Instagram username to associate with the session.
        timeout_seconds: Maximum time in seconds to wait for user to log in (default: 5 min).

    Returns:
        Dict with status, username, and saved file paths.
    """
    from playwright.sync_api import sync_playwright

    sessions_dir = PROJECT_ROOT / "data" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    user_data_dir = PROJECT_ROOT / "data" / "browser_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    channel = get_available_channel()
    console.print(f"\n[bold cyan]🌐 Abriendo navegador ({channel.upper()}) para inicio de sesión en Instagram...[/bold cyan]")
    console.print("[yellow]Por favor ingresa tus credenciales, resuelve 2FA si aplica y navega hasta que cargue tu cuenta.[/yellow]\n")

    with sync_playwright() as p:
        # Launch persistent context to preserve browser fingerprint
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            channel=channel if channel != "chromium" else None,
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
            no_viewport=True,
        )

        page = context.new_page()
        page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")

        start_time = time.time()
        logged_in = False
        detected_username = target_username or settings.instagram_username.strip()

        console.print("[dim]Esperando que inicies sesión en la ventana del navegador...[/dim]")

        while time.time() - start_time < timeout_seconds:
            cookies = context.cookies()
            cookie_dict = {
                c["name"]: c["value"]
                for c in cookies
                if "instagram.com" in c.get("domain", "")
            }

            # Check if critical auth cookies are present
            has_sessionid = "sessionid" in cookie_dict and len(cookie_dict["sessionid"]) > 10
            has_user_id = "ds_user_id" in cookie_dict
            current_url = page.url

            # If sessionid is active and we moved past login / checkpoint screen
            if has_sessionid and has_user_id and "/accounts/login" not in current_url:
                logged_in = True
                
                # Try to extract the username if not already known
                if not detected_username:
                    try:
                        # Attempt to find username from profile link or cookies
                        profile_link = page.query_selector("a[href*='/direct/inbox/'] ~ a, svg[aria-label='Perfil']")
                        # Look at the user ID
                        ds_id = cookie_dict.get("ds_user_id", "")
                        detected_username = f"user_{ds_id}" if ds_id else "default"
                    except Exception:
                        detected_username = "default"

                break

            time.sleep(2)

        if not logged_in:
            context.close()
            raise TimeoutError("Tiempo de espera agotado sin detectar inicio de sesión en Instagram.")

        # Save cookies in multiple compatible formats
        final_username = detected_username or "default"
        
        # 1. Instaloader pickle session format
        session_file = sessions_dir / f"session-{final_username}"
        with open(session_file, "wb") as f:
            pickle.dump(cookie_dict, f)

        # Also save a default alias session file
        default_session_file = sessions_dir / "session-default"
        with open(default_session_file, "wb") as f:
            pickle.dump(cookie_dict, f)

        # 2. JSON cookies file for Playwright / direct requests
        json_file = sessions_dir / "cookies.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "username": final_username,
                "ds_user_id": cookie_dict.get("ds_user_id"),
                "sessionid": cookie_dict.get("sessionid"),
                "csrftoken": cookie_dict.get("csrftoken"),
                "cookies": cookie_dict,
                "user_agent": page.evaluate("navigator.userAgent"),
            }, f, indent=2)

        context.close()

        console.print(f"[bold green]✓ ¡Inicio de sesión exitoso detectado![/bold green]")
        console.print(f"[green]✓ Sesión guardada en:[/green] [cyan]{session_file}[/cyan]")
        console.print(f"[green]✓ Configuración JSON guardada en:[/green] [cyan]{json_file}[/cyan]\n")

        return {
            "success": True,
            "username": final_username,
            "session_file": str(session_file),
            "json_file": str(json_file),
        }
