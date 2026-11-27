"""Single configurable AI provider layer.

* OpenAI-compatible by default (`/chat/completions`, `/images/generations`)
* Retries with exponential backoff + jitter, honours Retry-After on 429
* Timeouts, structured ProviderError kinds (rate_limit / timeout / auth / ...)
* A deterministic DEMO provider so the whole app runs with zero API keys
  (clearly labelled "DEMO" in the UI — never used when a real token is set)

Switching providers = edit API_BASE_URL / models in .env. No other code changes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from .config import settings, provider_base_url


class ProviderError(Exception):
    def __init__(self, kind: str, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.kind = kind  # rate_limit | timeout | auth | payment | server | network | bad_request
        self.message = message
        self.status = status

    def friendly(self) -> str:
        base = {
            "rate_limit": "Rate limited by the AI provider — retrying shortly.",
            "timeout": "The AI provider timed out.",
            "auth": "Authentication failed — check API_TOKEN in .env.",
            "payment": "AI provider account needs credit/top-up (HTTP 402).",
            "server": "The AI provider returned a server error.",
            "network": "Cannot reach the AI provider — check API_BASE_URL.",
            "bad_request": "The AI provider rejected the request.",
        }.get(self.kind, self.message)
        return f"{base} ({self.message})"


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    model: str = ""
    demo: bool = False


@dataclass
class ChatResult:
    text: str
    usage: Usage
    raw: dict = field(default_factory=dict)


def _cost(tokens_in: int, tokens_out: int) -> float:
    return (tokens_in / 1000.0) * settings.price_in + (tokens_out / 1000.0) * settings.price_out


class BaseProvider:
    demo: bool = False

    async def chat(self, messages: list[dict], *, temperature: float = 0.4,
                   max_tokens: int = 2000, json_mode: bool = False) -> ChatResult:
        raise NotImplementedError

    async def image(self, prompt: str, *, size: str = "1024x1024") -> bytes:
        raise NotImplementedError


# --------------------------------------------------------------------------
# Real OpenAI-compatible provider
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ProviderConfig:
    """Fully-resolved configuration for one OpenAI-compatible provider."""
    key: str
    label: str
    base_url: str
    token: str
    model: str
    headers: dict = field(default_factory=dict)
    reasoning_off: bool = False


def active_config() -> Optional[ProviderConfig]:
    """Config of the currently active provider (None when no token anywhere)."""
    from .config import PROVIDER_PRESETS
    from .hosted_settings import refresh
    refresh()
    key = settings.active_provider
    creds = (settings.provider_creds or {}).get(key) or {}
    preset = PROVIDER_PRESETS.get(key, {})
    from . import db
    if db.kv_get('disconnected_' + key) == '1': return None
    token = creds.get("token") or ""
    if not token and key != "ollama":
        # active has no token → first configured provider wins (if any)
        for k2, c2 in (settings.provider_creds or {}).items():
            if c2.get("token") and db.kv_get("disconnected_" + k2) != "1":
                key, creds = k2, c2
                preset = PROVIDER_PRESETS.get(k2, {})
                token = c2["token"]
                break
    if not token and key != "ollama":
        return None
    return ProviderConfig(
        key=key,
        label=preset.get("label", key),
        base_url=(creds.get("base_url") or preset.get("base_url", settings.api_base_url)).rstrip("/").removesuffix("/api") + "/v1" if key=="ollama_cloud" and (creds.get("base_url") or preset.get("base_url", "")).rstrip("/").endswith("/api") else (creds.get("base_url") or preset.get("base_url", settings.api_base_url)).rstrip("/"),
        token=token or "ollama",
        model=creds.get("model") or preset.get("model", settings.text_model),
        headers=dict(preset.get("headers") or {}),
        reasoning_off=bool(preset.get("reasoning_off")),
    )


def configured_configs() -> list[ProviderConfig]:
    """All providers that have a token (active first) — the failover chain."""
    from .config import PROVIDER_PRESETS
    out: list[ProviderConfig] = []
    seen: set[str] = set()
    ac = active_config()
    if ac:
        out.append(ac)
        seen.add(ac.key)
    for key, preset in PROVIDER_PRESETS.items():
        from . import db
        if key in seen or db.kv_get("disconnected_" + key) == "1":
            continue
        creds = (settings.provider_creds or {}).get(key) or {}
        token = creds.get("token") or ""
        if not token and key != "ollama":
            continue
        out.append(ProviderConfig(
            key=key,
            label=preset.get("label", key),
            base_url=(creds.get("base_url") or preset["base_url"]).rstrip("/").removesuffix("/api") + "/v1" if key=="ollama_cloud" and (creds.get("base_url") or preset["base_url"]).rstrip("/").endswith("/api") else (creds.get("base_url") or preset["base_url"]).rstrip("/"),
            token=token or "ollama",
            model=creds.get("model") or preset["model"],
            headers=dict(preset.get("headers") or {}),
            reasoning_off=bool(preset.get("reasoning_off")),
        ))
    return out


# ---------------------------------------------------------------- model discovery
_IMG_RE = re.compile(r"image|dall|flux|imagen|sdxl|stable.?diff|\bsd-|sd/|draw", re.I)
# non-chat endpoints that would break pipeline calls if auto-selected
_NON_CHAT_RE = re.compile(
    r"whisper|embedding|tts|audio|moderation|rerank|guard|lyria|music", re.I)


def classify_models(key: str, entries: list[tuple[str, dict]]) -> list[dict]:
    """(id, pricing) rows → [{id, free, image}], free models first (stable)."""
    out: list[dict] = []
    for mid, pricing in entries:
        if _NON_CHAT_RE.search(mid):
            continue
        if key == "openrouter":
            free = mid.endswith(":free") or (
                str(pricing.get("prompt")) in ("0", "0.0")
                and str(pricing.get("completion")) in ("0", "0.0"))
        elif key == "apinex":
            free = mid.startswith("free/") or "/free-" in mid
        else:
            free = key in ("groq", "gemini", "ollama")  # Unknown commercial catalogs are not labelled free.
        out.append({"id": mid, "free": free, "image": bool(_IMG_RE.search(mid))})
    out.sort(key=lambda m: (not m["free"],))  # stable — provider order kept
    return out


async def fetch_models(key: str, base_url: str, token: str) -> dict:
    """Validate an API key against the provider and list its models.

    Returns {valid, error, models:[{id,free,image}], free_count, image_default}
    — never contains the token itself.
    """
    import httpx

    from .config import AUTO_IMAGE_MODEL, PROVIDER_PRESETS

    preset = PROVIDER_PRESETS.get(key, {})
    headers = dict(preset.get("headers") or {})
    if token and key != "ollama":
        headers["Authorization"] = f"Bearer {token}"
    base = provider_base_url(key, base_url)
    if key in ('openai','anthropic') and not base.endswith('/v1'): base += '/v1'
    if key == 'anthropic':
        headers.pop('Authorization',None)
        headers.update({'x-api-key':token,'anthropic-version':'2023-06-01'})
    out: dict = {
        "valid": False, "error": "", "models": [], "free_count": 0,
        "images_api": bool(preset.get("images_api")),
        "image_default": AUTO_IMAGE_MODEL,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0),
                                 headers=headers, follow_redirects=False) as client:
        if key in ('ollama', 'ollama_cloud'):
            if os.getenv('VERCEL') == '1' and any(host in base for host in ('localhost', '127.0.0.1', '[::1]')):
                out['error'] = 'Local Ollama is not reachable from Vercel. Use a secured, remotely reachable runtime endpoint.'
                return out
            try:
                endpoint = base[:-3] if base.endswith('/v1') else base
                endpoint = endpoint[:-4] if endpoint.endswith('/api') else endpoint
                response = await client.get(endpoint + '/api/tags', headers={'Authorization': 'Bearer ' + token} if token else {})
                response.raise_for_status()
                tags = response.json().get('models', [])
                out['models'] = [{'id': item.get('name') or item.get('model'), 'free': key=='ollama',
                                  'size': item.get('size'), 'image': False} for item in tags if item.get('name') or item.get('model')]
                out['valid'] = bool(out['models'])
                out['free_count'] = len(out['models']) if key=='ollama' else 0
                if not out['valid']: out['error'] = 'No installed Ollama models. Install a model on your runtime, then retry.'
                return out
            except Exception:
                if key=='ollama_cloud':
                    try:
                        response=await client.get(endpoint+'/v1/models')
                        response.raise_for_status()
                        entries=response.json().get('data',[])
                        out['models']=[{'id':m['id'],'free':False,'image':False} for m in entries if m.get('id')]
                        out['valid']=bool(out['models'])
                        if out['valid']:return out
                    except Exception:pass
                out['error'] = 'Model discovery failed. Check the saved key, endpoint, provider access and quota. Local Ollama requires a reachable /api/tags endpoint.'
                return out

        # 1) key validation — openrouter's /models is public, so check /key
        if key == "openrouter":
            if not token:
                out["error"] = "enter your OpenRouter key"
                return out
            try:
                r = await client.get(f"{base}/key")
            except Exception as e:
                out["error"] = f"cannot reach openrouter.ai ({type(e).__name__})"
                return out
            if r.status_code in (401, 403):
                out["error"] = "invalid API key"
                return out
            if r.status_code >= 400:
                out["error"] = f"key check failed (HTTP {r.status_code})"
                return out

        # 2) model list — doubles as the auth check on every other provider
        try:
            r = await client.get(f"{base}/models")
        except Exception as e:
            hint = " — start it with `ollama serve`" if key == "ollama" else ""
            out["error"] = f"cannot reach {base} ({type(e).__name__}){hint}"
            return out
        if r.status_code in (401, 403):
            out["error"] = (f"Arena authentication or API access denied (HTTP {r.status_code}). Check the Arena API key and workspace API permissions."
                            if key == 'arena' else "invalid API key")
            return out
        if r.status_code >= 400:
            out["error"] = ("Arena model discovery returned HTTP 404. Use https://api.arena.ai/v1 as the API endpoint, not the dashboard URL. If using a custom gateway, verify its /models route."
                            if key == 'arena' and r.status_code == 404 else f"/models returned HTTP {r.status_code}")
            return out
        try:
            payload = r.json()
        except Exception:
            out["error"] = "provider returned a non-JSON response"
            return out

    rows = payload.get("data") if isinstance(payload, dict) else payload
    entries: list[tuple[str, dict]] = []
    for m in rows or []:
        if isinstance(m, str):
            entries.append((m, {}))
        elif isinstance(m, dict):
            mid = m.get("id") or m.get("name") or ""
            if mid:
                entries.append((str(mid), m.get("pricing") or {}))
    if not entries:
        out["error"] = "provider returned no models"
        return out

    models = classify_models(key, entries)
    if not models:
        out["error"] = "no usable chat models found"
        return out
    if out["images_api"]:
        img = next((m["id"] for m in models if m["image"]), None)
        if img:
            out["image_default"] = img
    out.update(valid=True, error="", models=models,
               free_count=sum(1 for m in models if m["free"]))
    return out


def failover_configs(exclude_key: Optional[str] = None) -> list[ProviderConfig]:
    """Configured providers to try after a failure (active excluded)."""
    return [c for c in configured_configs() if c.key != exclude_key]


class OpenAIProvider(BaseProvider):
    demo = False

    def __init__(self, cfg: Optional[ProviderConfig] = None) -> None:
        self.cfg = cfg or active_config()
        if self.cfg is None:
            raise ProviderError("bad_request", "no AI provider configured (no API token)")
        self.base = provider_base_url(self.cfg.key, self.cfg.base_url)
        if self.cfg.key in ('openai','anthropic') and not self.base.endswith('/v1'):self.base += '/v1'
        # local CPU generations (Ollama) need the full local budget — the
        # outer asyncio wait_for(LOCAL_TIMEOUT) still caps the whole call
        self.timeout = (900.0 if self.cfg.key == "ollama"
                        else settings.request_timeout)
        self.max_retries = max(1, settings.max_retries)

    @property
    def model(self) -> str:
        return self.cfg.model

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.cfg.token:
            h["Authorization"] = f"Bearer {self.cfg.token}"
        if self.cfg.key=='anthropic':
            h.pop('Authorization',None)
            h.update({'x-api-key':self.cfg.token,'anthropic-version':'2023-06-01'})
        h.update(self.cfg.headers or {})
        return h

    async def _request(self, method: str, path: str, payload: dict) -> dict:
        from .ai_hub import validate_endpoint
        try: validate_endpoint(self.base,local=self.cfg.key=='ollama',resolve=os.getenv('VERCEL')=='1')
        except Exception: raise ProviderError('bad_request','Provider endpoint is not permitted or cannot be resolved.') from None
        url = f"{self.base}{path}"
        last_err: Optional[ProviderError] = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(method, url, json=payload, headers=self._headers())
            except httpx.TimeoutException as e:
                last_err = ProviderError("timeout", f"request timed out after {self.timeout}s: {e}")
            except httpx.HTTPError as e:
                last_err = ProviderError("network", str(e))
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except Exception as e:
                        raise ProviderError("server", f"invalid JSON response: {e}")
                if resp.status_code in (401, 403):
                    # do not retry auth errors — and never echo the token
                    raise ProviderError("auth", f"HTTP {resp.status_code}", resp.status_code)
                if resp.status_code == 402:
                    raise ProviderError(
                        "payment",
                        f"HTTP 402: upstream request rejected "
                        "(top up your APInex account, or set DEMO_MODE=true in .env to explore offline)",
                        402)
                if resp.status_code == 404:
                    body = resp.text[:300]
                    if "model" in body.lower():
                        raise ProviderError(
                            "bad_request",
                            f"Model '{payload.get('model')}' not found on this provider — "
                            f"set TEXT_MODEL in .env or Settings to a model it supports. ({body})",
                            404)
                    raise ProviderError("bad_request", f"HTTP 404: {body}", 404)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else None
                    last_err = ProviderError("rate_limit", f"HTTP 429: upstream request rejected", 429)
                    if delay is None:
                        delay = self._backoff(attempt)
                    await asyncio.sleep(min(delay, 30))
                    continue
                if resp.status_code >= 500:
                    last_err = ProviderError("server", f"HTTP {resp.status_code}: upstream request rejected", resp.status_code)
                else:
                    raise ProviderError("bad_request", f"HTTP {resp.status_code}: upstream request rejected", resp.status_code)
            # backoff before next attempt
            await asyncio.sleep(self._backoff(attempt))
        assert last_err is not None
        raise last_err

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(2 ** attempt + random.uniform(0, 0.5), 20)

    async def chat(self, messages: list[dict], *, temperature: float = 0.4,
                   max_tokens: int = 2000, json_mode: bool = False) -> ChatResult:
        if self.cfg.key == 'anthropic':
            system='\n'.join(m['content'] for m in messages if m['role']=='system')
            payload={'model':self.cfg.model,'max_tokens':max_tokens,'system':system,'messages':[m for m in messages if m['role']!='system']}
            data=await self._request('POST','/messages',payload)
            u=data.get('usage',{})
            return ChatResult(''.join(b.get('text','') for b in data.get('content',[]) if b.get('type')=='text'),Usage(tokens_in=int(u.get('input_tokens',0)),tokens_out=int(u.get('output_tokens',0)),model=self.cfg.model),data)
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.cfg.key == "ollama":
            # small local models can loop on long structured JSON —
            # standard OpenAI param, ollama accepts it
            payload["frequency_penalty"] = 0.5
        if self.cfg.reasoning_off:
            # free reasoning models burn the token budget on reasoning and can
            # return content=null — disable reasoning for pipeline calls
            payload["reasoning"] = {"enabled": False}
        try:
            data = await self._request("POST", "/chat/completions", payload)
        except ProviderError as e:
            # some OpenAI-compatible gateways reject response_format — retry plain
            if json_mode and e.kind == "bad_request" and "response_format" in e.message:
                payload.pop("response_format", None)
                data = await self._request("POST", "/chat/completions", payload)
            elif json_mode and e.kind == "bad_request" and e.status == 404:
                # gateway may not accept response_format either — but 404 here is
                # a missing route/model; surface it with the friendly message
                raise
            else:
                raise
        try:
            msg = data["choices"][0]["message"]
            text = msg.get("content") or ""
            if not text.strip() and msg.get("reasoning"):
                # reasoning model returned no content — surface a clear error
                raise ProviderError(
                    "server",
                    "model returned reasoning but no content (increase max_tokens "
                    "or disable reasoning for this model)")
        except (KeyError, IndexError) as e:
            raise ProviderError("server", f"unexpected response shape: {e}")
        u = data.get("usage", {}) or {}
        tin, tout = int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
        # OpenRouter reports usage.cost: 0 for :free models → bill nothing.
        # cost absent (None) → fall back to the price-sheet estimate.
        cost_raw = u.get("cost")
        cost = _cost(tin, tout) if cost_raw is None else float(cost_raw)
        usage = Usage(tin, tout, cost, self.cfg.model, demo=False)
        return ChatResult(text=text, usage=usage, raw=data)

    async def image(self, prompt: str, *, size: str = "1024x1024") -> bytes:
        payload = {"model": settings.image_model, "prompt": prompt, "size": size, "n": 1}
        data = await self._request("POST", "/images/generations", payload)
        try:
            item = data["data"][0]
        except (KeyError, IndexError) as e:
            raise ProviderError("server", f"unexpected image response: {e}")
        if item.get("b64_json"):
            import base64
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(item["url"])
                r.raise_for_status()
                return r.content
        raise ProviderError("server", "image response had neither b64_json nor url")


# --------------------------------------------------------------------------
# Demo provider — deterministic, offline, labelled DEMO everywhere
# --------------------------------------------------------------------------
class DemoProvider(BaseProvider):
    """Produces structured, believable outputs derived from the prompt itself.

    It never invents prices or facts beyond what appears in the user brief:
    numbers/prices are only echoed if they were present in the input.
    """
    demo = True

    async def chat(self, messages: list[dict], *, temperature: float = 0.4,
                   max_tokens: int = 2000, json_mode: bool = False) -> ChatResult:
        await asyncio.sleep(random.uniform(0.25, 0.7))  # simulate latency
        system = " ".join(m["content"] for m in messages if m.get("role") == "system")
        user = " ".join(m["content"] for m in messages if m.get("role") == "user")
        blob = system + "\n" + user
        marker = _extract_marker(system)  # orchestration tags prompts with [TASK:...]
        text = self._render(marker, blob, json_mode)
        tin = len(blob) // 4
        tout = len(text) // 4
        usage = Usage(tin, tout, 0.0, "demo-provider", demo=True)
        return ChatResult(text=text, usage=usage, raw={"demo": True})

    async def image(self, prompt: str, *, size: str = "1024x1024") -> bytes:
        # demo: return a tiny PNG (1x1) — UI falls back to generated SVG placeholder art
        import base64
        await asyncio.sleep(0.2)
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )

    # -- deterministic renderers ------------------------------------------
    def _render(self, marker: str, blob: str, json_mode: bool) -> str:
        brief = _extract_block(blob, "BRIEF")
        brand = _extract_block(blob, "BRAND_KIT") or ""
        brand_name = _first_line(brand) or "the brand"

        if marker == "plan":
            tasks = _demo_plan_tasks(brief, brand_name)
            out = {
                "summary": f"Plan for: {_short(brief, 120)}",
                "questions": _demo_questions(brief),
                "tasks": tasks,
                "risks": ["Claims must stay within the client brief (no invented prices or guarantees)."],
            }
            return json.dumps(out, ensure_ascii=False)

        if marker == "qa":
            # strict QA: approve unless the output looks empty/placeholder
            issues = []
            if re.search(r"\bTODO\b|\bplaceholder\b|\bTBD\b", blob, re.I):
                issues.append("Output contains TODO/placeholder markers — not deliverable.")
            if len(blob) < 120:
                issues.append("Output too thin — expand with concrete detail from the brief.")
            out = {"approved": not issues, "issues": issues,
                   "score": 8 if not issues else 4,
                   "notes": "Checked against brief, brand kit and acceptance criteria."}
            return json.dumps(out, ensure_ascii=False)

        if marker == "campaign":
            return json.dumps(_demo_campaign(brief, brand), ensure_ascii=False)

        if marker == "images":
            return json.dumps(_demo_images(brief, brand_name), ensure_ascii=False)

        if marker == "calendar":
            return json.dumps(_demo_calendar(brief, brand_name), ensure_ascii=False)

        if marker == "meeting":
            return json.dumps({"ideas": _demo_ideas(blob)}, ensure_ascii=False)

        if marker == "standup":
            return json.dumps(_demo_standup(blob), ensure_ascii=False)

        if marker == "trends":
            return json.dumps(_demo_trends(brief), ensure_ascii=False)

        if json_mode:
            # generic JSON: echo a small structured object derived from input
            return json.dumps({"result": _short(blob, 400), "demo": True}, ensure_ascii=False)

        # generic text: role-aware canned answer built strictly from the input
        role = _extract_field(blob, "ROLE") or "Agent"
        role = re.split(r"[.(\n]", role)[0].strip() or "Agent"   # first sentence only
        # prefer the BRIEF block, else use the raw request content
        source = brief or _short(blob, 260)
        return (
            f"[DEMO · {role}] Reviewed the request against the brief and brand kit.\n\n"
            f"Key points taken from the request:\n"
            f"• {source}\n"
            f"• Brand guardrails respected: no invented prices, no unsupported claims.\n"
            f"• Output structured as JSON + human-readable summary (see attached deliverable).\n\n"
            f"Self-check passed: follows brief, matches tone, ready for QA review."
        )


def _extract_marker(system: str) -> str:
    m = re.search(r"\[TASK:([a-z_]+)\]", system)
    return m.group(1) if m else ""


def _extract_block(blob: str, name: str) -> str:
    m = re.search(rf"<<<{name}>>>(.*?)<<<END{name}>>>", blob, re.S)
    return m.group(1).strip() if m else ""


def _extract_field(blob: str, name: str) -> str:
    m = re.search(rf"^{name}:\s*(.+)$", blob, re.M)
    return m.group(1).strip() if m else ""


def _first_line(s: str) -> str:
    for line in s.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _short(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _brief_facts(brief: str) -> list[str]:
    """Pull concrete facts (prices, numbers) out of the brief — demo agent
    outputs may only echo these, never invent new ones."""
    return list(dict.fromkeys(re.findall(r"[^\n.,;]*?(?:\d[\d.,]*\s*(?:%|€|\$|TND|USD|EUR|DA|days?|hours?|weeks?|months?))[^\n.,;]*", brief, re.I)))


def _demo_questions(brief: str) -> list[str]:
    if len(brief.strip()) < 40:
        return ["Could you share a longer brief: goals, audience, deadline and budget?"]
    if not re.search(r"budget|prix|price|coût|cost", brief, re.I):
        return []  # only ask when genuinely missing something blocking
    return []


def _demo_plan_tasks(brief: str, brand: str) -> list[dict]:
    seed = hashlib.md5(brief.encode()).hexdigest()[:4]
    base = [
        ("lina", "Define visual direction", "Extract palette, layout principles and image style from the brief + brand kit. Produce a design direction sheet.", ["design_direction"]),
        ("sami", "Write core messaging", "Slogans, value proposition and tone-of-voice copy strictly from the brief facts.", ["messaging"]),
        ("zed", "Create image assets", "Generate post/ad images (1:1, 4:5, 9:16) in brand colors with logo applied.", ["images"]),
        ("karim", "Build landing page", "Responsive HTML/CSS/JS landing page using approved copy and design direction.", ["page"]),
        ("yara", "SEO & metadata", "Keyword set, meta titles/descriptions and on-page recommendations.", ["seo"]),
        ("adam", "Ads campaign package", "Facebook/Instagram campaign: audience, budget plan, 3 A/B/C variants, KPIs, UTM links.", ["campaign"]),
        ("mona", "30-day content calendar", "Calendar with captions, hashtags, best times, Reels/Stories ideas.", ["calendar"]),
        ("rami", "QA review", "Strict review of every deliverable against brief + brand kit; reject and send back if off-brief.", ["qa"]),
    ]
    tasks = []
    for i, (assignee, title, desc, acc) in enumerate(base):
        tid = f"t{seed}{i}"
        deps = []
        if i in (3, 4, 6):
            deps = [f"t{seed}0"]                 # ← design direction
        if i in (5, 6):
            deps = deps + [f"t{seed}{2 if i == 5 else 3}"]
        if i == 7:
            deps = [f"t{seed}{k}" for k in range(7)]  # QA gates on everything
        tasks.append({
            "id": tid, "title": title, "description": desc,
            "assignee": assignee, "depends": list(dict.fromkeys(deps)),
            "acceptance": acc + ["no_invented_facts", "brand_kit_respected"],
        })
    return tasks


def _demo_campaign(brief: str, brand: str) -> dict:
    facts = _brief_facts(brief)
    brand_name = _first_line(brand) or "Your Brand"
    audience_core = "Adults 25-54, local area, interests aligned to the offer in the brief"
    variants = []
    for i, (hook, cta) in enumerate([
        ("Protect what matters most — get a free quote in minutes.", "Get Quote"),
        ("Coverage that fits your life. Compare plans side by side.", "Learn More"),
        ("Smart protection, simple process. Start your free check today.", "Sign Up"),
    ]):
        variants.append({
            "label": ["A", "B", "C"][i],
            "headline": hook.split(" — ")[0],
            "primary_text": hook + (f" Fact from brief: {facts[0]}." if facts and i == 0 else ""),
            "cta": cta,
            "image_brief": f"Brand colors, logo top-left, friendly local scene, minimal text (≤20% of frame).",
            "utm": f"utm_source=facebook&utm_medium=paid&utm_campaign=launch_{seed_of(brief)}&utm_content=var_{i}",
        })
    return {
        "objective": "Leads / Conversions",
        "audience": {"age": "25-54", "location": "From brief / client region", "interests": audience_core,
                     "placements": ["Facebook Feed", "Instagram Feed", "Stories"]},
        "budget_plan": {"note": "Budget must be confirmed by the client — not invented here.",
                        "daily": "Awaiting client confirmation", "duration": "14 days suggested"},
        "variants": variants,
        "kpi": ["CTR ≥ 1.2%", "CPC ≤ benchmark", "CPA ≤ client target", "Frequency < 3"],
        "compliance_notes": ["No guarantees of savings or outcomes", "Avoid 'best/#1/100%' claims"],
        "sources": [],
    }


def seed_of(brief: str) -> str:
    return hashlib.md5(brief.encode()).hexdigest()[:6]


def _demo_calendar(brief: str, brand: str) -> dict:
    themes = ["Educational tip", "Customer story (needs client input)", "Product highlight",
              "Behind the scenes", "Myth vs fact", "Q&A carousel", "Reel: 30-sec explainer",
              "Community post", "Checklist", "Offer reminder (no invented discount)"]
    days = []
    for d in range(30):
        theme = themes[d % len(themes)]
        days.append({
            "day": d + 1,
            "date_offset": d + 1,
            "channel": ["instagram", "facebook", "instagram"][d % 3],
            "format": ["feed", "reel", "story", "carousel"][d % 4],
            "theme": theme,
            "caption": f"{brand}: {theme}. More info straight from the campaign brief — details at the link in bio.",
            "hashtags": ["#marketing", "#localbusiness", f"#{brand.lower().replace(' ', '')}"],
            "best_time": ["12:00", "18:00", "09:30"][d % 3],
            "notes": "",
        })
    return {"days": days, "reels_scripts": [
        {"day": 3, "script": "Hook 0-3s: question from brief. 3-10s: key fact. 10-15s: CTA."},
        {"day": 17, "script": "Hook: myth vs fact. Body: explanation. End: CTA button."},
    ], "carousels": [{"day": 6, "slides": 5, "title": "5-point checklist"}]}


def _demo_ideas(blob: str) -> list[dict]:
    return [
        {"agent": "lina", "idea": "Lead the visual concept with one bold brand color + generous whitespace."},
        {"agent": "sami", "idea": "Open with a question that mirrors the client's brief language."},
        {"agent": "adam", "idea": "Segment audiences by intent; keep budget flexible until week-1 data."},
        {"agent": "mona", "idea": "Anchor the calendar on 3 hero posts; fill the rest with repurposed assets."},
        {"agent": "yara", "idea": "Capture long-tail keywords from the FAQ section of the brief."},
        {"agent": "karim", "idea": "Ship a single landing page fast; iterate after first conversions."},
        {"agent": "zed", "idea": "One photoshoot style, many crops — keeps the feed cohesive."},
        {"agent": "rami", "idea": "Add a pre-publish compliance checklist to every campaign."},
        {"agent": "pixel", "idea": "I can compile last week's metrics into a one-pager (learning!)."},
    ]


def _demo_images(brief: str, brand: str) -> dict:
    return {
        "summary": "Image set planned in brand colors: one hero per format, logo top-left, minimal text.",
        "images": [
            {"name": "hero_square", "ratio": "1:1", "prompt": "Hero visual, brand palette, logo top-left, friendly local scene, ≤20% text."},
            {"name": "post_portrait", "ratio": "4:5", "prompt": "Value-prop visual with one clear message, brand colors, CTA corner."},
            {"name": "story_vertical", "ratio": "9:16", "prompt": "Story format, bold single headline area, logo safe-zone top, CTA swipe-up area."},
        ],
    }


def _demo_standup(blob: str) -> dict:
    return {
        "done": ["Brief analysed and plan approved", "Core messaging drafted", "Design direction agreed"],
        "blockers": ["Awaiting client confirmation on budget (not invented by the team)"],
        "next": ["Build landing page", "Generate image set", "Run QA pass"],
        "note": "Stand-up generated from the project activity log.",
    }


def _demo_trends(brief: str) -> dict:
    return {
        "summary": "Short-form video and authenticity-led content continue to outperform polished ads; "
                   "local/service businesses win with clear CTAs and social proof. (Demo summary — configure web search for live sources.)",
        "competitors": [
            {"name": "Regional peer A", "observation": "Heavy Reels use, consistent weekly cadence.", "source": ""},
            {"name": "Regional peer B", "observation": "Carousel explainers + lead-gen forms.", "source": ""},
        ],
        "sources": [],
        "demo": True,
    }


# --------------------------------------------------------------------------
# Session-level demo fallback: when every real provider reports a billing
# problem (HTTP 402), the app can keep running on the clearly-labelled demo
# provider until accounts are fixed. Real API resumes automatically
# on restart or when settings change.
session_fallback = False


def activate_session_fallback() -> None:
    global session_fallback, _provider
    session_fallback = True
    _provider = DemoProvider()


def get_provider() -> BaseProvider:
    from .hosted_settings import refresh
    refresh()
    if session_fallback:
        return DemoProvider()
    if settings.is_demo:
        return DemoProvider()
    cfg = active_config()
    if cfg is None:
        if os.getenv("VERCEL") == "1":
            raise ProviderError("auth", "Add a cloud provider API key in Settings before starting AI work.")
        return DemoProvider()
    return OpenAIProvider(cfg)


_provider: Optional[BaseProvider] = None


def provider() -> BaseProvider:
    global _provider
    if os.getenv("VERCEL") == "1":
        return get_provider()
    if _provider is None:
        _provider = get_provider()
    return _provider


def reset_provider() -> None:
    """Called when settings change so the next call picks up new config."""
    global _provider, session_fallback
    _provider = None
    session_fallback = False
