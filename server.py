"""
Cinemora Backend — نقطة الدخول
=================================
تشغيل محلي:
    pip install -r requirements.txt
    cp .env.example .env   # ثم عدّل القيم
    uvicorn server:app --reload --port 8000

كل المسارات تحت بادئة /api لتطابق frontend/src/lib/api.js
(REACT_APP_BACKEND_URL يجب أن يشير لعنوان هذا السيرفر، مثل http://localhost:8000).
"""

import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import auth
import cinema
import community
import enhance
import generation
import payments
import projects
import referral
import usage

app = FastAPI(title="Cinemora Backend")

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
async def health():
    return {"status": "ok"}


api_router.include_router(auth.router)
api_router.include_router(payments.router)
api_router.include_router(usage.router)
api_router.include_router(enhance.router)
api_router.include_router(generation.router)
api_router.include_router(cinema.router)
api_router.include_router(projects.router)
api_router.include_router(referral.router)
api_router.include_router(community.router)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
