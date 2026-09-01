"""راوتر التوليد: /generate/image, /generate/video, /generate/video/{id}, /enhance/prompt"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from db import video_jobs_col
import provider_fal as fal_provider
import provider_pollinations as pollinations_provider
from usage import check_and_increment_usage

router = APIRouter(tags=["generation"])


@router.post("/generate/image")
async def generate_image(request: Request):
    body = await request.json()
    prompt = body.get("prompt")
    session_id = body.get("session_id")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt مطلوب")

    await check_and_increment_usage(request, session_id, kind="image")

    try:
        result = await pollinations_provider.generate_image(prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"فشل توليد الصورة: {e}")

    return result


@router.post("/generate/video")
async def generate_video(request: Request):
    body = await request.json()
    prompt = body.get("prompt")
    duration = body.get("duration", 8)
    aspect_ratio = body.get("aspect_ratio", "16:9")
    resolution = body.get("resolution", "720p")
    provider = body.get("provider", "pollinations")
    model = body.get("model", "wan")

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt مطلوب")

    await check_and_increment_usage(request, body.get("session_id"), kind="video")

    job_id = str(uuid.uuid4())
    job_doc = {
        "job_id": job_id,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "provider": provider,
        "model": model,
        "status": "queued",
        "video_url": None,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        if provider == "fal":
            fal_result = await fal_provider.submit_video_job(prompt, duration, aspect_ratio, model)
            job_doc["status"] = fal_result["status"]
            job_doc["_fal_status_url"] = fal_result.get("_status_url")
            job_doc["_fal_response_url"] = fal_result.get("_response_url")
        else:
            pollinations_result = await pollinations_provider.submit_video_job(
                prompt, duration, aspect_ratio, resolution, model
            )
            job_doc["status"] = pollinations_result.get("status", "queued")
            job_doc["_provider_job_id"] = pollinations_result.get("job_id")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"فشل إرسال مهمة الفيديو: {e}")

    await video_jobs_col.insert_one(job_doc)
    return {"job_id": job_id, "status": job_doc["status"]}


@router.get("/generate/video/{job_id}")
async def get_video_job(job_id: str):
    job = await video_jobs_col.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="مهمة غير موجودة")

    if job["status"] not in ("completed", "failed", "error"):
        try:
            if job["provider"] == "fal":
                updated = await fal_provider.get_video_job(
                    job_id, job.get("_fal_status_url"), job.get("_fal_response_url")
                )
            else:
                updated = await pollinations_provider.get_video_job(job.get("_provider_job_id", job_id))

            new_status = updated.get("status", job["status"])
            video_url = updated.get("video_url")
            update_fields = {"status": new_status}
            if video_url:
                update_fields["video_url"] = video_url
            await video_jobs_col.update_one({"job_id": job_id}, {"$set": update_fields})
            job.update(update_fields)
        except Exception:
            pass  # نرجّع آخر حالة معروفة محليًا إن تعذّر الاستعلام من المزوّد

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "video_url": job.get("video_url"),
        "prompt": job.get("prompt"),
    }
