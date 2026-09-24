"""
Announcement endpoints for the High School Management System API
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..database import announcements_collection, teachers_collection

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    start_date: Optional[date] = None
    expiration_date: date

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A mensagem do anúncio não pode ficar em branco")
        return stripped

    @field_validator("expiration_date")
    @classmethod
    def expiration_after_start(cls, value: date, info) -> date:
        start_date = info.data.get("start_date")
        if start_date and value < start_date:
            raise ValueError(
                "A data de expiração deve ser igual ou posterior à data de início")
        return value


def _require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    """Ensure the request is made by an authenticated teacher/admin"""
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize(announcement: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": announcement["_id"],
        "message": announcement["message"],
        "start_date": announcement.get("start_date"),
        "expiration_date": announcement["expiration_date"],
        "created_by": announcement.get("created_by"),
        "created_at": announcement.get("created_at"),
    }


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements currently visible to all visitors (public banner)"""
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [{"start_date": None}, {"start_date": {"$lte": today}}],
    }

    announcements = announcements_collection.find(
        query).sort("created_at", -1)
    return [_serialize(announcement) for announcement in announcements]


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get every announcement (past, active and future) - requires teacher authentication"""
    _require_teacher(teacher_username)

    announcements = announcements_collection.find().sort("created_at", -1)
    return [_serialize(announcement) for announcement in announcements]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement - requires teacher authentication"""
    teacher = _require_teacher(teacher_username)

    doc = {
        "_id": str(uuid.uuid4()),
        "message": payload.message,
        "start_date": payload.start_date.isoformat() if payload.start_date else None,
        "expiration_date": payload.expiration_date.isoformat(),
        "created_by": teacher["_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        announcements_collection.insert_one(doc)
    except Exception:
        logger.exception("Failed to create announcement")
        raise HTTPException(
            status_code=500, detail="Failed to create announcement")

    return _serialize(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement - requires teacher authentication"""
    _require_teacher(teacher_username)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    update = {
        "message": payload.message,
        "start_date": payload.start_date.isoformat() if payload.start_date else None,
        "expiration_date": payload.expiration_date.isoformat(),
    }

    result = announcements_collection.update_one(
        {"_id": announcement_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, Any])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Delete an announcement - requires teacher authentication"""
    _require_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
