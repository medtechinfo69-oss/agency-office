"""Zed's image generation — fully automatic, three layers:

1. The active provider's own /images endpoint (when its preset declares
   `images_api` — most free APIs don't have one).
2. **Pollinations** — free, keyless image API (the automatic default,
   IMAGE_MODEL=pollinations-free). No key or billing needed.
3. Branded SVG placeholder, clearly labelled, so the pipeline never breaks.

Aspect ratios: 1:1 (1080×1080), 4:5 (1080×1350), 9:16 (1080×1920).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from . import db
from .config import AUTO_IMAGE_MODEL, settings
from .provider import ProviderError, provider
from .media import persist_file, restore_file

RATIOS = {"1:1": (1080, 1080), "4:5": (1080, 1350), "9:16": (1080, 1920)}


def _brand(project_id: str) -> tuple[list[str], str, Optional[str]]:
    row = db.one("SELECT * FROM brand_kit WHERE project_id=?", (project_id,))
    if not row:
        return ["#0f172a", "#2dd4bf", "#f8fafc"], "BRAND", None
    colors = db.jload(row["colors"], []) or ["#0f172a", "#2dd4bf", "#f8fafc"]
    extra = db.jload(row["extra"], {}) or {}
    name = extra.get("name", "BRAND")
    if row['logo_path']:
        restore_file(Path(row['logo_path']))
    return colors, name, row["logo_path"]


def _svg_placeholder(name: str, colors: list[str], title: str, ratio: str,
                     logo_path: Optional[str], kind: str) -> str:
    w, h = RATIOS.get(ratio, RATIOS["1:1"])
    c1, c2, c3 = (colors + ["#0f172a", "#2dd4bf", "#f8fafc"])[:3]
    # simple pixel blocks decoration
    blocks = []
    import hashlib
    seed = int(hashlib.md5(title.encode()).hexdigest()[:6], 16)
    for i in range(14):
        x = (seed * (i + 3) * 37) % w
        y = (seed * (i + 7) * 53) % h
        s = 40 + (seed >> i) % 80
        op = 0.06 + (i % 4) * 0.03
        blocks.append(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{c2}" opacity="{op:.2f}"/>')
    logo = ""
    if logo_path and Path(logo_path).exists():
        logo = f'<image href="{_file_uri(logo_path)}" x="60" y="60" height="140"/>'
    elif name:
        logo = (f'<text x="60" y="140" font-family="monospace" font-size="64" '
                f'font-weight="bold" fill="{c3}">{_esc(name[:14])}</text>')
    title_lines = _wrap(title, 18)[:3]
    title_svg = "".join(
        f'<text x="60" y="{int(h * 0.55) + i * 74}" font-family="monospace" font-size="56" '
        f'fill="{c3}">{_esc(line)}</text>'
        for i, line in enumerate(title_lines))
    badge = (f'<rect x="60" y="{h - 160}" width="420" height="80" rx="8" fill="{c2}"/>'
             f'<text x="90" y="{h - 105}" font-family="monospace" font-size="40" fill="#041018">'
             f'{_esc(kind.upper())} · {ratio}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<rect width="{w}" height="{h}" fill="{c1}"/>
{''.join(blocks)}
<rect x="0" y="0" width="{w}" height="18" fill="{c2}"/>
{logo}
{title_svg}
{badge}
</svg>'''


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _wrap(s: str, n: int) -> list[str]:
    words, lines, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= n:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _file_uri(p: str) -> str:
    return "file://" + str(Path(p).resolve())


async def generate_image(project_id: str, title: str, ratio: str = "1:1",
                         prompt: str = "", slug: str = "asset") -> dict:
    """Generate one image. Returns {path, url, source} or raises ProviderError."""
    colors, name, logo = _brand(project_id)
    safe = re.sub(r"[^a-z0-9_-]+", "_", slug.lower())[:40] or "asset"
    out_dir = settings.media_dir / project_id
    out_dir.mkdir(parents=True, exist_ok=True)

    full_prompt = (
        f"Pixel-art / clean modern marketing creative for \"{name}\". "
        f"Title: {title}. Aspect {ratio}. "
        f"Brand colors: {', '.join(colors[:5])}. Minimal text (max 20% of frame). "
        f"{prompt}"
    )

    note = ""

    # 1) provider's own images API — only when the preset supports it
    if (settings.image_model and settings.image_model != AUTO_IMAGE_MODEL
            and _active_images_api()):
        try:
            size = _api_size(ratio)
            data = await provider().image(full_prompt, size=size)
            ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ("jpg" if data[:2] == b"\xff\xd8" else "png")
            path = out_dir / f"{safe}.{ext}"
            path.write_bytes(data)
            persist_file(path)
            return {"path": str(path), "url": f"/media/{project_id}/{path.name}",
                    "source": "api", "model": settings.image_model}
        except Exception as e:
            note = f"provider image API failed ({e}); "

    # 2) automatic free backend (Pollinations — no key, no billing)
    if settings.image_model != "none":
        try:
            import httpx
            data = await _pollinations(full_prompt, ratio)
            ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
            path = out_dir / f"{safe}.{ext}"
            path.write_bytes(data)
            persist_file(path)
            return {"path": str(path), "url": f"/media/{project_id}/{path.name}",
                    "source": "api", "model": AUTO_IMAGE_MODEL}
        except Exception as e:
            note += f"auto image service unavailable ({e}); "

    # 3) branded placeholder — labelled in the UI, pipeline keeps moving
    svg = _svg_placeholder(name, colors, title, ratio, logo, "creative")
    path = out_dir / f"{safe}.svg"
    path.write_text(svg, encoding="utf-8")
    persist_file(path)
    out = {"path": str(path), "url": f"/media/{project_id}/{path.name}",
           "source": "placeholder_svg", "model": "local"}
    if note:
        out["note"] = note.rstrip("; ")
    return out


def _active_images_api() -> bool:
    from .config import PROVIDER_PRESETS
    preset = PROVIDER_PRESETS.get(settings.active_provider, {})
    return bool(preset.get("images_api"))


async def _pollinations(prompt: str, ratio: str) -> bytes:
    """Free keyless image generation (pollinations.ai). Raises on failure."""
    import httpx
    w, h = RATIOS.get(ratio, RATIOS["1:1"])
    # service renders at common sizes; keep aspect, cap longest edge at 1080
    scale = 1080 / max(w, h)
    width, height = int(w * scale) // 8 * 8, int(h * scale) // 8 * 8
    url = ("https://image.pollinations.ai/prompt/"
           + quote(prompt[:900], safe=""))
    resp = await httpx.AsyncClient(timeout=httpx.Timeout(90.0)).get(
        url, params={"width": width, "height": height, "nologo": "true"})
    if resp.status_code >= 400 or not resp.content:
        raise ProviderError("network", f"pollinations HTTP {resp.status_code}")
    ctype = resp.headers.get("content-type", "")
    if "image" not in ctype and not resp.content[:4].startswith(
            (b"\xff\xd8", b"\x89PNG", b"RIFF", b"GIF8")):
        raise ProviderError("server", f"pollinations returned {ctype or 'no image'}")
    return resp.content


def _api_size(ratio: str) -> str:
    return {"1:1": "1024x1024", "4:5": "1024x1792", "9:16": "1024x1792"}.get(ratio, "1024x1024")
