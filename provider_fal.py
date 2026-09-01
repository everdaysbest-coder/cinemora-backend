"""
مزوّد fal.ai
=============
يستخدم fal.ai queue API الموثّق:
    POST https://queue.fal.run/{model_id}          (Authorization: Key <FAL_KEY>)
        -> {request_id, status_url, response_url, ...}
    GET  {status_url}                                -> {status: IN_QUEUE|IN_PROGRESS|COMPLETED, ...}
    GET  {response_url}                               -> نتيجة النموذج النهائية (تحتوي رابط فيديو)

نموذج "sora-2" هنا افتراضي (fal_model_id) — إذا كان معرّف النموذج الفعلي على
fal.ai مختلفًا (مثلاً "fal-ai/sora-2" أو غيره حسب اتفاقك مع fal)، عدّل
FAL_MODEL_MAP بالأسفل.
"""

import os

import httpx

FAL_KEY = os.environ.get("FAL_KEY", "")
FAL_BASE = "https://queue.fal.run"

FAL_MODEL_MAP = {
    "sora-2": "fal-ai/sora-2/text-to-video",
}


def _headers():
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


async def submit_video_job(prompt: str, duration: int, aspect_ratio: str, model: str) -> dict:
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY غير مضبوط في .env")
    fal_model = FAL_MODEL_MAP.get(model, model)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{FAL_BASE}/{fal_model}",
            headers=_headers(),
            json={
                "prompt": prompt,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
            },
        )
        r.raise_for_status()
        data = r.json()

    return {
        "job_id": data.get("request_id"),
        "status": "queued",
        "_status_url": data.get("status_url"),
        "_response_url": data.get("response_url"),
    }


async def get_video_job(job_id: str, status_url: str, response_url: str) -> dict:
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY غير مضبوط في .env")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(status_url, headers=_headers())
        r.raise_for_status()
        status_data = r.json()
        fal_status = status_data.get("status", "IN_QUEUE")

        if fal_status != "COMPLETED":
            return {"job_id": job_id, "status": _map_status(fal_status)}

        rr = await client.get(response_url, headers=_headers())
        rr.raise_for_status()
        result = rr.json()

    video_url = None
    video_field = result.get("video")
    if isinstance(video_field, dict):
        video_url = video_field.get("url")
    elif isinstance(video_field, str):
        video_url = video_field

    return {"job_id": job_id, "status": "completed", "video_url": video_url, "raw": result}


def _map_status(fal_status: str) -> str:
    return {
        "IN_QUEUE": "queued",
        "IN_PROGRESS": "processing",
        "COMPLETED": "completed",
    }.get(fal_status, "processing")
