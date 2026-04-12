"""Pexels photo fetcher + Grok AI image generation fallback.
Returns base64-encoded JPEG for HTML embedding.
"""
from __future__ import annotations
import base64
import os
import random

import httpx

PEXELS_API = "https://api.pexels.com/v1"


async def fetch_photo_base64(query: str) -> str | None:
    """Search Pexels for query; fallback to Grok if Pexels fails.
    Returns base64-encoded JPEG, or None on failure.
    """
    result = await _pexels(query)
    if result:
        return result

    if os.environ.get("GROK_API_KEY"):
        return await _grok_generate(query)

    return None


async def _pexels(query: str) -> str | None:
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)) as client:
        try:
            r = await client.get(
                f"{PEXELS_API}/search",
                headers={"Authorization": api_key},
                params={"query": query, "per_page": 5, "orientation": "square"},
            )
            r.raise_for_status()
            photos = r.json().get("photos", [])
            if not photos:
                return None
            photo = random.choice(photos)
            img_url = photo["src"].get("large") or photo["src"].get("medium") or photo["src"]["original"]
            img_r = await client.get(img_url)
            img_r.raise_for_status()
            return base64.b64encode(img_r.content).decode()
        except Exception as e:
            print(f"[insta.photo] Pexels 실패 ({query}): {e}")
            return None


async def _grok_generate(prompt: str) -> str | None:
    api_key = os.environ.get("GROK_API_KEY", "")
    if not api_key:
        return None

    english_prompt = f"High quality Instagram background photo: {prompt}, vibrant colors, professional photography"

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)) as client:
        try:
            r = await client.post(
                "https://api.x.ai/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "grok-2-image", "prompt": english_prompt, "n": 1},
            )
            r.raise_for_status()
            img_url = r.json()["data"][0]["url"]
            img_r = await client.get(img_url)
            img_r.raise_for_status()
            return base64.b64encode(img_r.content).decode()
        except Exception as e:
            print(f"[insta.photo] Grok 실패 ({prompt}): {e}")
            return None
