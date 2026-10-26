"""
tests/test_message_parser.py
─────────────────────────────
Tests for the WhatsApp webhook payload parser.
"""

from app.utils.message_parser import is_status_update, parse_webhook_payload
from tests.conftest import make_status_payload, make_text_payload


def test_parse_text_message():
    payload = make_text_payload("919876543210", "bearing noise", "msg_001")
    messages = parse_webhook_payload(payload)

    assert len(messages) == 1
    msg = messages[0]
    assert msg.from_number == "919876543210"
    assert msg.text == "bearing noise"
    assert msg.message_type == "text"
    assert msg.display_name == "Test User"
    assert msg.wa_message_id == "msg_001"


def test_parse_image_message():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "e1",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [{"profile": {"name": "Alice"}, "wa_id": "911111111111"}],
                            "messages": [
                                {
                                    "id": "img_001",
                                    "from": "911111111111",
                                    "timestamp": "1700000000",
                                    "type": "image",
                                    "image": {
                                        "id": "media_xyz",
                                        "mime_type": "image/jpeg",
                                        "caption": "broken bearing",
                                    },
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    messages = parse_webhook_payload(payload)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.message_type == "image"
    assert msg.media_id == "media_xyz"
    assert msg.mime_type == "image/jpeg"
    assert msg.caption == "broken bearing"


def test_status_update_returns_empty():
    messages = parse_webhook_payload(make_status_payload())
    assert messages == []


def test_is_status_update_true():
    assert is_status_update(make_status_payload()) is True


def test_is_status_update_false():
    assert is_status_update(make_text_payload("91123", "test")) is False


def test_malformed_payload_returns_empty():
    messages = parse_webhook_payload({"invalid": "data"})
    assert messages == []


def test_interactive_list_reply():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "e1",
                "changes": [
                    {
                        "value": {
                            "contacts": [{"profile": {"name": "Bob"}, "wa_id": "912222222222"}],
                            "messages": [
                                {
                                    "id": "int_001",
                                    "from": "912222222222",
                                    "timestamp": "1700000010",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "list_reply",
                                        "list_reply": {"id": "part_0", "title": "Ball Bearing SKF"},
                                    },
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    messages = parse_webhook_payload(payload)
    assert len(messages) == 1
    assert messages[0].message_type == "text"
    assert messages[0].text == "Ball Bearing SKF"
