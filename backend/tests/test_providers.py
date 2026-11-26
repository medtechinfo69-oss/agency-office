"""Tests for the multi-provider system: presets, config resolution, failover."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import PROVIDER_PRESETS, match_preset, settings  # noqa: E402
from app.provider import (  # noqa: E402
    ProviderConfig, active_config, configured_configs, failover_configs,
    OpenAIProvider, ProviderError,
)


def test_presets_exist_with_free_models():
    for key in ("openrouter", "apinex", "groq", "gemini", "ollama"):
        assert key in PROVIDER_PRESETS
        p = PROVIDER_PRESETS[key]
        assert p["base_url"].startswith("http")
        assert p["model"]
        assert p["free"] is True


def test_openrouter_preset_is_openai_compatible():
    p = PROVIDER_PRESETS["openrouter"]
    assert p["base_url"] == "https://openrouter.ai/api/v1"
    assert ":free" in p["model"]          # free model by default
    assert p["reasoning_off"] is True     # null-content guard


def test_match_preset_by_host():
    assert match_preset("https://openrouter.ai/api/v1") == "openrouter"
    assert match_preset("https://api.apinex.bond/v1") == "apinex"
    assert match_preset("https://api.groq.com/openai/v1") == "groq"
    assert match_preset("https://example.com/v1") is None


def test_active_config_resolves_from_settings():
    cfg = active_config()
    # the app seeds at least one tokened provider in tests (openrouter/apinex)
    if any((c.get("token") for c in settings.provider_creds.values())):
        assert cfg is not None
        assert cfg.key == settings.active_provider or cfg.token
        assert cfg.model
        assert cfg.base_url.startswith("http")


def test_failover_chain_excludes_active_and_untokened():
    chain = configured_configs()
    keys = [c.key for c in chain]
    assert len(keys) == len(set(keys)), "no duplicate providers in chain"
    ac = active_config()
    if ac:
        assert keys[0] == ac.key  # active first
        fails = failover_configs(exclude_key=ac.key)
        assert ac.key not in [c.key for c in fails]
    # ollama needs no token so it may always join the chain
    for c in chain:
        assert c.token, "every chain entry must have a token (ollama auto)"


def test_provider_config_is_immutable_data():
    cfg = ProviderConfig(key="x", label="X", base_url="http://a/v1/",
                         token="t", model="m")
    assert cfg.base_url.endswith("/v1/")  # frozen dataclass keeps value as given
    with pytest.raises(Exception):
        cfg.model = "other"  # type: ignore[misc]


def test_openai_provider_requires_config():
    # monkeypatch-free: passing an explicit empty config path
    old = settings.active_provider
    old_creds = settings.provider_creds
    try:
        settings.provider_creds = {"none": {"token": "", "base_url": "", "model": ""}}
        settings.active_provider = "none"
        from app import provider as pm
        pm.reset_provider()
        with pytest.raises(ProviderError):
            OpenAIProvider(pm.active_config())
    finally:
        settings.active_provider = old
        settings.provider_creds = old_creds
        pm.reset_provider()


def test_reasoning_off_flag_on_payload(monkeypatch):
    """OpenRouter config must disable reasoning (free models return null content)."""
    cfg = ProviderConfig(key="openrouter", label="OpenRouter",
                         base_url="https://openrouter.ai/api/v1",
                         token="sk-test", model="m:free", reasoning_off=True)
    p = OpenAIProvider(cfg)
    captured = {}

    async def fake_request(method, path, payload):
        captured.update(payload)
        return {"choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0}}

    monkeypatch.setattr(p, "_request", fake_request)
    import asyncio
    res = asyncio.run(p.chat([{"role": "user", "content": "x"}], json_mode=True))
    assert res.text == "hi"
    assert captured["reasoning"] == {"enabled": False}
    assert captured["model"] == "m:free"
    assert captured["response_format"] == {"type": "json_object"}
    assert res.usage.cost_usd == 0  # :free model reports cost 0 → not billed


def test_classify_models_free_and_image_heuristics():
    from app.provider import classify_models
    # openrouter: :free suffix and zero pricing both count
    rows = [
        ("nvidia/nemotron-3-ultra-550b-a55b:free", {"prompt": "0.1", "completion": "0.4"}),
        ("some/paid-model", {"prompt": "0.1", "completion": "0.4"}),
        ("zero/cost-model", {"prompt": "0", "completion": "0"}),
        ("provider/flux-schnell", {"prompt": "0", "completion": "0"}),
        ("whisper-large-v3", {"prompt": "0", "completion": "0"}),
    ]
    out = classify_models("openrouter", rows)
    ids = [m["id"] for m in out]
    assert "whisper-large-v3" not in ids, "non-chat models excluded"
    assert ids[0].endswith(":free"), "free models sorted first (stable)"
    by_id = {m["id"]: m for m in out}
    assert by_id["some/paid-model"]["free"] is False
    assert by_id["zero/cost-model"]["free"] is True
    assert by_id["provider/flux-schnell"]["image"] is True
    assert by_id["nvidia/nemotron-3-ultra-550b-a55b:free"]["image"] is False

    # apinex: free/* prefix marks free
    out = classify_models("apinex", [("free/glm-5.3-flash", {}), ("claude-opus-5.5", {})])
    assert {m["id"]: m["free"] for m in out} == {"free/glm-5.3-flash": True,
                                                 "claude-opus-5.5": False}
    # groq/ollama: everything listed is usable on the free/local tier
    out = classify_models("groq", [("llama-3.3-70b-versatile", {})])
    assert out[0]["free"] is True


def test_fetch_models_unreachable_provider_is_clear_error():
    import asyncio
    from app.provider import fetch_models
    res = asyncio.run(fetch_models("groq", "http://127.0.0.1:9/v1", "gsk_x"))
    assert res["valid"] is False
    assert "cannot reach" in res["error"]
    assert res["models"] == []


def test_fetch_models_rejects_missing_openrouter_key():
    import asyncio
    from app.provider import fetch_models
    res = asyncio.run(fetch_models(
        "openrouter", "https://openrouter.ai/api/v1", ""))
    assert res["valid"] is False
    assert "key" in res["error"].lower()


def test_free_model_usage_not_double_charged(monkeypatch):
    cfg = ProviderConfig(key="x", label="X", base_url="http://a/v1",
                         token="t", model="m")
    p = OpenAIProvider(cfg)

    async def fake_request(method, path, payload):
        return {"choices": [{"message": {"content": "yo"}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "cost": 0}}

    monkeypatch.setattr(p, "_request", fake_request)
    import asyncio
    res = asyncio.run(p.chat([{"role": "user", "content": "x"}]))
    # OpenRouter :free → cost 0 wins over the price-sheet estimate
    assert res.usage.cost_usd == 0
    assert res.usage.tokens_in == 1000
