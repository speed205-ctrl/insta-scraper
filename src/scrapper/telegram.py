"""
Telegram notifications module for dispatching viral Reel intelligence alerts.
"""

import logging
from typing import Any, Dict, Optional
import requests

from scrapper.config import settings

logger = logging.getLogger(__name__)


def send_telegram_message(text: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a message to the configured Telegram chat using Telegram Bot API.

    Args:
        text: Message content (Markdown or HTML supported).
        parse_mode: Formatting mode ('Markdown', 'MarkdownV2', or 'HTML').

    Returns:
        True if successfully sent, False otherwise.
    """
    token = settings.telegram_bot_token.strip()
    chat_id = settings.telegram_chat_id.strip()

    if not token or not chat_id:
        logger.debug("Telegram credentials not configured. Skipping notification.")
        return False

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(api_url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram notification sent successfully.")
            return True
        else:
            logger.warning(f"Telegram API returned status {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def send_viral_alert(
    competitor_username: str,
    reel: Dict[str, Any],
    analysis: Dict[str, Any],
    median_views: int = 0,
) -> bool:
    """
    Format and send an alert summarizing a newly detected and analyzed viral Reel.

    Args:
        competitor_username: Instagram username of the target account.
        reel: Reel data dictionary (url, views, likes, comments).
        analysis: AI analysis results (hook_text, hook_type, hook_score, etc.).
        median_views: Account historical median views.

    Returns:
        True if sent successfully, False otherwise.
    """
    views = reel.get("views", 0)
    multiplier = (views / median_views) if median_views > 0 else 1.0
    url = reel.get("url", "")
    hook_text = analysis.get("hook_text", "N/A")
    hook_type = analysis.get("hook_type", "N/A")
    hook_score = analysis.get("hook_score", 0)
    trigger = analysis.get("psychological_trigger", "N/A")
    script = analysis.get("generated_script", "")

    # Truncate script if too long for Telegram message limit
    if len(script) > 800:
        script = script[:800] + "...\n*(guion completo guardado en base de datos)*"

    message = f"""🚀 *¡NUEVO OUTLIER VIRAL DETECTADO!*

👤 *Cuenta:* `@{competitor_username}`
🔗 *Reel:* {url}
📊 *Vistas:* *{views:,}* ({multiplier:.1f}x la mediana de {median_views:,})
❤️ *Likes:* {reel.get('likes', 0):,} | 💬 *Comentarios:* {reel.get('comments', 0):,}

🎯 *ANÁLISIS DE GANCHO:*
- *Score:* ⭐ *{hook_score}/10*
- *Tipo:* _{hook_type}_
- *Frase inicial:* "{hook_text}"

🧠 *POR QUÉ FUNCIONÓ:*
{trigger}

📝 *GUION ADAPTADO SUGERIDO:*
{script}
"""

    return send_telegram_message(message, parse_mode="Markdown")
