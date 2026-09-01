"""نظام الإحالة (Referrals)."""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from db import referrals_col, users_col
from deps import get_current_user

router = APIRouter(prefix="/referral", tags=["referral"])


def _generate_code() -> str:
    return secrets.token_hex(4)


async def _get_or_create_referral_doc(user_id):
    doc = await referrals_col.find_one({"user_id": user_id})
    if doc:
        return doc
    code = _generate_code()
    while await referrals_col.find_one({"code": code}):
        code = _generate_code()
    new_doc = {
        "user_id": user_id,
        "code": code,
        "referred_count": 0,
        "created_at": datetime.now(timezone.utc),
    }
    await referrals_col.insert_one(new_doc)
    return new_doc


async def maybe_apply_referral(new_user_id, code: str) -> bool:
    """يُستدعى عند إنشاء حساب جديد إذا كان معه كود إحالة."""
    referrer_doc = await referrals_col.find_one({"code": code})
    if not referrer_doc:
        return False
    if referrer_doc["user_id"] == new_user_id:
        return False
    await referrals_col.update_one(
        {"_id": referrer_doc["_id"]}, {"$inc": {"referred_count": 1}}
    )
    await users_col.update_one(
        {"_id": new_user_id}, {"$set": {"referred_by": referrer_doc["user_id"]}}
    )
    return True


@router.get("/me")
async def my_referral(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="غير مسجل الدخول")
    doc = await _get_or_create_referral_doc(user["_id"])
    return {
        "code": doc["code"],
        "referred_count": doc.get("referred_count", 0),
    }


@router.post("/apply")
async def apply_referral(request: Request):
    body = await request.json()
    code = body.get("code")
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="غير مسجل الدخول")
    if not code:
        raise HTTPException(status_code=400, detail="code مطلوب")
    applied = await maybe_apply_referral(user["_id"], code)
    return {"applied": applied}
