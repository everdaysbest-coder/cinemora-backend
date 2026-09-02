"""
مزوّد Hugging Face Inference API (توليد فيديو حقيقي مجاني — best-effort)
==========================================================================
⚠️ هذا مجاني فعليًا (حساب Hugging Face مجاني + مفتاح API بدون بطاقة ائتمان)،
لكنه على "Serverless Inference API" المشترك: بطيء نسبيًا، معدّل طلبات محدود،
وأحيانًا الموديل يكون "نايم" فيرجع 503 أول مرة (يحتاج إعادة محاولة بعد ثواني
لحد ما يشتغل الموديل). هذا طبيعي لأي شيء "مجاني حقيقي" بدون خادم مخصص.

الحصول على HF_TOKEN:
  1. أنشئ حساب مجاني على https://huggingface.co/join
  2. من https://huggingface.co/settings/tokens أنشئ token جديد (صلاحية "Read" كافية)
"""

import base64
import os

import httpx

HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_VIDEO_MODEL = os.environ.get("HF_VIDEO_MODEL", "damo-vilab/text-to-video-ms-1.7b")
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_VIDEO_MODEL}"


async def generate_video_sync(prompt: str, max_retries: int = 3) -> dict:
    """
    يستدعي Hugging Face بشكل متزامن ويرجع الفيديو فورًا (بدون job/polling،
    لأن استدعاء HF Serverless نفسه متزامن). قد يحتاج إعادة محاولة إذا كان
    الموديل "نايم" (يرجع 503 مع estimated_time بالجسم).
    """
    if not HF_TOKEN:
        raise RuntimeError(
            "HF_TOKEN غير مضبوط في .env — أنشئ حساب مجاني على huggingface.co "
            "وتوكن من huggingface.co/settings/tokens"
        )

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(max_retries):
            r = await client.post(HF_API_URL, headers=headers, json={"inputs": prompt})
            if r.status_code == 200:
                video_bytes = r.content
                b64 = base64.b64encode(video_bytes).decode("utf-8")
                return {"video_base64": f"data:video/mp4;base64,{b64}"}

            if r.status_code == 503:
                # الموديل قيد التحميل على سيرفرات Hugging Face — ننتظر ونعيد المحاولة
                import asyncio

                wait_s = 10
                try:
                    wait_s = min(30, r.json().get("estimated_time", 10))
                except Exception:
                    pass
                await asyncio.sleep(wait_s)
                continue

            raise RuntimeError(f"Hugging Face API error {r.status_code}: {r.text[:300]}")

    raise RuntimeError("الموديل لسا قيد التحميل على Hugging Face، حاول مرة ثانية بعد قليل")
