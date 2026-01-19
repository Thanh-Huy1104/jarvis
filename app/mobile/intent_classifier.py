"""
Simplified Intent Classifier for Mobile App
--------------------------------------------
Uses LLM to classify voice input and extract structured data
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from dateutil import parser as date_parser
import re

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Classifies user intent and extracts structured data"""
    
    INTENT_SYSTEM_PROMPT = """You are an intent classifier for a voice-based mobile app that manages reminders and notes.

Your job is to analyze user voice input and:
1. Classify the intent as one of: "create_reminder", "create_note", "create_section", "view_calendar", "view_notes", "other"
2. Extract relevant structured data

For "create_reminder":
- Extract: title, datetime (in ISO format), description, duration_minutes
- Parse natural language dates like "tomorrow at 3pm", "next Monday at 9am", "in 2 hours"

For "create_note":
- Extract: content, section_name (the category/folder for the note), tags (list)
- If no section is mentioned, set section_name to "General"

For "create_section":
- Extract: name (the section/category name), description (optional)
- Use this intent when user explicitly wants to create a new category/folder/section for organizing notes
- Examples: "Create a new section called X", "Make a new category for Y", "Add a folder for Z"

For "view_calendar":
- Extract: start_date, end_date, or time_period (today, tomorrow, this_week, next_week)

For "view_notes":
- Extract: section_name (if specified), search_query

Respond ONLY with valid JSON in this format:
{{
    "intent": "create_reminder|create_note|create_section|view_calendar|view_notes|other",
    "confidence": 0.0-1.0,
    "data": {{
        // relevant fields based on intent
    }},
    "needs_clarification": false,
    "clarification_question": null,
    "section_exists": null  // will be filled by system
}}

Current datetime: {current_datetime}
Today is: {today}

Examples:
Input: "Remind me to buy groceries tomorrow at 5pm"
Output: {{"intent": "create_reminder", "confidence": 0.95, "data": {{"title": "Buy groceries", "datetime": "2026-01-19T17:00:00", "description": "Reminder to buy groceries", "duration_minutes": 30}}, "needs_clarification": false}}

Input: "Note that the meeting went well and we decided to launch in Q2"
Output: {{"intent": "create_note", "confidence": 0.9, "data": {{"content": "Meeting went well and we decided to launch in Q2", "section_name": "General", "tags": ["meeting", "Q2"]}}, "needs_clarification": false}}

Input: "Add to my work notes: follow up with John about the presentation"
Output: {{"intent": "create_note", "confidence": 0.95, "data": {{"content": "Follow up with John about the presentation", "section_name": "Work", "tags": ["work", "follow-up"]}}, "needs_clarification": false}}

Input: "Create a new section called Shopping List"
Output: {{"intent": "create_section", "confidence": 0.95, "data": {{"name": "Shopping List", "description": ""}}, "needs_clarification": false}}

Input: "What do I have scheduled tomorrow?"
Output: {{"intent": "view_calendar", "confidence": 0.9, "data": {{"time_period": "tomorrow"}}, "needs_clarification": false}}
"""
    
    def __init__(self, llm):
        """Initialize with LLM adapter"""
        self.llm = llm
    
    async def classify_intent(self, user_input: str, user_id: Optional[str] = None) -> Dict:
        """
        Classify user intent and extract structured data
        
        Args:
            user_input: The user's voice input as text
            user_id: Optional user ID for context
            
        Returns:
            Dictionary with intent, confidence, data, and clarification info
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        
        # Get current datetime for context
        now = datetime.now()
        today = now.strftime("%A, %B %d, %Y")
        current_datetime = now.isoformat()
        
        system_prompt = self.INTENT_SYSTEM_PROMPT.format(
            current_datetime=current_datetime,
            today=today
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User input: {user_input}")
        ]
        
        try:
            # Get LLM response
            response = await self.llm.ainvoke(messages)
            content = response.content.strip()
            
            logger.info(f"Raw LLM response (first 1000 chars): {content[:1000]}")
            
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end == -1:
                    logger.error("Found ```json but no closing ```")
                    content = content[json_start:].strip()
                else:
                    content = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                if json_end == -1:
                    logger.error("Found ``` but no closing ```")
                    content = content[json_start:].strip()
                else:
                    content = content[json_start:json_end].strip()
            
            logger.info(f"Extracted content for JSON parsing: {content}")
            
            # Try to parse JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError as je:
                logger.error(f"JSON parsing failed: {je}")
                logger.error(f"Content that failed to parse: {repr(content)}")
                raise
            
            # Validate result structure
            if "intent" not in result:
                logger.error(f"Invalid intent classification result: {result}")
                return {
                    "intent": "other",
                    "confidence": 0.0,
                    "data": {},
                    "needs_clarification": False,
                    "error": "Invalid classification format"
                }
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse intent classification JSON: {e}")
            logger.error(f"JSON content was: {repr(content)}")
            return {
                "intent": "other",
                "confidence": 0.0,
                "data": {},
                "needs_clarification": False,
                "error": f"JSON parse error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Intent classification error: {e}", exc_info=True)
            return {
                "intent": "other",
                "confidence": 0.0,
                "data": {},
                "needs_clarification": False,
                "error": str(e)
            }
    
    @staticmethod
    def parse_datetime(datetime_str: Optional[str], base_datetime: Optional[datetime] = None) -> Optional[datetime]:
        """
        Parse datetime string (ISO format or natural language)
        
        Args:
            datetime_str: String representation of datetime
            base_datetime: Base datetime for relative calculations
            
        Returns:
            Parsed datetime or None
        """
        if not datetime_str:
            return None
        
        base = base_datetime or datetime.now()
        
        try:
            # Try ISO format first
            return datetime.fromisoformat(datetime_str)
        except:
            pass
        
        try:
            # Try dateutil parser for natural language
            return date_parser.parse(datetime_str, default=base)
        except:
            logger.warning(f"Could not parse datetime: {datetime_str}")
            return None


class MobileIntentHandler:
    """Handles intent execution with section management"""
    
    def __init__(self, calendar_skills, note_skills):
        """
        Initialize handler
        
        Args:
            calendar_skills: CalendarSkills instance
            note_skills: NoteSkills instance
        """
        self.calendar = calendar_skills
        self.notes = note_skills
    
    async def handle_create_reminder(self, user_id: str, data: Dict) -> Dict:
        """Handle create_reminder intent"""
        try:
            # Parse datetime
            event_datetime = IntentClassifier.parse_datetime(data.get("datetime"))
            if not event_datetime:
                return {
                    "success": False,
                    "error": "Could not parse datetime",
                    "needs_clarification": True,
                    "clarification_question": "When would you like to be reminded?"
                }
            
            result = await self.calendar.create_event(
                user_id=user_id,
                title=data.get("title", "Reminder"),
                event_datetime=event_datetime,
                description=data.get("description"),
                duration_minutes=data.get("duration_minutes", 30)
            )
            
            return {
                "success": True,
                "data": result,
                "message": f"Reminder created: {result['title']} at {event_datetime.strftime('%B %d at %I:%M %p')}"
            }
        except Exception as e:
            logger.error(f"Error creating reminder: {e}")
            return {"success": False, "error": str(e)}
    
    async def handle_create_note(self, user_id: str, data: Dict) -> Dict:
        """Handle create_note intent with section management"""
        try:
            section_name = data.get("section_name", "General")
            
            # Check if section exists
            section = await self.notes.get_section_by_name(user_id, section_name)
            
            if not section:
                # Section doesn't exist - ask user if they want to create it
                return {
                    "success": False,
                    "needs_section_creation": True,
                    "section_name": section_name,
                    "clarification_question": f"The section '{section_name}' doesn't exist. Would you like to create it?",
                    "pending_data": data  # Store the note data for after section creation
                }
            
            # Section exists, create the note
            result = await self.notes.create_note(
                user_id=user_id,
                section_id=section["id"],
                content=data.get("content", ""),
                tags=data.get("tags", [])
            )
            
            return {
                "success": True,
                "data": result,
                "message": f"Note added to {section_name}"
            }
        except Exception as e:
            logger.error(f"Error creating note: {e}")
            return {"success": False, "error": str(e)}
    
    async def handle_view_calendar(self, user_id: str, data: Dict) -> Dict:
        """Handle view_calendar intent"""
        try:
            now = datetime.now()
            time_period = data.get("time_period", "today")
            
            # Calculate date range based on time period
            if time_period == "today":
                start_date = now.replace(hour=0, minute=0, second=0)
                end_date = now.replace(hour=23, minute=59, second=59)
            elif time_period == "tomorrow":
                tomorrow = now + timedelta(days=1)
                start_date = tomorrow.replace(hour=0, minute=0, second=0)
                end_date = tomorrow.replace(hour=23, minute=59, second=59)
            elif time_period == "this_week":
                start_date = now - timedelta(days=now.weekday())
                end_date = start_date + timedelta(days=6)
            else:
                start_date = data.get("start_date")
                end_date = data.get("end_date")
                if start_date:
                    start_date = IntentClassifier.parse_datetime(start_date)
                if end_date:
                    end_date = IntentClassifier.parse_datetime(end_date)
            
            events = await self.calendar.get_events(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date
            )
            
            return {
                "success": True,
                "data": events,
                "message": f"Found {len(events)} event(s)"
            }
        except Exception as e:
            logger.error(f"Error viewing calendar: {e}")
            return {"success": False, "error": str(e)}
    
    async def handle_view_notes(self, user_id: str, data: Dict) -> Dict:
        """Handle view_notes intent"""
        try:
            section_name = data.get("section_name")
            search_query = data.get("search_query")
            
            if search_query:
                notes = await self.notes.search_notes(user_id, search_query)
                message = f"Found {len(notes)} note(s) matching '{search_query}'"
            elif section_name:
                section = await self.notes.get_section_by_name(user_id, section_name)
                if not section:
                    return {
                        "success": False,
                        "error": f"Section '{section_name}' not found"
                    }
                notes = await self.notes.get_notes_by_section(user_id, section["id"])
                message = f"Found {len(notes)} note(s) in {section_name}"
            else:
                # Get all sections
                sections = await self.notes.get_sections(user_id)
                return {
                    "success": True,
                    "data": {"sections": sections},
                    "message": f"You have {len(sections)} section(s)"
                }
            
            return {
                "success": True,
                "data": {"notes": notes},
                "message": message
            }
        except Exception as e:
            logger.error(f"Error viewing notes: {e}")
            return {"success": False, "error": str(e)}
