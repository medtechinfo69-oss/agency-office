"""Force-check EVERY backend endpoint end-to-end.

Covers: core reads, provider key validation + model lists, settings, full
project lifecycle, prompt/agent/schedule CRUD, logo upload, all LLM-backed
actions (standup, trends, meeting, campaign, calendar, insight, chat),
image generation + media serving, meta draft approval gate, ZIP export,
control actions, and the frontend itself.

Run:  python3 tests/api_sweep.py        (backend :8000 + web :5173 up)
"""
from __future__ import annotations

import io
import sys
import time
import zipfile

import httpx

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:5173"
results: list[tuple[str, bool, str]] = []

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d994800000000"
    "49454e44ae426082")


def hit(name: str, method: str, path: str, *, json_body=None,
        good=None, timeout: float = 30, base: str = API) -> httpx.Response | None:
    t0 = time.time()
    try:
        r = httpx.request(method, base + path, json=json_body,
                          timeout=timeout, follow_redirects=True)
        ms = int((time.time() - t0) * 1000)
        ok = (r.status_code < 400) if good is None else good(r.status_code)
        detail = f"HTTP {r.status_code} · {ms}ms"
        if not ok:
            detail += " · " + r.text[:140].replace("\n", " ")
        results.append((name, ok, detail))
        return r
    except Exception as e:
        results.append((name, False, f"EXC {type(e).__name__}: {e}"))
        return None


def main() -> int:
    print("=" * 72)
    print("AGENCY OFFICE — full API sweep")
    print("=" * 72)

    # ---------- core reads ----------
    hit("health", "GET", "/api/health")
    hit("settings GET", "GET", "/api/settings")
    hit("providers GET", "GET", "/api/providers")
    hit("agents GET", "GET", "/api/agents")
    hit("templates GET", "GET", "/api/templates")
    hit("prompts GET", "GET", "/api/prompts")
    hit("projects GET", "GET", "/api/projects")

    # ---------- provider key validation + model discovery ----------
    r = hit("models: openrouter (stored key)", "POST",
            "/api/providers/openrouter/models", json_body={})
    if r is not None:
        try:
            d = r.json()
            n = len(d.get("models", []))
            results.append(("openrouter key valid + free models listed",
                            bool(d.get("valid")) and n > 0,
                            f"valid={d.get('valid')} models={n} "
                            f"free={d.get('free_count')}"))
        except Exception as e:
            results.append(("openrouter key valid + free models listed", False, str(e)))
    r = hit("models: apinex (stored key)", "POST",
            "/api/providers/apinex/models", json_body={})
    if r is not None:
        try:
            d = r.json()
            results.append(("apinex key valid", bool(d.get("valid")),
                            f"models={len(d.get('models', []))}"))
        except Exception as e:
            results.append(("apinex key valid", False, str(e)))
    r = hit("models: BAD key rejected", "POST",
            "/api/providers/openrouter/models",
            json_body={"token": "sk-or-v1-definitely-not-a-key"},
            good=lambda s: s == 200)
    if r is not None:
        try:
            d = r.json()
            results.append(("bad key → valid:false", d.get("valid") is False,
                            d.get("error", "")))
        except Exception as e:
            results.append(("bad key → valid:false", False, str(e)))
    hit("models: unknown provider → 404", "POST", "/api/providers/nope/models",
        json_body={}, good=lambda s: s == 404)
    # re-activate whichever provider is currently active — exercises the
    # endpoint without stealing the slot from the configured local/cloud one
    r = hit("providers GET (find active)", "GET", "/api/providers")
    if r is not None and r.status_code < 400:
        act = next((p["key"] for p in r.json() if p.get("active")), "openrouter")
        hit(f"provider activate ({act})", "POST", "/api/providers/activate",
            json_body={"provider": act})

    # ---------- settings write ----------
    hit("settings PUT", "PUT", "/api/settings", json_body={"sound": "on"})

    # ---------- project lifecycle ----------
    r = hit("project CREATE", "POST", "/api/projects", json_body={
        "name": "API sweep project",
        "brief": "Brief for the API sweep: promote a local bakery on Instagram. "
                 "No invented prices. Deliverables: captions, 3 creatives, 30-day calendar.",
    })
    if r is None or r.status_code >= 400:
        print("\n".join(f"[{'PASS' if ok else 'FAIL'}] {n} — {d}" for n, ok, d in results))
        return 1
    pid = r.json()["id"]
    print(f"→ project {pid}")

    hit("project GET", "GET", f"/api/projects/{pid}")
    hit("messages GET", "GET", f"/api/projects/{pid}/messages")
    hit("activity GET", "GET", f"/api/projects/{pid}/activity")
    hit("memory GET", "GET", f"/api/projects/{pid}/memory")
    hit("brand GET", "GET", f"/api/projects/{pid}/brand")
    hit("brand PUT", "PUT", f"/api/projects/{pid}/brand", json_body={
        "name": "Sweep Bakery", "colors": ["#4b4be3", "#0b6139"],
        "fonts": ["Inter"], "tone": "friendly",
        "rules": ["no invented prices"], "logo_url": ""})
    hit("logo UPLOAD", "POST", f"/api/projects/{pid}/brand/logo",
        json_body=None)  # replaced below with multipart

    # multipart logo (httpx request() can't mix json+files, redo properly)
    t0 = time.time()
    try:
        r = httpx.post(f"{API}/api/projects/{pid}/brand/logo",
                       files={"file": ("logo.png", PNG_1PX, "image/png")},
                       timeout=30)
        ok = r.status_code < 400
        results[-1] = ("logo UPLOAD", ok,
                       f"HTTP {r.status_code} · {int((time.time()-t0)*1000)}ms"
                       + ("" if ok else " · " + r.text[:100]))
    except Exception as e:
        results[-1] = ("logo UPLOAD", False, str(e))

    # ---------- CRUD: prompts, agents, schedules ----------
    r = hit("prompt CREATE", "POST", "/api/prompts", json_body={
        "name": "sweep-prompt", "category": "custom", "content": "test"})
    if r is not None and r.status_code < 400:
        prid = r.json().get("id") or r.json().get("pid")
        hit("prompt DELETE", "DELETE", f"/api/prompts/{prid}",
            good=lambda s: s < 400)
    r = hit("agent CREATE (custom)", "POST", "/api/agents", json_body={
        "name": "Sweepy", "role": "Tester", "personality": "meticulous",
        "system_prompt": "You verify APIs.", "skills": ["testing"],
        "color": "#4b4be3", "strictness": 3})
    if r is not None and r.status_code < 400:
        aid = r.json().get("id")
        hit("agent DELETE", "DELETE", f"/api/agents/{aid}",
            good=lambda s: s < 400)
    r = hit("schedule CREATE", "POST", f"/api/projects/{pid}/schedules",
            json_body={"name": "sweep-weekly", "kind": "weekly_posts",
                       "interval_hours": 168, "enabled": False})
    hit("schedules GET", "GET", f"/api/projects/{pid}/schedules")
    if r is not None and r.status_code < 400:
        sid = r.json().get("id")
        if sid:
            hit("schedule PATCH", "PATCH", f"/api/schedules/{sid}",
                json_body={"enabled": True})

    # ---------- LLM-backed actions (real OpenRouter, free models) ----------
    print("→ LLM actions (free OpenRouter — this takes a few minutes)…")
    hit("standup (LLM)", "POST", f"/api/projects/{pid}/standup",
        timeout=400)
    hit("trends scan (LLM+web)", "POST", f"/api/projects/{pid}/trends",
        json_body={"query": "bakery instagram"}, timeout=700)
    hit("meeting roundtable (LLM)", "POST", f"/api/projects/{pid}/meeting",
        json_body={"topic": "Best growth move for the bakery"}, timeout=400)
    hit("campaign package (LLM+images)", "POST",
        f"/api/projects/{pid}/campaign", json_body={"brief_override": ""},
        timeout=700)
    hit("30-day calendar (LLM)", "POST", f"/api/projects/{pid}/calendar",
        json_body={"days": 30}, timeout=1000)
    hit("standups GET", "GET", f"/api/projects/{pid}/standups")
    hit("meetings GET", "GET", f"/api/projects/{pid}/meetings")

    # ---------- images (automatic Pollinations) ----------
    r = hit("image GENERATE (auto free)", "POST", f"/api/projects/{pid}/images",
            json_body={"title": "Sweep creative", "ratio": "1:1",
                       "prompt": "warm bakery storefront", "slug": "sweep"},
            timeout=150)
    if r is not None and r.status_code < 400:
        try:
            d = r.json()
            url = d.get("url", "")
            results.append(("image saved + media served",
                            bool(url) and d.get("source") in ("api", "placeholder_svg"),
                            f"source={d.get('source')} model={d.get('model')}"))
            if url:
                hit("media GET (image file)", "GET", url)
        except Exception as e:
            results.append(("image saved + media served", False, str(e)))

    # ---------- analytics + insight ----------
    hit("analytics ADD", "POST", f"/api/projects/{pid}/analytics",
        json_body={"campaign": "sweep-test",
                   "metrics": {"reach": 1200, "ctr": 1.4},
                   "notes": "synthetic sweep row"})
    hit("analytics GET", "GET", f"/api/projects/{pid}/analytics")
    hit("analytics insight (LLM)", "POST",
        f"/api/projects/{pid}/analytics/insight", timeout=400)

    # ---------- deliverables, meta gate, export ----------
    hit("deliverables GET", "GET", f"/api/projects/{pid}/deliverables")
    hit("meta drafts GET", "GET", f"/api/projects/{pid}/meta/drafts")
    r = hit("meta draft CREATE", "POST", f"/api/projects/{pid}/meta/drafts",
            json_body={"payload": {"channel": "instagram", "caption": "hi",
                                   "status": "draft"}})
    if r is not None and r.status_code < 400:
        did = (r.json() or {}).get("draft_id") or (r.json() or {}).get("id")
        if did:
            hit("meta publish WITHOUT approve → 400 (gate)", "POST",
                f"/api/projects/{pid}/meta/publish",
                json_body={"draft_id": did, "approve": False},
                good=lambda s: s == 400)
    r = hit("export ZIP", "GET", f"/api/projects/{pid}/export", timeout=60)
    if r is not None and r.status_code < 400:
        try:
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            bad = zf.testzip()
            results.append(("export ZIP valid", bad is None,
                            f"{len(zf.namelist())} files"))
        except Exception as e:
            results.append(("export ZIP valid", False, str(e)))

    # ---------- control + chat (chat last: kicks Nora's real reply) ----------
    hit("control pause", "POST", f"/api/projects/{pid}/control",
        json_body={"action": "pause"})
    hit("control resume", "POST", f"/api/projects/{pid}/control",
        json_body={"action": "resume"})
    hit("chat → Nora (LLM reply async)", "POST", f"/api/projects/{pid}/chat",
        json_body={"text": "Reply with exactly: SWEEP OK"}, timeout=60)

    # ---------- frontend ----------
    hit("frontend serves app", "GET", "/", base=WEB, timeout=15)

    # ---------- report ----------
    print()
    print("=" * 72)
    failed = 0
    for name, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{tag}] {name:<44} {detail}")
    print("=" * 72)
    llm = sum(1 for n, _, _ in results if "LLM" in n)
    print(f"{len(results) - failed}/{len(results)} passed "
          f"({llm} LLM-backed, all real API)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
