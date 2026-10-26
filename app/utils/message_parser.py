"""
app/utils/message_parser.py
────────────────────────────
Parse raw WhatsApp Cloud API webhook payloads into clean Python objects.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class IncomingMessage:
    """Normalised representation of a WhatsApp message."""
    wa_message_id: str
    from_number: str
    display_name: str | None
    message_type: str          # text | image | audio | document | sticker | ...
    text: str | None           # Populated for text messages
    media_id: str | None       # Populated for image/audio/document messages
    mime_type: str | None
    caption: str | None        # Caption sent with media
    timestamp: int


def parse_webhook_payload(payload: dict[str, Any]) -> list[IncomingMessage]:
    """
    Extract all incoming messages from a WhatsApp webhook payload.
    A single webhook POST can contain multiple messages (rare but possible).

    Returns an empty list if the payload is a status update (not a message).
    """
    messages: list[IncomingMessage] = []

    try:
        entry = payload.get("entry", [])
        for entry_item in entry:
            changes = entry_item.get("changes", [])
            for change in changes:
                value = change.get("value", {})

                if "messages" not in value:
                    # This is a status update (delivered/read), skip it
                    continue

                contacts = value.get("contacts", [])
                contact_map: dict[str, str] = {}
                for c in contacts:
                    wa_id = c.get("wa_id", "")
                    name = c.get("profile", {}).get("name")
                    if wa_id:
                        contact_map[wa_id] = name or wa_id

                for msg in value.get("messages", []):
                    msg_type = msg.get("type", "text")
                    from_number = msg.get("from", "")

                    text: str | None = None
                    media_id: str | None = None
                    mime_type: str | None = None
                    caption: str | None = None

                    if msg_type == "text":
                        text = msg.get("text", {}).get("body")
                    elif msg_type in ("image", "audio", "document", "video", "sticker"):
                        media_block = msg.get(msg_type, {})
                        media_id = media_block.get("id")
                        mime_type = media_block.get("mime_type")
                        caption = media_block.get("caption")
                    elif msg_type == "interactive":
                        # Handle button/list reply
                        interactive = msg.get("interactive", {})
                        reply = (
                            interactive.get("button_reply")
                            or interactive.get("list_reply")
                            or {}
                        )
                        text = reply.get("title") or reply.get("id", "")
                        msg_type = "text"

                    messages.append(
                        IncomingMessage(
                            wa_message_id=msg.get("id", ""),
                            from_number=from_number,
                            display_name=contact_map.get(from_number),
                            message_type=msg_type,
                            text=text,
                            media_id=media_id,
                            mime_type=mime_type,
                            caption=caption,
                            timestamp=int(msg.get("timestamp", 0)),
                        )
                    )
    except (KeyError, TypeError, ValueError):
        pass  # Malformed payload — return empty list

    return messages


def is_status_update(payload: dict[str, Any]) -> bool:
    """Return True if the payload is only a delivery/read status, not a new message."""
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "statuses" in value and "messages" not in value:
                    return True
    except (KeyError, TypeError):
        pass
    return False
