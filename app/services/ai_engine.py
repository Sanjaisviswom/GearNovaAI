"""
app/services/ai_engine.py
──────────────────────────
Fault analysis engine powered by Google Gemini 1.5 Flash.
Uses the google-genai SDK (REST/HTTP only — no gRPC, no DLL required).

Given a user's fault description (text and/or image), the engine:
  1. Analyses the problem
  2. Identifies root causes
  3. Returns a structured list of recommended spare parts
  4. Generates YouTube search queries for repair tutorials

The engine maintains per-conversation chat history for multi-turn support.
"""

import base64
import json
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

# ── Lazy Gemini Client ────────────────────────────────────────
# Client is created on first use, not at import time.
# This lets the server boot even before a real API key is configured.
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env file. "
                "Get a free key at https://aistudio.google.com/app/apikey"
            )
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client

_GENERATION_CONFIG = types.GenerateContentConfig(
    temperature=0.3,
    top_p=0.85,
    max_output_tokens=2048,
)

_SYSTEM_PROMPT = """You are an expert automotive mechanic and vehicle spare parts specialist with deep expertise in the Indian automotive market, covering two-wheelers (motorcycles, scooters) and passenger cars.

🌍 MULTILINGUAL INTELLIGENCE (CRITICAL):
Users will communicate in English, native Indian scripts, or conversational Romanized scripts (Hinglish, Tanglish, Tenglish, Kanglish, Manglish, etc.).
- Detect the language and script the user is communicating in (e.g., English, Hinglish, Hindi, Tamil, Tanglish, Telugu, Tenglish, Kannada, Kanglish, Malayalam, Manglish, Marathi, Bengali, Gujarati).
- Respond in the EXACT SAME LANGUAGE and SCRIPT that the user used.
  - If the user writes in Hinglish ("bhai gadi start nahi ho rahi, kick jam hai"), reply with natural conversational Hinglish!
  - If the user writes in Tanglish ("vandi pickup aagala, sound varudhu"), reply in Tanglish!
  - If the user writes in Tenglish ("bike start avvatledu, sound vastondi"), reply in Tenglish!
  - If the user writes in native script (Hindi, Tamil, Telugu, etc.), reply in that native script!
  - If the user writes in English, reply in English!
- IMPORTANT FOR PARTS: Keep standard English brand and technical part names intact (e.g., "Rolon Brass Chain & Sprocket Kit", "NGK CR7HSA Spark Plug", "Bosch Brake Shoes") alongside your explanation so the customer can easily show it to an Indian mechanic or spare parts shop.
- In YouTube search queries, include relevant language/region keywords (e.g., "Activa 6G pickup problem in Tamil", "Splendor missing problem Hindi").

Your domain covers:
- Indian Two-Wheelers: Hero (Splendor, HF Deluxe, Glamour, Xpulse), Honda (Activa 3G/4G/5G/6G, Dio, Shine, Unicorn), Bajaj (Pulsar 125/150/180/NS200, Platina), TVS (Jupiter, Apache RTR 160/200, Ntorq, Raider, XL100), Royal Enfield (Classic 350, Bullet, Hunter, Meteor, Himalayan), Yamaha (FZ, R15, MT-15), Suzuki (Access 125, Burgman).
- Indian Four-Wheelers: Maruti Suzuki (Swift, Dzire, Baleno, WagonR, Brezza, Ertiga), Hyundai (i10, i20, Creta, Venue), Tata (Nexon, Punch, Tiago, Harrier), Mahindra (Scorpio, Thar, XUV700, Bolero), Kia, Toyota (Innova, Fortuner).
- Popular Indian Brands: Rolon, Endurance, Gabriel, Suprajit, ASK, Bosch, NGK, Amaron, Exide, Motul, Castrol, Bando, Varroc, Uno Minda, Lumax.

ALWAYS respond with valid JSON in this exact format:
{
  "detected_language": "Name of detected language (e.g. Hinglish, Tamil, Tanglish, English, Hindi, Telugu)",
  "fault_summary": "One-sentence diagnosis in the USER'S language/script",
  "root_causes": ["Cause 1 in user's language", "Cause 2 in user's language"],
  "severity": "low | medium | high | critical",
  "spare_parts": [
    {
      "name": "Part name (Keep English brand/part name clear, e.g. Rolon Chain Sprocket Kit)",
      "part_number": "Manufacturer/OEM part number if known, else null",
      "quantity": 1,
      "priority": "essential | recommended | optional",
      "reason": "Why this part is needed (explained in user's language)"
    }
  ],
  "search_queries": [
    "specific YouTube search query for repair tutorial in user's language 1",
    "specific YouTube search query for repair tutorial 2"
  ],
  "safety_warning": "Critical safety precaution in user's language, or null"
}

If you cannot diagnose without knowing the bike/car model or symptoms are too vague, set fault_summary to null and ask a clarifying question in root_causes[0] in the user's language."""




@dataclass
class FaultAnalysis:
    """Structured result from the AI engine."""
    fault_summary: str | None
    detected_language: str = "English"
    root_causes: list[str] = field(default_factory=list)
    severity: str = "medium"
    spare_parts: list[dict] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    safety_warning: str | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    raw_response: str = ""


# ── In-memory chat history (keyed by conversation_id) ────────
# Format: { conv_id: [ {"role": "user"|"model", "parts": [...]} ] }
_chat_history: dict[str, list[dict]] = {}


def _extract_json(text: str) -> dict:
    """Extract JSON from Gemini response, handling markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return json.loads(text)


async def analyse_fault(
    conversation_id: str,
    user_message: str,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> FaultAnalysis:
    """
    Analyse a fault description and return structured recommendations.

    Args:
        conversation_id: Used to maintain chat history for multi-turn conversations.
        user_message:    The user's text description of the fault.
        image_bytes:     Optional image of the broken part (JPEG/PNG/WEBP).
        mime_type:       MIME type of the image (e.g. 'image/jpeg').

    Returns:
        FaultAnalysis dataclass with parts, search queries, and safety info.
    """
    history = _chat_history.get(conversation_id, [])

    # Build content parts for this turn
    user_parts: list = [types.Part.from_text(text=user_message)]
    if image_bytes and mime_type:
        user_parts.append(
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        )

    # Assemble full contents (history + new user message)
    contents: list[types.Content] = []
    for h in history:
        contents.append(types.Content(role=h["role"], parts=h["parts"]))
    contents.append(types.Content(role="user", parts=user_parts))

    models_to_try = [settings.gemini_model, "gemini-3.8-flash", "gemini-2.5-flash"]
    seen = set()
    unique_models = [m for m in models_to_try if not (m in seen or seen.add(m))]

    response = None
    last_err = None
    for model_name in unique_models:
        try:
            response = await _get_client().aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    temperature=0.3,
                    top_p=0.85,
                    max_output_tokens=2048,
                ),
            )
            if response and response.text:
                break
        except Exception as err:
            logger.warning("Gemini model %s failed: %s. Trying fallback...", model_name, err)
            last_err = err

    if response is None:
        raise last_err or RuntimeError("All Gemini models failed")

    try:
        raw_text = response.text

        # Update chat history with this turn
        model_parts = [types.Part.from_text(text=raw_text)]
        _chat_history[conversation_id] = history + [
            {"role": "user", "parts": user_parts},
            {"role": "model", "parts": model_parts},
        ]

        # Parse structured JSON response
        try:
            data = _extract_json(raw_text)
        except (json.JSONDecodeError, ValueError) as parse_err:
            logger.warning(
                "Gemini returned non-JSON for conversation %s: %s", conversation_id, parse_err
            )
            return FaultAnalysis(
                fault_summary=None,
                needs_clarification=True,
                clarification_question=raw_text,
                raw_response=raw_text,
            )

        fault_summary = data.get("fault_summary")
        root_causes = data.get("root_causes", [])
        needs_clarification = fault_summary is None
        clarification_question = root_causes[0] if needs_clarification and root_causes else None

        return FaultAnalysis(
            fault_summary=fault_summary,
            detected_language=data.get("detected_language", "English"),
            root_causes=root_causes,
            severity=data.get("severity", "medium"),
            spare_parts=data.get("spare_parts", []),
            search_queries=data.get("search_queries", []),
            safety_warning=data.get("safety_warning"),
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            raw_response=raw_text,
        )

    except Exception as exc:
        logger.exception("Gemini API error for conversation %s: %s", conversation_id, exc)
        raise


def clear_session(conversation_id: str) -> None:
    """Clear the in-memory chat history for a conversation."""
    _chat_history.pop(conversation_id, None)


def format_parts_text(parts: list[dict]) -> str:
    """Format spare parts list as a WhatsApp-friendly string."""
    if not parts:
        return "_No specific parts identified. Please provide more details._"

    lines = []
    for i, part in enumerate(parts, 1):
        priority_emoji = {"essential": "🔴", "recommended": "🟡", "optional": "🟢"}.get(
            part.get("priority", "recommended"), "🔵"
        )
        name = part.get("name", "Unknown Part")
        pn = part.get("part_number")
        qty = part.get("quantity", 1)
        reason = part.get("reason", "")

        line = f"{i}. {priority_emoji} *{name}*"
        if pn:
            line += f" (P/N: {pn})"
        if qty > 1:
            line += f" × {qty}"
        if reason:
            line += f"\n   _{reason}_"
        lines.append(line)

    return "\n".join(lines)
