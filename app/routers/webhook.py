"""
app/routers/webhook.py
───────────────────────
WhatsApp Cloud API webhook handler.

GET  /webhook  →  Meta verification challenge
POST /webhook  →  Receive messages, run async pipeline, reply to user

Processing pipeline for each incoming message:
  1. Parse payload → IncomingMessage
  2. Get or create User in DB
  3. Get or create active Conversation
  4. Save incoming message to DB
  5. Mark message as read (blue ticks)
  6. If first message → send welcome
  7. Run AI fault analysis (text + optional image)
  8. Enrich parts with DB catalogue
  9. Search YouTube tutorials
  10. Send formatted WhatsApp reply
  11. Save assistant reply to DB
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageType,
)
from app.models.user import User
from app.services import ai_engine, parts_lookup, whatsapp, youtube
from app.utils.message_parser import IncomingMessage, is_status_update, parse_webhook_payload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


# ── Verification endpoint ─────────────────────────────────────

@router.get("")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """
    Meta webhook verification handshake.
    Meta sends a GET request with hub.verify_token; we echo back hub.challenge.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("Webhook verified successfully.")
        return PlainTextResponse(content=hub_challenge or "")
    logger.warning("Webhook verification failed — invalid token.")
    raise HTTPException(status_code=403, detail="Verification failed")


# ── Incoming messages endpoint ────────────────────────────────

@router.post("")
async def receive_message(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive incoming WhatsApp messages.
    Returns 200 immediately (Meta requires < 15s) and processes in background.
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return {"status": "ok"}  # Always return 200 to Meta

    # Ignore status-only updates (delivered / read receipts)
    if is_status_update(payload):
        return {"status": "ok"}

    messages = parse_webhook_payload(payload)
    for msg in messages:
        # Schedule processing as a background task so we return 200 immediately
        background_tasks.add_task(_process_message, msg)

    return {"status": "ok"}


# ── Core processing pipeline ──────────────────────────────────

async def _process_message(incoming: IncomingMessage) -> None:
    """
    Full async pipeline: AI analysis → parts enrichment → YouTube → WhatsApp reply.
    Uses a fresh DB session since this runs outside the request lifecycle.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            await _handle_message(incoming, db)
            await db.commit()
        except Exception as exc:
            logger.exception(
                "Error processing message from %s: %s", incoming.from_number, exc
            )
            await db.rollback()
            # Best-effort error reply
            try:
                await whatsapp.send_error(incoming.from_number)
            except Exception:
                pass


def _detect_language_choice(text: str) -> str | None:
    """Detect if the user selected or typed a video language choice."""
    if not text:
        return None
    raw = text.strip().lower()
    if raw in ("1", "malayalam", "lang_malayalam", "mal", "ml", "malayalam 🌴"):
        return "malayalam"
    if raw in ("2", "english", "lang_english", "eng", "en", "english 🌐"):
        return "english"
    if raw in ("3", "hindi", "lang_hindi", "hin", "hi", "hindi 🇮🇳"):
        return "hindi"
    if "malayalam" in raw:
        return "malayalam"
    if "hindi" in raw:
        return "hindi"
    if "english" in raw:
        return "english"
    return None


async def _handle_message(incoming: IncomingMessage, db: AsyncSession) -> None:
    # ── Step 1: Get or create User ────────────────────────────
    stmt = select(User).where(User.phone_number == incoming.from_number)
    result = await db.execute(stmt)
    user: User | None = result.scalar_one_or_none()
    is_new_user = user is None

    if user is None:
        user = User(
            phone_number=incoming.from_number,
            name=incoming.display_name,
        )
        db.add(user)
        await db.flush()  # Get the ID assigned

    # ── Step 2: Get active Conversation or create new ─────────
    stmt = (
        select(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.status == ConversationStatus.ACTIVE,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    conversation: Conversation | None = result.scalar_one_or_none()

    if conversation is None:
        conversation = Conversation(user_id=user.id, status=ConversationStatus.ACTIVE)
        db.add(conversation)
        await db.flush()

    conversation_id = str(conversation.id)

    # ── Step 3: Save incoming message ─────────────────────────
    msg_type = MessageType.TEXT if incoming.message_type == "text" else MessageType.IMAGE
    user_text = incoming.text or incoming.caption or ""

    user_msg = Message(
        conversation_id=conversation.id,
        whatsapp_message_id=incoming.wa_message_id,
        role=MessageRole.USER,
        message_type=msg_type,
        content=user_text,
    )
    db.add(user_msg)
    await db.flush()

    # ── Step 4: Mark message as read (blue ticks) ─────────────
    await whatsapp.mark_as_read(incoming.wa_message_id)

    raw_lower = user_text.strip().lower()

    # ── Language selection command ────────────────────────────
    if raw_lower in ("language", "lang", "video language", "change language", "select language", "languages"):
        await whatsapp.send_language_selection(incoming.from_number)
        return

    # ── Language choice response ──────────────────────────────
    selected_lang = _detect_language_choice(user_text)
    if selected_lang and (len(user_text.strip().split()) <= 3 or raw_lower.startswith("lang_")):
        user.preferred_video_language = selected_lang
        await db.flush()
        lang_names = {
            "malayalam": "Malayalam (മലയാളം) 🌴",
            "english": "English 🌐",
            "hindi": "Hindi (हिन्दी) 🇮🇳",
        }
        display_lang = lang_names.get(selected_lang, selected_lang.capitalize())

        # Check for recent search queries in the active conversation
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.role == MessageRole.ASSISTANT,
            )
            .order_by(Message.created_at.desc())
            .limit(5)
        )
        res = await db.execute(stmt)
        recent_messages = res.scalars().all()

        search_queries = []
        for msg in recent_messages:
            if msg.metadata_ and "search_queries" in msg.metadata_:
                search_queries = msg.metadata_.get("search_queries", [])
                if search_queries:
                    break

        if search_queries:
            # User selected language for the repair tutorial videos!
            await whatsapp.send_text(
                incoming.from_number,
                f"🔍 Finding repair tutorial videos in *{display_lang}*...",
            )
            videos = await youtube.search_multiple_queries(
                search_queries, db, videos_per_query=2, language=selected_lang
            )
            videos_text = youtube.format_videos_for_whatsapp(videos, language=selected_lang)
            reply_text = (
                f"🎥 *Repair Tutorial Videos ({display_lang}):*\n\n{videos_text}\n\n"
                f"_Type *language* to switch languages or describe another fault for more help!_ 🔧"
            )
            await whatsapp.send_text(incoming.from_number, reply_text)
            _save_assistant_message(db, conversation.id, reply_text, {
                "language": selected_lang,
                "videos": videos,
                "search_queries": search_queries,
            })
            await db.flush()
            return
        else:
            await whatsapp.send_text(
                incoming.from_number,
                f"✅ Video tutorial language set to *{display_lang}*!\n\n"
                "Now describe your vehicle or machine fault (e.g. _'Activa pickup low'_ or _'Splendor missing problem'_), and I will send diagnosis and repair videos in your chosen language! 🔧\n\n"
                "_(Type *language* anytime to change it)_",
            )
            return

    # ── Step 5: Send welcome to first-time users or greetings ─
    is_greeting = raw_lower in ("hi", "hello", "hey", "start", "help", "menu")
    if is_new_user or is_greeting:
        await whatsapp.send_welcome(incoming.from_number, incoming.display_name)
        if not user_text or is_greeting:
            return  # Wait for them to describe the fault
        # If they already described a fault on their first message, continue to analysis!

    # ── Step 6: Download media if image was sent ───────────────
    image_bytes: bytes | None = None
    mime_type: str | None = None
    if incoming.media_id and incoming.message_type in ("image", "document"):
        try:
            image_bytes = await whatsapp.download_media(incoming.media_id)
            mime_type = incoming.mime_type or "image/jpeg"
        except Exception as exc:
            logger.warning("Could not download media %s: %s", incoming.media_id, exc)

    # Need at least some text to analyse
    if not user_text and not image_bytes:
        await whatsapp.send_text(
            incoming.from_number,
            "Please describe the fault in words, or send a photo of the broken part. 🔧",
        )
        return

    # ── Step 7: AI Fault Analysis ─────────────────────────────
    await whatsapp.send_text(
        incoming.from_number,
        "🤖 Analysing your fault... please wait a moment.",
    )

    analysis = await ai_engine.analyse_fault(
        conversation_id=conversation_id,
        user_message=user_text or "Analyse this image of a broken part.",
        image_bytes=image_bytes,
        mime_type=mime_type,
    )

    # ── Handle clarification requests ─────────────────────────
    if analysis.needs_clarification:
        question = analysis.clarification_question or (
            "Could you provide more details about the machine and the fault?"
        )
        await whatsapp.send_text(incoming.from_number, f"❓ {question}")
        _save_assistant_message(db, conversation.id, question)
        return

    # ── Step 8: Safety warning ────────────────────────────────
    if analysis.safety_warning:
        await whatsapp.send_text(
            incoming.from_number, f"⚠️ *Safety Warning:* {analysis.safety_warning}"
        )

    # ── Step 9: Enrich parts with DB catalogue ─────────────────
    enriched_parts = await parts_lookup.enrich_parts(analysis.spare_parts, db)

    # ── Step 10: Send parts list ──────────────────────────────
    parts_text = ai_engine.format_parts_text(enriched_parts)

    # Send interactive parts list (if enough parts)
    if len(enriched_parts) >= 2:
        try:
            await whatsapp.send_parts_list(
                to=incoming.from_number,
                fault_summary=analysis.fault_summary or "Fault analysed",
                parts=enriched_parts,
            )
        except Exception:
            # Fallback to plain text if interactive message fails
            await whatsapp.send_text(
                incoming.from_number,
                f"🔧 *Fault:* {analysis.fault_summary}\n\n"
                f"📦 *Spare Parts:*\n{parts_text}",
            )
    else:
        await whatsapp.send_text(
            incoming.from_number,
            f"🔧 *Fault:* {analysis.fault_summary}\n\n"
            f"📦 *Spare Parts:*\n{parts_text}",
        )

    # ── Step 11: Save assistant reply & queries to DB ─────────
    full_reply = f"{analysis.fault_summary}\n\n{parts_text}"
    _save_assistant_message(db, conversation.id, full_reply, {
        "fault_summary": analysis.fault_summary,
        "severity": analysis.severity,
        "parts": enriched_parts,
        "search_queries": analysis.search_queries,
    })

    # Update conversation fault summary
    conversation.fault_summary = analysis.fault_summary
    await db.flush()

    # ── Step 12: Prompt user with language dropdown for videos ─
    await whatsapp.send_language_selection(
        to=incoming.from_number,
        prompt="In which language would you like to watch repair tutorial videos for this issue?",
    )


def _save_assistant_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    content: str,
    metadata: dict | None = None,
) -> None:
    msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        message_type=MessageType.TEXT,
        content=content,
        metadata_=metadata,
    )
    db.add(msg)
