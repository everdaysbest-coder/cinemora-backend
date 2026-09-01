"""
راوتر /admin — محمي بالكامل، يتطلب role == "admin".
يصبح حسابك admin تلقائيًا عند تسجيل الدخول بإيميل مدرج ضمن ADMIN_EMAILS
(متغيّر بيئة، إيميلات مفصولة بفاصلة) — راجع auth.py.
"""

from fastapi import APIRouter, HTTPException, Request

from db import projects_col, users_col
from deps import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


async def _require_admin(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="غير مسجل الدخول")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="هذه الصفحة تتطلب صلاحيات مشرف")
    return user


# ---------- إدارة المستخدمين ----------

@router.get("/users")
async def list_users(request: Request, limit: int = 100):
    await _require_admin(request)
    cursor = users_col.find({}).sort("created_at", -1).limit(limit)
    return [
        {
            "id": u.get("_id"),
            "email": u.get("email"),
            "name": u.get("name"),
            "tier": u.get("tier", "free"),
            "role": u.get("role", "user"),
            "banned": u.get("banned", False),
            "created_at": u.get("created_at"),
        }
        async for u in cursor
    ]


@router.post("/users/{user_id}/ban")
async def set_user_ban(user_id: str, request: Request):
    await _require_admin(request)
    body = await request.json()
    banned = bool(body.get("banned", True))
    result = await users_col.update_one({"_id": user_id}, {"$set": {"banned": banned}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="مستخدم غير موجود")
    return {"id": user_id, "banned": banned}


@router.post("/users/{user_id}/tier")
async def set_user_tier(user_id: str, request: Request):
    await _require_admin(request)
    body = await request.json()
    tier = body.get("tier")
    if tier not in ("free", "starter", "creator", "pro", "admin"):
        raise HTTPException(status_code=400, detail="tier غير صالح")
    result = await users_col.update_one({"_id": user_id}, {"$set": {"tier": tier}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="مستخدم غير موجود")
    return {"id": user_id, "tier": tier}


# ---------- مراقبة المحتوى (Explore/Trending) ----------

@router.get("/projects")
async def list_all_projects(request: Request, limit: int = 100):
    """يعرض كل المشاريع (عامة ومخفية) — للمراجعة/الحذف."""
    await _require_admin(request)
    cursor = projects_col.find({}).sort("created_at", -1).limit(limit)
    items = []
    async for p in cursor:
        p["id"] = p.get("_id")
        items.append(p)
    return items


@router.post("/projects/{project_id}/moderate")
async def moderate_project(project_id: str, request: Request):
    """إخفاء (public=false) أو إعادة إظهار مشروع بالمعرض العام."""
    await _require_admin(request)
    body = await request.json()
    public = bool(body.get("public", False))
    result = await projects_col.update_one({"_id": project_id}, {"$set": {"public": public}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="مشروع غير موجود")
    return {"id": project_id, "public": public}


@router.delete("/projects/{project_id}")
async def delete_project_admin(project_id: str, request: Request):
    await _require_admin(request)
    await projects_col.delete_one({"_id": project_id})
    return {"deleted": project_id}
