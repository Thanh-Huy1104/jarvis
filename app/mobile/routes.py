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


class CreateSectionRequest(BaseModel):
    user_id: str
    name: str
    description: Optional[str] = None


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
        elif intent == "delete_reminder":
            result = await handler.handle_delete_reminder(user_id, intent_data)
        elif intent == "create_note":
            result = await handler.handle_create_note(user_id, intent_data)
        elif intent == "delete_note":
            result = await handler.handle_delete_note(user_id, intent_data)
        elif intent == "create_section":
            result = await handler.handle_create_section(user_id, intent_data)
        elif intent == "delete_section":
            result = await handler.handle_delete_section(user_id, intent_data)
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

        # Ensure result is JSON-serializable (convert any remaining objects)
        response_data = {
            "response": result.get("message", "I'm not sure how to respond to that."),
            "intent": intent,
            "confidence": intent_result.get("confidence"),
            "result": {
                "success": result.get("success"),
                "message": result.get("message"),
                "needs_clarification": result.get("needs_clarification"),
                "needs_section_creation": result.get("needs_section_creation"),
                "clarification_question": result.get("clarification_question"),
                "section_name": result.get("section_name"),
                "pending_data": result.get("pending_data"),
                "error": result.get("error")
            }
        }
        
        # Only include data if it's simple types (not SQLAlchemy models)
        if "data" in result and isinstance(result["data"], dict):
            response_data["result"]["data"] = result["data"]
        
        return response_data

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Calendar Endpoints
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


# Note Endpoints
@router.get("/notes/{user_id}/section/{section_id}")
async def get_notes_by_section(user_id: str, section_id: int, limit: int = 100):
    """Get all notes in a specific section"""
    try:
        notes = await NoteSkills.get_notes_by_section(user_id, section_id, limit)
        return {"notes": notes}
    except Exception as e:
        logger.error(f"Get notes by section error: {e}")
        raise HTTPException(status_code=500, detail=str(e))