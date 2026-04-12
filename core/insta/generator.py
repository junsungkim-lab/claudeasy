"""인스타그램 캐러셀 생성 파이프라인.

카드 output(마크다운)에서 슬라이드 JSON을 추출하고,
사진 수급 → HTML 조립 → PNG 렌더링 → 파일 저장까지 수행.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "insta"


def _load_brand_bg() -> str | None:
    """브랜드 배경 이미지를 base64로 로드."""
    path = ASSETS_DIR / "brand_bg.jpg"
    if path.exists():
        return base64.b64encode(path.read_bytes()).decode()
    return None


def _extract_slides_json(text: str) -> dict | None:
    """카드 output 텍스트에서 슬라이드 JSON 추출."""
    # ```json ... ``` 블록 우선
    fenced = re.search(r'```json\s*([\s\S]*?)```', text, re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 중괄호 블록 fallback
    brace = re.search(r'\{[\s\S]*"slides"[\s\S]*\}', text)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _build_hook_slide_html(slide_num: int, total: int, title: str, body: str, photo_b64: str | None, brand_name: str) -> str:
    if photo_b64:
        bg_style = f"background-image: url('data:image/jpeg;base64,{photo_b64}'); background-size: cover; background-position: center;"
    else:
        bg_style = "background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);"

    counter_html = f'<div class="counter">{slide_num}/{total}</div>' if total > 1 else ""
    brand_html = f'<div class="brand">{brand_name}</div>' if brand_name else ""
    body_html = f'<div class="body">{body}</div>' if body.strip() else ""
    title_html = title.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@700;900&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ width: 1080px; height: 1080px; overflow: hidden; position: relative;
         font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif; }}
  .bg {{ position: absolute; inset: 0; {bg_style} }}
  .overlay {{ position: absolute; inset: 0;
    background: radial-gradient(ellipse at center, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0.55) 60%, rgba(0,0,0,0.82) 100%); }}
  .overlay2 {{ position: absolute; inset: 0; background: rgba(0,0,0,0.25); }}
  .brand {{ position: absolute; top: 44px; left: 50%; transform: translateX(-50%);
    color: rgba(255,255,255,0.90); font-size: 28px; font-weight: 900;
    letter-spacing: 6px; text-transform: uppercase; white-space: nowrap; z-index: 10; }}
  .counter {{ position: absolute; top: 36px; right: 50px; color: rgba(255,255,255,0.85);
    font-size: 30px; font-weight: 700; background: rgba(0,0,0,0.35);
    padding: 8px 18px; border-radius: 24px; z-index: 10; }}
  .text-block {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 900px; text-align: center; z-index: 10; }}
  .title {{ color: #ffffff; font-size: 88px; font-weight: 900; line-height: 1.15;
    letter-spacing: -2px; text-shadow: 0 4px 32px rgba(0,0,0,0.8), 0 0 60px rgba(0,0,0,0.5); }}
  .body {{ margin-top: 28px; color: rgba(255,255,255,0.85); font-size: 40px;
    font-weight: 700; line-height: 1.4; text-shadow: 0 2px 16px rgba(0,0,0,0.7); word-break: keep-all; }}
</style>
</head>
<body>
  <div class="bg"></div><div class="overlay"></div><div class="overlay2"></div>
  {brand_html}{counter_html}
  <div class="text-block">
    <div class="title">{title_html}</div>
    {body_html}
  </div>
</body>
</html>"""


def _build_slide_html(slide_num: int, total: int, title: str, body: str, photo_b64: str | None, brand_name: str) -> str:
    if photo_b64:
        bg_style = f"background-image: url('data:image/jpeg;base64,{photo_b64}'); background-size: cover; background-position: center;"
    else:
        bg_style = "background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);"

    counter_html = f'<div class="counter">{slide_num}/{total}</div>' if total > 1 else ""
    brand_html = f'<div class="brand">{brand_name}</div>' if brand_name else ""
    body_html = f'<div class="body">{body}</div>' if body.strip() else ""
    title_html = title.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@700;900&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ width: 1080px; height: 1080px; overflow: hidden; position: relative;
         font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif; }}
  .bg {{ position: absolute; inset: 0; {bg_style} }}
  .overlay {{ position: absolute; inset: 0;
    background: linear-gradient(to top, rgba(0,0,0,0.90) 0%, rgba(0,0,0,0.55) 35%, rgba(0,0,0,0.15) 60%, rgba(0,0,0,0.05) 100%); }}
  .brand {{ position: absolute; top: 44px; left: 50%; transform: translateX(-50%);
    color: rgba(255,255,255,0.92); font-size: 28px; font-weight: 900;
    letter-spacing: 6px; text-transform: uppercase; white-space: nowrap; }}
  .counter {{ position: absolute; top: 36px; right: 50px; color: rgba(255,255,255,0.85);
    font-size: 30px; font-weight: 700; background: rgba(0,0,0,0.35);
    padding: 8px 18px; border-radius: 24px; }}
  .text-block {{ position: absolute; bottom: 80px; left: 64px; right: 64px; }}
  .title {{ color: #ffffff; font-size: 76px; font-weight: 900; line-height: 1.2;
    letter-spacing: -1px; text-shadow: 0 3px 24px rgba(0,0,0,0.6); }}
  .body {{ margin-top: 20px; color: rgba(255,255,255,0.80); font-size: 42px;
    font-weight: 700; line-height: 1.4; text-shadow: 0 2px 12px rgba(0,0,0,0.5); word-break: keep-all; }}
</style>
</head>
<body>
  <div class="bg"></div><div class="overlay"></div>
  {brand_html}{counter_html}
  <div class="text-block">
    <div class="title">{title_html}</div>
    {body_html}
  </div>
</body>
</html>"""


def _build_brand_slide_html(slide_num: int, total: int, brand_name: str, bg_b64: str | None = None) -> str:
    brand_display = brand_name or "STUDIO"
    bg_layer = ""
    if bg_b64:
        bg_layer = f"""<div style="position:absolute;inset:0;
          background-image:url('data:image/jpeg;base64,{bg_b64}');
          background-size:cover;background-position:center top;opacity:0.18;"></div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@700;900&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ width: 1080px; height: 1080px; overflow: hidden; position: relative;
         font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif; background: #080808; }}
  .glow1 {{ position:absolute; width:600px; height:600px; border-radius:50%;
    background:radial-gradient(circle,rgba(124,107,255,0.12) 0%,transparent 70%); top:-150px; right:-150px; }}
  .glow2 {{ position:absolute; width:500px; height:500px; border-radius:50%;
    background:radial-gradient(circle,rgba(255,107,157,0.08) 0%,transparent 70%); bottom:-100px; left:-100px; }}
  .counter {{ position:absolute; top:36px; right:50px; color:rgba(255,255,255,0.4);
    font-size:28px; font-weight:700; background:rgba(255,255,255,0.06);
    padding:8px 18px; border-radius:24px; z-index:10; }}
  .center-block {{ position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
    text-align:center; width:840px; z-index:10; }}
  .brand-name {{ color:#ffffff; font-size:68px; font-weight:900; letter-spacing:12px;
    text-transform:uppercase; text-shadow:0 0 80px rgba(124,107,255,0.7),0 2px 20px rgba(0,0,0,0.8); }}
  .divider {{ margin:36px auto; width:120px; height:2px;
    background:linear-gradient(to right,transparent,rgba(124,107,255,0.8),transparent); }}
  .tagline {{ color:rgba(255,255,255,0.50); font-size:32px; font-weight:700; letter-spacing:2px; }}
  .cta {{ margin-top:56px; display:inline-block; border:2px solid rgba(124,107,255,0.6);
    color:rgba(255,255,255,0.92); font-size:30px; font-weight:700; padding:16px 52px;
    border-radius:60px; letter-spacing:2px; background:rgba(124,107,255,0.10); }}
</style>
</head>
<body>
  {bg_layer}
  <div class="glow1"></div><div class="glow2"></div>
  <div class="counter">{slide_num}/{total}</div>
  <div class="center-block">
    <div class="brand-name">{brand_display}</div>
    <div class="divider"></div>
    <div class="tagline">매일 업데이트되는 트렌드 정보</div>
    <div class="cta">팔로우 &amp; 저장 👆</div>
  </div>
</body>
</html>"""


async def generate_carousel(card_id: int, output_text: str) -> list[str]:
    """카드 output에서 슬라이드 JSON 추출 → 사진 수급 → HTML 조립 → PNG 저장.

    Returns: 저장된 PNG 파일 경로 목록 (빈 리스트면 생성 실패)
    """
    from .photo import fetch_photo_base64
    from .renderer import render_html_to_png

    data = _extract_slides_json(output_text)
    if not data or "slides" not in data:
        print(f"[insta.generator] card {card_id}: JSON 추출 실패 — 슬라이드 생성 스킵")
        return []

    slides = data["slides"]
    brand_name = os.environ.get("BRAND_NAME", "")
    brand_bg = _load_brand_bg()
    total = len(slides) + 1  # 콘텐츠 슬라이드 + 브랜드 슬라이드

    print(f"[insta.generator] card {card_id}: {len(slides)}개 슬라이드 생성 시작")

    # 1. 사진 병렬 수급
    async def fetch_with_timeout(query: str) -> str | None:
        try:
            return await asyncio.wait_for(fetch_photo_base64(query), timeout=20)
        except (asyncio.TimeoutError, Exception) as e:
            print(f"[insta.generator] 사진 수급 실패 ({query}): {e}")
            return None

    photos = await asyncio.gather(*[
        fetch_with_timeout(s.get("photo_query", s.get("title", "")))
        for s in slides
    ])

    # 2. HTML 조립
    html_pages: list[str] = []
    for i, (slide, photo) in enumerate(zip(slides, photos)):
        slide_num = i + 1
        title = slide.get("title", "")
        body = slide.get("body", "")
        if i == 0:
            html = _build_hook_slide_html(slide_num, total, title, body, photo, brand_name)
        else:
            html = _build_slide_html(slide_num, total, title, body, photo, brand_name)
        html_pages.append(html)

    # 브랜드 슬라이드 (마지막)
    html_pages.append(_build_brand_slide_html(total, total, brand_name, brand_bg))

    # 3. PNG 렌더링 + 저장
    output_dir = OUTPUT_DIR / str(card_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    png_paths: list[str] = []
    for i, html in enumerate(html_pages):
        try:
            png_bytes = await render_html_to_png(html)
            filename = f"slide_{i + 1:02d}.png"
            path = output_dir / filename
            path.write_bytes(png_bytes)
            png_paths.append(str(path))
            print(f"[insta.generator] card {card_id}: {filename} 저장 ({len(png_bytes)//1024}KB)")
        except Exception as e:
            print(f"[insta.generator] card {card_id}: slide {i+1} 렌더링 실패: {e}")

    print(f"[insta.generator] card {card_id}: 완료 ({len(png_paths)}/{len(html_pages)}개)")
    return png_paths
