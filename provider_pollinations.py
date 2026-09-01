"""
مزوّد Pollinations (مجاني)
============================
الصور: pollinations.ai توفّر فعليًا نقطة نهاية عامة موثّقة لتوليد الصور:
    GET https://image.pollinations.ai/prompt/{urlencoded_prompt}?width=&height=&nologo=true
    (تُرجع بايتات الصورة مباشرة، بدون حاجة لمفتاح API).
    هذا الجزء موثوق نسبيًا.

الفيديو: ⚠️ لا يوجد لدى pollinations.ai — بحسب معرفتي — نقطة نهاية عامة موثّقة
    لتوليد فيديو فعلي بنماذج مثل Wan/Seedance/Nova Reel كما يوحي كود الواجهة
    الأصلية (constants.js). على الأغلب كان الـ backend الأصلي يستخدم مزوّدًا
    داخليًا/وسيطًا مختلفًا تم تسميته "pollinations" في الواجهة فقط.
    لذلك دالة generate_video هنا مبنية كطبقة قابلة للتوصيل:
    اضبط POLLINATIONS_VIDEO_BASE في .env على نقطة نهاية REST حقيقية لديك
    (متوافقة مع POST يرجّع job id + GET للحالة)، وإلا سترجع الدالة خطأ واضح
    بدل التظاهر بأنها اتصلت بشيء حقيقي.
"""

import base64
import os
import uuid

import httpx

IMAGE_BASE = os.environ.get("POLLINATIONS_IMAGE_BASE", "https://image.pollinations.ai/prompt")
VIDEO_BASE = os.environ.get("POLLINATIONS_VIDEO_BASE", "")


async def generate_image(prompt: str) -> dict:
    import urllib.parse

    url = f"{IMAGE_BASE}/{urllib.parse.quote(prompt)}?nologo=true"
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.get(url)
        r.raise_for_status()
        image_bytes = r.content
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return {"image_base64": f"data:image/jpeg;base64,{b64}"}


async def submit_video_job(prompt: str, duration: int, aspect_ratio: str, resolution: str, model: str) -> dict:
    if not VIDEO_BASE:
        raise RuntimeError(
            "POLLINATIONS_VIDEO_BASE غير مضبوط في .env — لا يوجد مزوّد فيديو مجاني "
            "حقيقي متصل بعد. اضبط هذا المتغيّر على نقطة نهاية توليد فيديو فعلية، "
            "أو استخدم provider='fal' بدلًا منه."
        )
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{VIDEO_BASE}/generate",
            json={
                "prompt": prompt,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "model": model,
            },
        )
        r.raise_for_status()
        return r.json()


async def get_video_job(job_id: str) -> dict:
    if not VIDEO_BASE:
        raise RuntimeError("POLLINATIONS_VIDEO_BASE غير مضبوط في .env")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{VIDEO_BASE}/status/{job_id}")
        r.raise_for_status()
        return r.json()
