"""
app/services/whatsapp.py
─────────────────────────
WhatsApp Cloud API client.

Provides methods to:
  - send_text       → plain text reply
  - send_parts_list → interactive list of spare parts
  - send_videos     → formatted YouTube recommendations
  - send_typing     → show "typing…" indicator (mark message as read)
  - download_media  → fetch image/audio bytes for AI analysis
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_BASE = f"https://graph.facebook.com/{settings.whatsapp_api_version}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }


async def _post(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a POST to the WhatsApp messages endpoint."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            settings.whatsapp_api_url,
            headers=_headers(),
            json=payload,
        )
        if response.status_code >= 400:
            logger.error("WhatsApp API Error [%s]: %s", response.status_code, response.text)
        response.raise_for_status()
        return response.json()


# ── Public API ────────────────────────────────────────────────

async def mark_as_read(message_id: str) -> None:
    """Mark an incoming message as read (shows blue ticks + typing indicator)."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{GRAPH_BASE}/{settings.whatsapp_phone_number_id}/messages",
                headers=_headers(),
                json=payload,
            )
            if resp.status_code >= 400:
                logger.warning("Could not mark message as read [%s]: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Could not mark message as read: %s", exc)


async def send_text(to: str, body: str) -> dict[str, Any]:
    """Send a plain text message."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    return await _post(payload)


async def send_parts_list(
    to: str,
    fault_summary: str,
    parts: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Send an interactive list message with spare parts.
    Each part becomes a row with its name and part number as description.
    Limited to 10 rows per WhatsApp API rules.
    """
    rows = [
        {
            "id": f"part_{i}",
            "title": p.get("name", "Unknown Part")[:24],
            "description": (
                f"P/N: {p.get('part_number', 'N/A')} | Priority: {p.get('priority', 'medium')}"
            )[:72],
        }
        for i, p in enumerate(parts[:10])
    ]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "🔧 Fault Analysis Complete"},
            "body": {
                "text": (
                    f"*Diagnosis:* {fault_summary[:1000]}\n\n"
                    "📦 *Recommended Spare Parts:*"
                )
            },
            "footer": {"text": "Tap to see part details"},
            "action": {
                "button": "View Parts",
                "sections": [{"title": "Spare Parts", "rows": rows}],
            },
        },
    }
    return await _post(payload)


async def send_videos(
    to: str,
    videos: list[dict[str, str]],
    parts_text: str,
) -> dict[str, Any]:
    """
    Send parts list + YouTube tutorial links as a formatted text message.
    WhatsApp does not support clickable links natively in list messages,
    so we use a rich text message with emojis.
    """
    lines = [
        "🔧 *Spare Parts Needed:*",
        parts_text,
        "",
        "🎥 *Repair Tutorial Videos:*",
    ]
    for v in videos:
        lines.append(f"▶️ *{v.get('title', 'Tutorial')}*")
        lines.append(f"   {v.get('url', '')}")

    lines.append("")
    lines.append("_Reply with your next question or describe another fault._")

    return await send_text(to, "\n".join(lines))


async def send_error(to: str) -> dict[str, Any]:
    """Send a generic error message when processing fails."""
    return await send_text(
        to,
        "⚠️ Sorry, I encountered an error while analysing your request. "
        "Please try again or describe the fault differently.",
    )


async def send_language_selection(
    to: str,
    prompt: str = "Choose your preferred language for YouTube repair tutorial videos:",
) -> dict[str, Any]:
    """
    Send an interactive dropdown selection list asking for video tutorial language preference:
    Malayalam, English, Hindi.
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": "🎥 Tutorial Videos",
            },
            "body": {
                "text": prompt[:1024],
            },
            "footer": {
                "text": "Tap to choose language",
            },
            "action": {
                "button": "Select Language",
                "sections": [
                    {
                        "title": "Available Languages",
                        "rows": [
                            {
                                "id": "lang_malayalam",
                                "title": "Malayalam",
                                "description": "മലയാളം repair tutorials",
                            },
                            {
                                "id": "lang_english",
                                "title": "English",
                                "description": "English repair tutorials",
                            },
                            {
                                "id": "lang_hindi",
                                "title": "Hindi",
                                "description": "हिन्दी repair tutorials",
                            },
                        ],
                    }
                ],
            },
        },
    }
    try:
        return await _post(payload)
    except Exception as exc:
        logger.warning("Could not send interactive language list, falling back to text: %s", exc)
        text_body = (
            f"🎥 *Repair Video Language Preference:*\n\n"
            f"{prompt}\n\n"
            "1️⃣ *Malayalam* (മലയാളം)\n"
            "2️⃣ *English*\n"
            "3️⃣ *Hindi* (हिन्दी)\n\n"
            "_Reply with 1, 2, or 3 (or type Malayalam, English, or Hindi)._"
        )
        return await send_text(to, text_body)


async def send_welcome(to: str, name: str | None = None) -> dict[str, Any]:
    """Send a welcome message to a first-time user."""
    greeting = f"Hi {name}! 👋" if name else "Hello! 👋"
    body = (
        f"{greeting} Welcome to *Spare Parts AI Assistant* 🔧\n\n"
        "I can help you diagnose vehicle and machine faults, find genuine spare parts, and provide repair video tutorials.\n\n"
        "📝 *How to use:*\n"
        "• Describe the fault in plain words (e.g. _'my compressor makes grinding noise'_)\n"
        "• Send a photo of the broken part\n"
        "• Choose your preferred video language (Malayalam, English, Hindi)!\n\n"
        "_Go ahead — describe your fault or choose your video language_ ⬇️"
    )
    return await send_text(to, body)


async def download_media(media_id: str) -> bytes:
    """Download image/audio bytes from WhatsApp media servers."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: Get the media URL
        meta_resp = await client.get(
            f"{GRAPH_BASE}/{media_id}",
            headers=_headers(),
        )
        meta_resp.raise_for_status()
        media_url = meta_resp.json()["url"]

        # Step 2: Download the actual bytes
        media_resp = await client.get(media_url, headers=_headers())
        media_resp.raise_for_status()
        return media_resp.content
