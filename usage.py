"""
تتبّع الاستخدام الشهري وتطبيق حدود الباقات (كما في pricing.js).
مفتاح التتبّع: user_id إن كان مسجّلًا، وإلا session_id (المرسل من الواجهة) أو IP كحل أخير.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from db import usage_col
from deps import get_current_user

router = APIRouter(prefix="/usage", tags=["usage"])

# {tier: {"images": شهريًا, "videos": شهريًا}}  None = غير محدود
LIMITS = {
    "free": {"images": 10, "videos": 3},
    "starter": {"images": 50, "videos": 15},
    "creator": {"images": 200, "videos": 50},
    "pro": {"images": None, "videos": 200},
    "admin": {"images": None, "videos": None},
}


def _current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


async def _usage_key(request: Request, session_id: Optional[str]):
    user = await get_current_user(request)
    if user:
        return f"user:{user['_id']}", user.get("tier", "free")
    key = session_id or request.client.host or "anonymous"
    return f"anon:{key}", "free"


async def check_and_increment_usage(request: Request, session_id: Optional[str], kind: str):
    """kind: 'image' أو 'video'. يرفع HTTPException 429 إذا تجاوز الحد الشهري."""
    key, tier = await _usage_key(request, session_id)
    period = _current_period()
    limit = LIMITS.get(tier, LIMITS["free"]).get(f"{kind}s")

    doc = await usage_col.find_one({"key": key, "period": period})
    used = doc.get(kind + "s", 0) if doc else 0

    if limit is not None and used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"تجاوزت الحد الشهري لباقتك ({limit} {kind}(s)). قم بالترقية للمتابعة.",
        )

    await usage_col.update_one(
        {"key": key, "period": period},
        {"$inc": {f"{kind}s": 1}, "$set": {"tier": tier}},
        upsert=True,
    )


@router.get("/me")
async def usage_me(request: Request):
    key, tier = await _usage_key(request, request.query_params.get("session_id"))
    period = _current_period()
    doc = await usage_col.find_one({"key": key, "period": period}) or {}
    limits = LIMITS.get(tier, LIMITS["free"])
    return {
        "tier": tier,
        "period": period,
        "images_used": doc.get("images", 0),
        "images_limit": limits["images"],
        "videos_used": doc.get("videos", 0),
        "videos_limit": limits["videos"],
    }
