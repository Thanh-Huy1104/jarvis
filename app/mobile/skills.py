"""
Fixed Skills for Mobile App
----------------------------
Calendar and Notes management functions
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, delete, update, func
from app.db.session import AsyncSessionLocal
from app.db.models import CalendarEventModel, NoteSectionModel, NoteModel
import logging

logger = logging.getLogger(__name__)


class CalendarSkills:
    """Calendar/Reminder management"""
    
    @staticmethod
    async def create_event(
        user_id: str,
        title: str,
        event_datetime: datetime,
        description: Optional[str] = None,
        duration_minutes: int = 60,
        metadata: Optional[dict] = None
    ) -> Dict:
        """Create a calendar event/reminder"""
        async with AsyncSessionLocal() as session:
            event = CalendarEventModel(
                user_id=user_id,
                title=title,
                description=description,
                event_datetime=event_datetime,
                duration_minutes=duration_minutes,
                extra_data=metadata or {}
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            
            return {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "event_datetime": event.event_datetime.isoformat(),
                "duration_minutes": event.duration_minutes,
                "created_at": event.created_at.isoformat()
            }
    
    @staticmethod
    async def get_events(
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Get calendar events within date range"""
        async with AsyncSessionLocal() as session:
            query = select(CalendarEventModel).where(CalendarEventModel.user_id == user_id)
            
            if start_date:
                query = query.where(CalendarEventModel.event_datetime >= start_date)
            if end_date:
                query = query.where(CalendarEventModel.event_datetime <= end_date)
            
            query = query.order_by(CalendarEventModel.event_datetime).limit(limit)
            result = await session.execute(query)
            events = result.scalars().all()
            
            return [
                {
                    "id": event.id,
                    "title": event.title,
                    "description": event.description,
                    "event_datetime": event.event_datetime.isoformat(),
                    "duration_minutes": event.duration_minutes,
                    "created_at": event.created_at.isoformat()
                }
                for event in events
            ]
    
    @staticmethod
    async def update_event(
        event_id: int,
        user_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        event_datetime: Optional[datetime] = None,
        duration_minutes: Optional[int] = None
    ) -> bool:
        """Update a calendar event"""
        async with AsyncSessionLocal() as session:
            updates = {}
            if title is not None:
                updates["title"] = title
            if description is not None:
                updates["description"] = description
            if event_datetime is not None:
                updates["event_datetime"] = event_datetime
            if duration_minutes is not None:
                updates["duration_minutes"] = duration_minutes
            
            if not updates:
                return False
            
            stmt = (
                update(CalendarEventModel)
                .where(and_(
                    CalendarEventModel.id == event_id,
                    CalendarEventModel.user_id == user_id
                ))
                .values(**updates)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def delete_event(event_id: int, user_id: str) -> bool:
        """Delete a calendar event"""
        async with AsyncSessionLocal() as session:
            stmt = delete(CalendarEventModel).where(
                and_(
                    CalendarEventModel.id == event_id,
                    CalendarEventModel.user_id == user_id
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0


class NoteSkills:
    """Note management with sections"""
    
    @staticmethod
    async def create_section(user_id: str, name: str, description: Optional[str] = None) -> Dict:
        """Create a note section"""
        async with AsyncSessionLocal() as session:
            section = NoteSectionModel(
                user_id=user_id,
                name=name,
                description=description
            )
            session.add(section)
            await session.commit()
            await session.refresh(section)
            
            return {
                "id": section.id,
                "name": section.name,
                "description": section.description,
                "created_at": section.created_at.isoformat()
            }
    
    @staticmethod
    async def get_sections(user_id: str) -> List[Dict]:
        """Get all sections for a user, with a preview of the first 3 notes."""
        async with AsyncSessionLocal() as session:
            # 1. Fetch all sections for the user
            sections_query = (
                select(NoteSectionModel)
                .where(NoteSectionModel.user_id == user_id)
                .order_by(NoteSectionModel.created_at)
            )
            sections_result = await session.execute(sections_query)
            sections = sections_result.scalars().all()
            
            if not sections:
                return []

            # 2. Fetch all notes for the user and group them by section_id
            notes_query = (
                select(NoteModel)
                .where(NoteModel.user_id == user_id)
                .order_by(NoteModel.created_at.desc())
            )
            notes_result = await session.execute(notes_query)
            all_notes = notes_result.scalars().all()
            
            notes_by_section = {}
            for note in all_notes:
                if note.section_id not in notes_by_section:
                    notes_by_section[note.section_id] = []
                notes_by_section[note.section_id].append({
                    "id": note.id,
                    "content": note.content,
                    "created_at": note.created_at.isoformat()
                })

            # 3. Combine sections with their note previews
            result = []
            for section in sections:
                section_data = {
                    "id": section.id,
                    "name": section.name,
                    "description": section.description,
                    "created_at": section.created_at.isoformat(),
                    "notes_preview": notes_by_section.get(section.id, [])[:3]
                }
                result.append(section_data)
            
            return result
    
    @staticmethod
    async def get_section_by_name(user_id: str, name: str) -> Optional[Dict]:
        """Get a section by name"""
        async with AsyncSessionLocal() as session:
            query = (
                select(NoteSectionModel)
                .where(and_(
                    NoteSectionModel.user_id == user_id,
                    NoteSectionModel.name == name
                ))
            )
            result = await session.execute(query)
            section = result.scalar_one_or_none()
            
            if not section:
                return None
            
            return {
                "id": section.id,
                "name": section.name,
                "description": section.description,
                "created_at": section.created_at.isoformat()
            }
    
    @staticmethod
    async def create_note(
        user_id: str,
        section_id: int,
        content: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[dict] = None
    ) -> Dict:
        """Create a note in a section"""
        async with AsyncSessionLocal() as session:
            note = NoteModel(
                user_id=user_id,
                section_id=section_id,
                content=content,
                tags=tags or [],
                metadata=metadata or {}
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            
            return {
                "id": note.id,
                "section_id": note.section_id,
                "content": note.content,
                "tags": note.tags,
                "created_at": note.created_at.isoformat()
            }
    
    @staticmethod
    async def get_notes_by_section(user_id: str, section_id: int, limit: int = 100) -> List[Dict]:
        """Get all notes in a section"""
        async with AsyncSessionLocal() as session:
            query = (
                select(NoteModel)
                .where(and_(
                    NoteModel.user_id == user_id,
                    NoteModel.section_id == section_id
                ))
                .order_by(NoteModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(query)
            notes = result.scalars().all()
            
            return [
                {
                    "id": note.id,
                    "section_id": note.section_id,
                    "content": note.content,
                    "tags": note.tags,
                    "created_at": note.created_at.isoformat()
                }
                for note in notes
            ]
    
    @staticmethod
    async def search_notes(user_id: str, query: str, limit: int = 50) -> List[Dict]:
        """Search notes by content"""
        async with AsyncSessionLocal() as session:
            search_query = (
                select(NoteModel)
                .where(and_(
                    NoteModel.user_id == user_id,
                    NoteModel.content.ilike(f"%{query}%")
                ))
                .order_by(NoteModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(search_query)
            notes = result.scalars().all()
            
            return [
                {
                    "id": note.id,
                    "section_id": note.section_id,
                    "content": note.content,
                    "tags": note.tags,
                    "created_at": note.created_at.isoformat()
                }
                for note in notes
            ]
    
    @staticmethod
    async def delete_note(note_id: int, user_id: str) -> bool:
        """Delete a note"""
        async with AsyncSessionLocal() as session:
            stmt = delete(NoteModel).where(
                and_(
                    NoteModel.id == note_id,
                    NoteModel.user_id == user_id
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def delete_section(section_id: int, user_id: str) -> Dict:
        """
        Delete a note section, but only if it has no notes
        
        Returns:
            Dict with "success" bool and "message" string
        """
        async with AsyncSessionLocal() as session:
            # First check if section has any notes
            count_query = select(func.count()).select_from(NoteModel).where(
                and_(
                    NoteModel.section_id == section_id,
                    NoteModel.user_id == user_id
                )
            )
            result = await session.execute(count_query)
            note_count = result.scalar()
            
            if note_count > 0:
                return {
                    "success": False,
                    "message": f"Cannot delete section - it contains {note_count} note(s). Please delete or move the notes first."
                }
            
            # Section is empty, safe to delete
            stmt = delete(NoteSectionModel).where(
                and_(
                    NoteSectionModel.id == section_id,
                    NoteSectionModel.user_id == user_id
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            
            if result.rowcount > 0:
                return {
                    "success": True,
                    "message": "Section deleted successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Section not found"
                }
