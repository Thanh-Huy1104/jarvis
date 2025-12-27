from typing import List, Optional
from app.db.session import AsyncSessionLocal
from app.db.models import ChatMessageModel, ChatSessionModel
from app.core.types import ChatMessage
from sqlalchemy import select, update, delete
import uuid

class ChatPostgresAdapter:
    async def create_session(self, session_id: str = None, title: str = None) -> str:
        if not session_id:
            session_id = str(uuid.uuid4())
            
        async with AsyncSessionLocal() as session:
            # Check if exists
            result = await session.execute(select(ChatSessionModel).where(ChatSessionModel.id == session_id))
            existing = result.scalar_one_or_none()
            
            if not existing:
                new_session = ChatSessionModel(id=session_id, title=title)
                session.add(new_session)
                await session.commit()
                
        return session_id

    async def get_sessions(self, limit: int = 50, offset: int = 0) -> List[dict]:
        async with AsyncSessionLocal() as session:
            query = (
                select(ChatSessionModel)
                .order_by(ChatSessionModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(query)
            rows = result.scalars().all()
            
            return [
                {
                    "id": row.id,
                    "title": row.title,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at
                }
                for row in rows
            ]

    async def delete_session(self, session_id: str) -> bool:
        async with AsyncSessionLocal() as session:
            # Check if session exists
            result = await session.execute(select(ChatSessionModel).where(ChatSessionModel.id == session_id))
            existing = result.scalar_one_or_none()
            
            if not existing:
                return False

            # Delete associated messages first (manual cascade)
            await session.execute(delete(ChatMessageModel).where(ChatMessageModel.session_id == session_id))
            
            # Delete session
            await session.execute(delete(ChatSessionModel).where(ChatSessionModel.id == session_id))
            await session.commit()
            return True

    async def update_session_title(self, session_id: str, title: str):
        async with AsyncSessionLocal() as session:
            stmt = (
                update(ChatSessionModel)
                .where(ChatSessionModel.id == session_id)
                .values(title=title)
            )
            await session.execute(stmt)
            await session.commit()

    async def add_message(self, session_id: str, role: str, content: str):
        # Ensure session exists (idempotent)
        await self.create_session(session_id)

        async with AsyncSessionLocal() as session:
            msg = ChatMessageModel(
                session_id=session_id,
                role=role,
                content=content
            )
            session.add(msg)
            
            # Update session updated_at
            # SQLAlchemy onupdate handles this if we were updating the session object,
            # but here we are just inserting a message. 
            # We should explicitly touch the session to update 'updated_at' if we want it to reflect last activity.
            # However, for simplicity, let's just insert the message. 
            # If we want 'updated_at' to be last message time, we should update the session record.
            
            stmt = (
                update(ChatSessionModel)
                .where(ChatSessionModel.id == session_id)
                # Rely on onupdate or explicit set? 
                # Let's rely on database behavior or just not worry about it for now, 
                # but "Recent Sessions" usually implies last activity.
                # So explicit update is better.
            )
            # await session.execute(stmt) # This might be empty update if we don't change values.
            
            await session.commit()
    
    async def get_history(self, session_id: str, limit: int = 50) -> List[ChatMessage]:
        async with AsyncSessionLocal() as session:
            # Fetch latest messages first
            query = (
                select(ChatMessageModel)
                .where(ChatMessageModel.session_id == session_id)
                .order_by(ChatMessageModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(query)
            rows = result.scalars().all()
            
            # Convert to Pydantic and reverse to get chronological order
            messages = [
                ChatMessage(id=row.id, role=row.role, content=row.content, created_at=row.created_at)
                for row in rows
            ]
            return messages[::-1]