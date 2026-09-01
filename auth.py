"""
المصادقة عبر Emergent OAuth
============================
تدفق الدخول (كما في authApi.js الأصلي):
1. الواجهة تحوّل المستخدم إلى https://auth.emergentagent.com/?redirect=<origin>
2. Emergent يعيد التوجيه بعد تسجيل الدخول مع session_id في الرابط (fragment/query)
3. الواجهة تستدعي POST /api/auth/session { session_id, referral_code }
4. الباك اند يستبدل session_id ببيانات المستخدم عبر خدمة Emergent الداخلية،
   وينشئ جلسة محلية (كوكي httpOnly).

⚠️ الرابط `https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data`
   والهيدر `X-Session-ID` هما النمط المعروف لمنصة emergent.sh لهذا النوع من
   المشاريع. لم يكن الباك اند الأصلي مرفوعًا لأتحقق منه حرفيًا، لذا إن فشل
   الاستبدال (exchange) بخطأ اتصال/401، تأكد من هذا العنوان تحديدًا مع فريق
   Emergent أو من لوحة التحكم الخاصة بمشروعك.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from db import sessions_col, users_col
from deps import get_current_user
from referral import maybe_apply_referral

router = APIRouter(prefix="/auth", tags=["auth"])

EMERGENT_SESSION_DATA_URL = os.environ.get(
    "EMERGENT_SESSION_DATA_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
)
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cinemora_session")
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "7"))


@router.post("/session")
async def exchange_session(request: Request, response: Response):
    body = await request.json()
    emergent_session_id = body.get("session_id")
    referral_code = body.get("referral_code")
    if not emergent_session_id:
        raise HTTPException(status_code=400, detail="session_id مطلوب")

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(
                EMERGENT_SESSION_DATA_URL,
                headers={"X-Session-ID": emergent_session_id},
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"تعذّر الاتصال بخدمة المصادقة: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="session_id غير صالح")

    data = r.json()
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="استجابة مصادقة غير مكتملة")

    user = await users_col.find_one({"email": email})
    if not user:
        user_doc = {
            "email": email,
            "name": data.get("name"),
            "picture": data.get("picture"),
            "tier": "free",
            "created_at": datetime.now(timezone.utc),
        }
        insert_result = await users_col.insert_one(user_doc)
        user = {**user_doc, "_id": insert_result.inserted_id}

    session_token = data.get("session_token") or os.urandom(24).hex()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    await sessions_col.insert_one(
        {
            "session_token": session_token,
            "user_id": user["_id"],
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc),
        }
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=SESSION_TTL_DAYS * 24 * 3600,
        path="/",
    )

    referral_applied = False
    if referral_code:
        referral_applied = await maybe_apply_referral(user["_id"], referral_code)

    return {
        "email": user["email"],
        "name": user.get("name"),
        "picture": user.get("picture"),
        "tier": user.get("tier", "free"),
        "referral_applied": referral_applied,
    }


@router.get("/me")
async def me(request: Request):
    current = await get_current_user(request)
    if not current:
        raise HTTPException(status_code=401, detail="غير مسجل الدخول")
    return {
        "email": current["email"],
        "name": current.get("name"),
        "picture": current.get("picture"),
        "tier": current.get("tier", "free"),
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await sessions_col.delete_one({"session_token": token})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}
