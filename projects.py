"""راوتر /projects — إنشاء وعرض والإعجاب بالمشاريع."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from db import projects_col
from deps import get_current_user

router = APIRouter(prefix="/projects", tags=["projects"])


def _serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = doc.pop("_id", None) or doc.get("id")
    return doc


@router.get("")
async def list_projects(limit: int = 12):
    cursor = projects_col.find({"public": True}).sort("created_at", -1).limit(limit)
    items = [_serialize(doc) async for doc in cursor]
    return items


@router.post("")
async def create_project(request: Request):
    body = await request.json()
    user = await get_current_user(request)

    doc = {
        "id": str(uuid.uuid4()),
        "title": body.get("title", "Untitled"),
        "author": (user or {}).get("name") or body.get("author", "@you"),
        "prompt": body.get("prompt"),
        "kind": body.get("kind", "image"),
        "image_base64": body.get("image_base64"),
        "image_url": body.get("image_url"),
        "public": body.get("public", True),
        "likes": 0,
        "user_id": user["_id"] if user else None,
        "created_at": datetime.now(timezone.utc),
    }
    await projects_col.insert_one({**doc, "_id": doc["id"]})
    return _serialize(doc)


@router.post("/{project_id}/like")
async def like_project(project_id: str):
    result = await projects_col.update_one({"_id": project_id}, {"$inc": {"likes": 1}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="مشروع غير موجود")
    doc = await projects_col.find_one({"_id": project_id})
    return {"id": project_id, "likes": doc["likes"]}
