"""راوتر ميزات المجتمع: /presets, /explore, /share/{id}, /trending, /stats, /signup."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from db import newsletter_col, projects_col, users_col, video_jobs_col

router = APIRouter(tags=["community"])

# مطابق لـ VIRAL_PRESETS في frontend/src/mock.js — انقلها هنا كمصدر حقيقي بدل mock
# إن أردت تحديثها من لوحة تحكم لاحقًا حوّلها لمجموعة Mongo خاصة بها.
VIRAL_PRESETS = [
    {"id": "agamemnon", "title": "Agamemnon"},
    {"id": "ink-riot", "title": "Ink Riot"},
    {"id": "fallen-angel", "title": "Fallen Angel"},
    {"id": "comic", "title": "Comic"},
    {"id": "cold-vision", "title": "Cold vision"},
    {"id": "particles", "title": "Particles"},
    {"id": "mighty", "title": "Mighty Fighter"},
    {"id": "pigeons", "title": "Pigeons"},
    {"id": "earth-zoom", "title": "Earth Zoom"},
    {"id": "bullet-time", "title": "Bullet time"},
    {"id": "fairytale", "title": "Fairytale Castle"},
    {"id": "cyclope", "title": "Cyclope"},
]


@router.get("/presets")
async def list_presets():
    return VIRAL_PRESETS


@router.get("/explore")
async def explore(kind: Optional[str] = None, limit: int = 24):
    query = {"public": True}
    if kind:
        query["kind"] = kind
    cursor = projects_col.find(query).sort("created_at", -1).limit(limit)
    items = []
    async for doc in cursor:
        doc["id"] = doc.pop("_id")
        items.append(doc)
    return items


@router.get("/share/{project_id}")
async def get_shared_project(project_id: str):
    doc = await projects_col.find_one({"_id": project_id})
    if not doc:
        raise HTTPException(status_code=404, detail="غير موجود")
    doc["id"] = doc.pop("_id")
    return doc


@router.get("/trending")
async def trending(limit: int = 20):
    cursor = projects_col.find({"public": True}).sort("likes", -1).limit(limit)
    items = []
    async for doc in cursor:
        doc["id"] = doc.pop("_id")
        items.append(doc)
    return items


@router.get("/stats")
async def stats():
    users_count = await users_col.count_documents({})
    projects_count = await projects_col.count_documents({})
    videos_count = await video_jobs_col.count_documents({"status": "completed"})
    return {
        "users": users_count,
        "projects": projects_count,
        "videos_generated": videos_count,
    }


@router.post("/signup")
async def signup(request: Request):
    body = await request.json()
    email = body.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="email مطلوب")
    await newsletter_col.update_one(
        {"email": email},
        {"$setOnInsert": {"email": email, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"ok": True}
