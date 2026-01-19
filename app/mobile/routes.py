"""
Mobile API Routes
-----------------
RESTful API endpoints for the mobile app (Expo/React Native)
"""

import asyncio
import json
import logging
import io
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Body
from pydantic import BaseModel, Field
from app.mobile.skills import CalendarSkills, NoteSkills
from app.mobile.intent_classifier import IntentClassifier, MobileIntentHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mobile", tags=["mobile"])


# Request/Response Models
class ChatRequest(BaseModel):
    message: str

class VoiceToActionRequest(BaseModel):
    """Voice input for intent processing"""
    user_id: str
    audio_base64: Optional[str] = None  # Optional: base64 encoded audio
    text: Optional[str] = None  # Optional: already transcribed text


class CreateReminderRequest(BaseModel):
    user_id: str
    title: str
    datetime: str  # ISO format
    description: Optional[str] = None
    duration_minutes: int = 60


class CreateNoteRequest(BaseModel):
    user_id: str
    section_name: str
    content: str
    tags: Optional[list] = []


class CreateSectionRequest(BaseModel):
    user_id: str
    name: str
    description: Optional[str] = None


class ConfirmSectionCreationRequest(BaseModel):
    user_id: str
    section_name: str
    description: Optional[str] = None
    pending_note_data: Optional[dict] = None  # If this was triggered by a note creation


# Chat Endpoint
@router.post("/chat")
async def chat(request: Request, data: ChatRequest):
    """
    Handle chat messages from the mobile app.
    """
    try:
        user_id = "default-user" # Replace with actual user management
        text = data.message

        # Step 1: Classify intent
        llm = request.app.state.llm
        if not llm:
            raise HTTPException(status_code=503, detail="LLM service not available")

        classifier = IntentClassifier(llm)
        logger.info(f"Classifying intent for message: {text}")
        intent_result = await classifier.classify_intent(text, user_id)
        logger.info(f"Intent result: {intent_result}")

        # Check if LLM itself needs clarification
        if intent_result.get("needs_clarification") and intent_result.get("clarification_question"):
            return {
                "response": intent_result.get("clarification_question"),
                "intent": intent_result.get("intent"),
                "confidence": intent_result.get("confidence"),
                "result": {
                    "success": False,
                    "needs_clarification": True,
                    "clarification_question": intent_result.get("clarification_question"),
                    "pending_data": intent_result.get("data")
                }
            }

        # Step 2: Execute based on intent
        handler = MobileIntentHandler(CalendarSkills, NoteSkills)

        intent = intent_result.get("intent")
        intent_data = intent_result.get("data", {})

        if intent == "create_reminder":
            result = await handler.handle_create_reminder(user_id, intent_data)
        elif intent == "create_note":
            result = await handler.handle_create_note(user_id, intent_data)
        elif intent == "create_section":
            result = await handler.handle_create_section(user_id, intent_data)
        elif intent == "view_calendar":
            result = await handler.handle_view_calendar(user_id, intent_data)
        elif intent == "view_notes":
            result = await handler.handle_view_notes(user_id, intent_data)
        else:
            result = {
                "success": False,
                "message": "I couldn't understand that. Please try asking about reminders, notes, or your calendar.",
                "intent": intent,
                "confidence": intent_result.get("confidence", 0)
            }
        print(result)

        return {
            "response": result.get("message", "I'm not sure how to respond to that."),
            "intent": intent,
            "confidence": intent_result.get("confidence"),
            "result": result
        }

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Voice & Intent Endpoints
@router.post("/voice-to-text")
async def voice_to_text(request: Request, audio: UploadFile = File(...)):
    """
    Convert voice audio to text using Whisper STT
    
    Accepts audio file upload and returns transcribed text
    """
    try:
        stt = request.app.state.stt
        if not stt:
            raise HTTPException(status_code=503, detail="Speech-to-text service not available")
        
        # Read audio bytes
        audio_bytes = await audio.read()
        
        # Transcribe using Whisper
        text = await stt.transcribe_async(audio_bytes, filename=audio.filename)
        
        return {
            "success": True,
            "text": text,
            "filename": audio.filename
        }
    except Exception as e:
        logger.error(f"Voice-to-text error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice-to-action")
async def voice_to_action(request: Request, data: VoiceToActionRequest):
    """
    Full voice processing pipeline:
    1. Convert audio to text (if audio provided)
    2. Classify intent
    3. Execute action
    
    This is the main endpoint for mobile voice interaction
    """
    try:
        user_id = data.user_id
        text = data.text
        
        # Step 1: Transcribe if audio provided
        if data.audio_base64 and not text:
            import base64
            stt = request.app.state.stt
            if not stt:
                raise HTTPException(status_code=503, detail="STT service not available")
            
            audio_bytes = base64.b64decode(data.audio_base64)
            text = await stt.transcribe_async(audio_bytes)
        
        if not text:
            raise HTTPException(status_code=400, detail="No text or audio provided")
        
        # Step 2: Classify intent
        llm = request.app.state.llm
        if not llm:
            raise HTTPException(status_code=503, detail="LLM service not available")
        
        classifier = IntentClassifier(llm)
        intent_result = await classifier.classify_intent(text, user_id)
        
        # Step 3: Execute based on intent
        handler = MobileIntentHandler(CalendarSkills, NoteSkills)
        
        intent = intent_result.get("intent")
        intent_data = intent_result.get("data", {})
        
        if intent == "create_reminder":
            result = await handler.handle_create_reminder(user_id, intent_data)
        elif intent == "create_note":
            result = await handler.handle_create_note(user_id, intent_data)
        elif intent == "view_calendar":
            result = await handler.handle_view_calendar(user_id, intent_data)
        elif intent == "view_notes":
            result = await handler.handle_view_notes(user_id, intent_data)
        else:
            result = {
                "success": False,
                "message": "I couldn't understand that. Please try asking about reminders, notes, or your calendar.",
                "intent": intent,
                "confidence": intent_result.get("confidence", 0)
            }
        
        return {
            "transcribed_text": text,
            "intent": intent,
            "confidence": intent_result.get("confidence"),
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Voice-to-action error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Calendar Endpoints
@router.post("/calendar/events")
async def create_calendar_event(data: CreateReminderRequest):
    """Create a calendar event/reminder"""
    try:
        event_datetime = IntentClassifier.parse_datetime(data.datetime)
        if not event_datetime:
            raise HTTPException(status_code=400, detail="Invalid datetime format")
        
        result = await CalendarSkills.create_event(
            user_id=data.user_id,
            title=data.title,
            event_datetime=event_datetime,
            description=data.description,
            duration_minutes=data.duration_minutes
        )
        return result
    except Exception as e:
        logger.error(f"Create calendar event error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar/events/{user_id}")
async def get_calendar_events(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50
):
    """Get calendar events for a user"""
    try:
        start = IntentClassifier.parse_datetime(start_date) if start_date else None
        end = IntentClassifier.parse_datetime(end_date) if end_date else None
        
        events = await CalendarSkills.get_events(
            user_id=user_id,
            start_date=start,
            end_date=end,
            limit=limit
        )
        return {"events": events}
    except Exception as e:
        logger.error(f"Get calendar events error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/calendar/events/{event_id}")
async def update_calendar_event(
    event_id: int,
    user_id: str = Body(...),
    title: Optional[str] = Body(None),
    description: Optional[str] = Body(None),
    datetime: Optional[str] = Body(None),
    duration_minutes: Optional[int] = Body(None)
):
    """Update a calendar event"""
    try:
        event_datetime = IntentClassifier.parse_datetime(datetime) if datetime else None
        
        success = await CalendarSkills.update_event(
            event_id=event_id,
            user_id=user_id,
            title=title,
            description=description,
            event_datetime=event_datetime,
            duration_minutes=duration_minutes
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Event not found")
        
        return {"success": True, "message": "Event updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update calendar event error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(event_id: int, user_id: str):
    """Delete a calendar event"""
    try:
        success = await CalendarSkills.delete_event(event_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Event not found")
        return {"success": True, "message": "Event deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete calendar event error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Note Section Endpoints
@router.post("/notes/sections")
async def create_note_section(data: CreateSectionRequest):
    """Create a new note section"""
    try:
        result = await NoteSkills.create_section(
            user_id=data.user_id,
            name=data.name,
            description=data.description
        )
        return result
    except Exception as e:
        logger.error(f"Create section error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notes/sections/{user_id}")
async def get_note_sections(user_id: str):
    """Get all note sections for a user"""
    try:
        sections = await NoteSkills.get_sections(user_id)
        return {"sections": sections}
    except Exception as e:
        logger.error(f"Get sections error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notes/sections/confirm")
async def confirm_section_creation(data: ConfirmSectionCreationRequest):
    """
    Confirm creation of a new section (used when voice intent asks to create)
    Optionally creates the pending note after section creation
    """
    try:
        # Create the section
        section = await NoteSkills.create_section(
            user_id=data.user_id,
            name=data.section_name,
            description=data.description
        )
        
        result = {
            "success": True,
            "section": section
        }
        
        # If there was a pending note, create it now
        if data.pending_note_data:
            note = await NoteSkills.create_note(
                user_id=data.user_id,
                section_id=section["id"],
                content=data.pending_note_data.get("content", ""),
                tags=data.pending_note_data.get("tags", [])
            )
            result["note"] = note
            result["message"] = f"Created section '{data.section_name}' and added your note"
        else:
            result["message"] = f"Created section '{data.section_name}'"
        
        return result
    except Exception as e:
        logger.error(f"Confirm section creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Note Endpoints
@router.post("/notes")
async def create_note(data: CreateNoteRequest):
    """Create a note in a section"""
    try:
        # Check if section exists
        section = await NoteSkills.get_section_by_name(data.user_id, data.section_name)
        if not section:
            raise HTTPException(
                status_code=404,
                detail=f"Section '{data.section_name}' not found. Create it first."
            )
        
        result = await NoteSkills.create_note(
            user_id=data.user_id,
            section_id=section["id"],
            content=data.content,
            tags=data.tags
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create note error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notes/{user_id}/section/{section_id}")
async def get_notes_by_section(user_id: str, section_id: int, limit: int = 100):
    """Get all notes in a specific section"""
    try:
        notes = await NoteSkills.get_notes_by_section(user_id, section_id, limit)
        return {"notes": notes}
    except Exception as e:
        logger.error(f"Get notes by section error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notes/{user_id}/search")
async def search_notes(user_id: str, q: str, limit: int = 50):
    """Search notes by content"""
    try:
        notes = await NoteSkills.search_notes(user_id, q, limit)
        return {"notes": notes, "query": q}
    except Exception as e:
        logger.error(f"Search notes error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notes/{note_id}")
async def delete_note(note_id: int, user_id: str):
    """Delete a note"""
    try:
        success = await NoteSkills.delete_note(note_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Note not found")
        return {"success": True, "message": "Note deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete note error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health check
@router.get("/health")
async def mobile_health_check():
    """Health check for mobile API"""
    return {
        "status": "healthy",
        "service": "mobile-api",
        "timestamp": datetime.now().isoformat()
    }