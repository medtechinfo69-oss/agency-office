"""Application configuration.

Reads .env (if present) and environment variables. Secrets (API_TOKEN,
META_ACCESS_TOKEN) are read here and never exposed through the API layer.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root (agency-office/.env) then backend/.env
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


# --------------------------------------------------------------------------
# Provider presets — switch with one click in Settings → Providers.
# Each preset is OpenAI-compatible. Free-model picks are included so the
# app can run at zero cost (Groq / Gemini free tier, OpenRouter :free,
# fully-local Ollama).
# --------------------------------------------------------------------------
# Automatic image backend: free keyless Pollinations API (no provider image
# endpoint needed). Set IMAGE_MODEL=none to disable image generation entirely.
AUTO_IMAGE_MODEL = "pollinations-free"

PROVIDER_PRESETS: dict[str, dict] = {
    "openai": {"label":"OpenAI", "base_url":"https://api.openai.com/v1", "model":"", "site":"https://platform.openai.com", "headers":{}, "free":False},
    "anthropic": {"label":"Anthropic Claude", "base_url":"https://api.anthropic.com/v1", "model":"", "site":"https://console.anthropic.com", "headers":{}, "free":False},
    "ollama_cloud": {"label": "Ollama Cloud", "base_url": "https://ollama.com/api", "model": "", "site": "https://ollama.com", "headers": {}, "free": False},
    "arena": {"label": "Arena", "base_url": "https://api.arena.ai/v1", "model": "", "site": "https://platform.arena.ai", "headers": {}, "free": False},
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "site": "https://openrouter.ai/models?order=newest",
        "headers": {"X-Title": "Agency Office"},
        "reasoning_off": True,   # free reasoning models burn budget & return null content
        "free": True,
    },
    "apinex": {
        "label": "APInex",
        "base_url": "https://api.apinex.bond/v1",
        "model": "free/glm-5.3-flash",
        "site": "https://apinex.bond",
        "headers": {},
        "free": True,
    },
    "groq": {
        "label": "Groq (free tier)",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "site": "https://console.groq.com/keys",
        "headers": {},
        "free": True,
    },
    "gemini": {
        "label": "Google Gemini (free tier)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash",
        "site": "https://aistudio.google.com/apikey",
        "headers": {},
        "free": True,
    },
    "ollama": {
        "label": "Ollama (local · unlimited)",
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2",
        "site": "https://ollama.com/download",
        "headers": {},
        "free": True,
    },
}


def provider_base_url(key: str, base_url: str) -> str:
    """Repair only Arena's known first-party preset aliases, never custom gateways.

    The dashboard host was shipped as the API host. Normalize old saved/env
    values at read time; leave keys and persisted configuration untouched.
    Official OpenAI-compatible API: https://platform.arena.ai/docs/api
    """
    base = base_url.strip().rstrip('/')
    if key == 'arena' and base in (
        'https://platform.arena.ai', 'https://platform.arena.ai/v1',
        'https://api.arena.ai', 'https://api.arena.ai/v1',
    ):
        return 'https://api.arena.ai/v1'
    return base


def match_preset(base_url: str) -> str | None:
    """Map a base URL to a preset key (for legacy API_BASE_URL env vars)."""
    base_url = provider_base_url('arena', base_url or '')
    host = base_url.split("//")[-1].split("/")[0].lower()
    for key, p in PROVIDER_PRESETS.items():
        p_host = p["base_url"].split("//")[-1].split("/")[0].lower()
        if host and (host == p_host or host.endswith("." + p_host) or p_host.endswith(host)):
            return key
    return None


@dataclass
class Settings:
    # --- AI provider (OpenAI-compatible) ---
    api_base_url: str = field(default_factory=lambda: _env("API_BASE_URL", "https://api.openai.com/v1"))
    api_token: str = field(default_factory=lambda: _env("API_TOKEN", ""))
    text_model: str = field(default_factory=lambda: _env("TEXT_MODEL", "gpt-4o-mini"))
    image_model: str = field(default_factory=lambda: _env("IMAGE_MODEL", "dall-e-3"))

    # --- multi-provider: active key + per-provider credentials ---
    active_provider: str = "openrouter"
    provider_creds: dict = field(default_factory=dict)

    # demo = auto (use demo provider when no token), true, or false
    demo_mode: str = field(default_factory=lambda: _env("DEMO_MODE", "auto"))

    # --- Server ---
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8000")))
    db_path: str = field(default_factory=lambda: _env("DB_PATH", "/tmp/agency-office/agency.db" if os.getenv('VERCEL') == '1' else "data/agency.db"))

    # --- Provider resilience ---
    request_timeout: float = field(default_factory=lambda: float(_env("REQUEST_TIMEOUT_SECONDS", "60")))
    max_retries: int = field(default_factory=lambda: int(_env("MAX_RETRIES", "4")))

    # --- Cost tracking ---
    price_in: float = field(default_factory=lambda: float(_env("PRICE_INPUT_PER_1K", "0.00015")))
    price_out: float = field(default_factory=lambda: float(_env("PRICE_OUTPUT_PER_1K", "0.0006")))

    # --- Meta Graph (optional, draft/approval only) ---
    meta_token: str = field(default_factory=lambda: _env("META_ACCESS_TOKEN", ""))
    meta_page_id: str = field(default_factory=lambda: _env("META_PAGE_ID", ""))
    meta_ig_id: str = field(default_factory=lambda: _env("META_IG_BUSINESS_ID", ""))

    # --- Trend scan ---
    trend_search: str = field(default_factory=lambda: _env("TREND_SEARCH", "web"))

    # --- Misc ---
    secret: str = field(default_factory=lambda: _env("SECRET_KEY", secrets.token_hex(32)))

    @property
    def is_demo(self) -> bool:
        """True when the app should run with the built-in demo provider."""
        if self.demo_mode.lower() == "true":
            return True
        if self.demo_mode.lower() == "false":
            return False
        return not self.api_token  # auto

    @property
    def db_file(self) -> Path:
        p = Path(self.db_path)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[1] / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_dir(self) -> Path:
        default = '/tmp/agency-office' if os.getenv('VERCEL') == '1' else str(Path(__file__).resolve().parents[1] / 'data')
        directory = Path(_env("DATA_DIR", default))
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def media_dir(self) -> Path:
        d = self.data_dir / "media"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def export_dir(self) -> Path:
        d = self.data_dir / "exports"
        d.mkdir(parents=True, exist_ok=True)
        return d


settings = Settings()


def _seed_provider_creds(s: "Settings") -> None:
    """Build per-provider credentials: presets < env < (kv applied at startup)."""
    creds: dict[str, dict] = {}
    for key, p in PROVIDER_PRESETS.items():
        ku = key.upper()
        token = _env(f"{ku}_API_KEY") or _env(f"{ku}_TOKEN") or _env(f"{ku}_API_TOKEN")
        if key == "ollama_cloud": token = token or _env("OLLAMA_API_KEY")
        model = _env(f"{ku}_MODEL")
        base = _env(f"{ku}_BASE_URL")
        creds[key] = {
            "base_url": base or p["base_url"],
            "token": token,
            "model": model or p["model"],
        }
    # legacy API_BASE_URL/API_TOKEN/TEXT_MODEL seed the matching preset
    legacy_token = _env("API_TOKEN")
    if legacy_token:
        target = match_preset(_env("API_BASE_URL")) or (
            s.active_provider if s.active_provider in creds else "apinex")
        if target in creds and not creds[target]["token"]:
            creds[target]["token"] = legacy_token
            if _env("API_BASE_URL"):
                creds[target]["base_url"] = _env("API_BASE_URL")
            if _env("TEXT_MODEL"):
                creds[target]["model"] = _env("TEXT_MODEL")
    for key, values in creds.items():
        values['base_url'] = provider_base_url(key, values['base_url'])
    s.provider_creds = creds
    # active provider: env wins at load; kv may override at startup
    env_active = _env("ACTIVE_PROVIDER")
    if env_active and env_active in creds:
        s.active_provider = env_active
    elif not any(c["token"] for c in creds.values()):
        s.active_provider = "openrouter"
    else:
        # auto-pick first preset (by definition order) that has a token
        for key in PROVIDER_PRESETS:
            if creds[key]["token"]:
                s.active_provider = key
                break
    # back-compat mirrors for code that still reads the flat fields
    ac = creds.get(s.active_provider, {})
    if ac.get("base_url"):
        s.api_base_url = ac["base_url"]
    if ac.get("token"):
        s.api_token = ac["token"]
    if ac.get("model"):
        s.text_model = ac["model"]


_seed_provider_creds(settings)
