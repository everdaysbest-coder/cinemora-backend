"""Dependencies مشتركة (مثل معرفة المستخدم الحالي) بمعزل عن الراوترات
لتفادي circular imports بين auth.py و referral.py وغيرهما."""
import os
from datetime import datetime, timezone

from fastapi import Request

from db import sessions_col, users_col

SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cinemora_session")


async def get_current_user(request: Request):
    """يرجّع بيانات المستخدم الحالي (dict) من كوكي الجلسة، أو None إذا زائر."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    session = await sessions_col.find_one({"session_token": token})
    if not session:
        return None
    if session["expires_at"] < datetime.now(timezone.utc):
        return None
    return await users_col.find_one({"_id": session["user_id"]})
