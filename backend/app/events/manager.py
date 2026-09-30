import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.entities import ExecutionEvent

class EventBroadcaster:
    """In-memory event hub for SSE clients and database event persistence."""

    def __init__(self):
        # Map execution_id -> list of asyncio.Queue for connected SSE clients
        self._listeners: Dict[str, List[asyncio.Queue]] = {}

    def subscribe(self, execution_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        if execution_id not in self._listeners:
            self._listeners[execution_id] = []
        self._listeners[execution_id].append(q)
        return q

    def unsubscribe(self, execution_id: str, q: asyncio.Queue):
        if execution_id in self._listeners:
            if q in self._listeners[execution_id]:
                self._listeners[execution_id].remove(q)
            if not self._listeners[execution_id]:
                del self._listeners[execution_id]

    async def emit(
        self,
        db: AsyncSession,
        execution_id: str,
        event_type: str,
        message: str,
        task_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ExecutionEvent:
        # Determine next sequence number
        stmt = (
            select(ExecutionEvent.seq)
            .where(ExecutionEvent.execution_id == execution_id)
            .order_by(ExecutionEvent.seq.desc())
            .limit(1)
        )
        res = await db.execute(stmt)
        last_seq = res.scalar_one_or_none() or 0
        new_seq = last_seq + 1

        event = ExecutionEvent(
            execution_id=execution_id,
            seq=new_seq,
            type=event_type,
            timestamp=datetime.now(timezone.utc),
            task_id=task_id,
            tool_id=tool_id,
            message=message,
            params=params or {},
            payload=payload or {}
        )
        db.add(event)
        await db.commit()

        # Broadcast to active SSE listeners
        if execution_id in self._listeners:
            data = {
                "id": event.id,
                "seq": event.seq,
                "type": event.type,
                "timestamp": event.timestamp.isoformat(),
                "task_id": event.task_id,
                "tool_id": event.tool_id,
                "message": event.message,
                "params": event.params,
                "payload": event.payload,
            }
            for q in list(self._listeners[execution_id]):
                await q.put(data)

        return event

event_broadcaster = EventBroadcaster()
