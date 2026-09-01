"""راوتر /enhance/prompt — تحسين الوصف عبر Claude، مع بديل بسيط بدون مفتاح API."""

import os

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/enhance", tags=["enhance"])

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = (
    "You are a prompt engineer for an AI video/image generation product. "
    "Rewrite the user's short idea into a single, vivid, cinematic generation prompt "
    "(camera angle, lighting, mood, style). Keep it under 60 words. "
    "Return only the improved prompt, nothing else."
)


def _fallback_enhance(prompt: str, mode: str) -> str:
    style = "cinematic, dramatic lighting, high detail, 8k" if mode == "video" else "highly detailed, professional photography, 8k"
    return f"{prompt}, {style}"


@router.post("/prompt")
async def enhance_prompt(request: Request):
    body = await request.json()
    prompt = body.get("prompt")
    mode = body.get("mode", "image")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt مطلوب")

    if not ANTHROPIC_API_KEY:
        return {"enhanced_prompt": _fallback_enhance(prompt, mode), "source": "fallback"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 200,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": f"Mode: {mode}\nIdea: {prompt}"}],
                },
            )
            r.raise_for_status()
            data = r.json()
        enhanced = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
        if not enhanced:
            raise ValueError("استجابة فارغة من Claude")
        return {"enhanced_prompt": enhanced, "source": "claude"}
    except Exception:
        return {"enhanced_prompt": _fallback_enhance(prompt, mode), "source": "fallback"}
