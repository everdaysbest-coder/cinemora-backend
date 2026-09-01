"""راوتر Cinema Studio: /cinema/plan (تقسيم فكرة لمشاهد), /cinema/scene (توليد مشهد واحد)."""

from fastapi import APIRouter, HTTPException, Request

import provider_pollinations as pollinations_provider
from usage import check_and_increment_usage

router = APIRouter(prefix="/cinema", tags=["cinema"])


@router.post("/plan")
async def plan_film(request: Request):
    body = await request.json()
    idea = body.get("idea")
    scene_count = int(body.get("scene_count", 5))
    scene_duration = int(body.get("scene_duration", 8))
    if not idea:
        raise HTTPException(status_code=400, detail="idea مطلوب")

    # ⚠️ تقسيم مبسّط بدون LLM حاليًا. لتوليد مشاهد أذكى استخدم /enhance/prompt
    # لكل مشهد يدويًا، أو وصّل هنا استدعاء Claude بنفس أسلوب enhance.py.
    scenes = [
        {
            "index": i + 1,
            "prompt": f"{idea} — scene {i + 1} of {scene_count}",
            "duration": scene_duration,
        }
        for i in range(scene_count)
    ]
    return {"idea": idea, "scenes": scenes}


@router.post("/scene")
async def generate_scene(request: Request):
    """توليد مشهد واحد بشكل متزامن (صورة تمثيلية سريعة)، خلافًا لـ /generate/video
    غير المتزامن. هنا نستخدم توليد صورة كمعاينة سريعة للمشهد."""
    body = await request.json()
    prompt = body.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt مطلوب")

    await check_and_increment_usage(request, None, kind="image")

    try:
        result = await pollinations_provider.generate_image(prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"فشل توليد معاينة المشهد: {e}")

    return {
        "prompt": prompt,
        "duration": body.get("duration", 8),
        "aspect_ratio": body.get("aspect_ratio", "16:9"),
        "preview_image_base64": result["image_base64"],
    }
