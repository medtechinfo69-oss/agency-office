"""Headless-browser smoke test for AGENCY OFFICE (redesigned shell).

Checks: page loads, isometric office renders, WebSocket connects, chat →
plan approval flow works, modals open, no console errors.
Run:  python3 tests/smoke_ui.py   (backend :8000 + frontend :5173 must run)
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
errors: list[str] = []
failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failed.append(name)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2500)

        # 1. title + banner
        check("page title", "AGENCY OFFICE" in page.title())
        check("isometric office present", page.locator(".iso-scene").count() >= 1)

        # 2. scene has real content (svg nodes, not blank)
        nodes = page.evaluate(
            "() => document.querySelectorAll('.iso-scene *').length"
        )
        check("scene not blank", nodes > 40, f"nodes={nodes}")

        # 3. shell panels present
        check("sidebar", page.locator(".sidebar").count() == 1)
        check("topbar", page.locator(".topbar").count() == 1)
        check("floor cards", page.locator(".floor-card").count() >= 3)

        # 4. live connection dot turns green (WS opened)
        page.wait_for_timeout(1500)
        conn_on = page.evaluate("() => !!document.querySelector('.live-dot.on')")
        check("websocket connected", conn_on)

        # 5. create a FRESH project — on an empty office the New Project
        #    modal auto-opens on first load; otherwise open it from Projects
        if page.locator(".modal").count() == 0:
            page.locator(".side-item", has_text="Projects").first.click()
            page.wait_for_timeout(600)
            page.click("button:has-text('New project')")
        page.wait_for_timeout(600)
        page.fill(".modal input", "Smoke test project")
        page.fill(".modal textarea", "Test brief: promote a local bakery on Instagram this month.")
        page.click(".modal .btn.primary")
        # approval card lives on the Office page
        page.locator(".side-item", has_text="Office").first.click()
        page.wait_for_timeout(700)
        # real AI plans take 30–150s (cloud) — and up to ~400s on local CPU
        approval = 0
        for _ in range(300):
            page.wait_for_timeout(2000)
            approval = page.locator(".approval-card").count()
            if approval:
                break
        check("plan approval card", approval >= 1, f"count={approval}")

        # 6. approve → tasks appear in kanban (Projects page)
        if approval:
            page.click(".approval-card .btn.good")
        page.locator(".side-item", has_text="Projects").first.click()
        page.wait_for_timeout(900)
        cards = 0
        for _ in range(25):  # up to 50s
            cards = page.locator(".kanban-card").count()
            if cards:
                break
            page.wait_for_timeout(2000)
        check("kanban cards after approve", cards >= 1, f"count={cards}")

        # 7. click an agent → side panel
        page.locator(".side-item", has_text="Office").first.click()
        page.wait_for_timeout(700)
        agents = page.locator("[data-agent]")
        if agents.count():
            agents.first.click()
            page.wait_for_timeout(800)
        check("agent panel opens on click", page.locator(".agent-panel").count() >= 1)
        if page.locator(".agent-panel .ap-close").count():
            page.click(".agent-panel .ap-close")

        # 8. settings page (Connections tab default)
        page.locator(".side-item", has_text="Settings").first.click()
        page.wait_for_timeout(900)
        check("settings screen", page.locator(".settings-screen").count() >= 1)
        # token field must never show a real value
        tok = page.locator("input[type=password]").first
        if tok.count():
            val = tok.input_value()
            check("token not exposed", val == "" or "•" in val, val)
        else:
            check("token not exposed", True)

        # 9. preview modal (Chat page tools)
        page.locator(".side-item", has_text="Chat").first.click()
        page.wait_for_timeout(600)
        page.click("text=👁 Preview")
        page.wait_for_timeout(1500)
        check("preview modal", page.locator(".modal").count() == 1)
        if page.locator(".modal .ap-close").count():
            page.click(".modal .ap-close")
        page.wait_for_timeout(400)

        # 10. theme toggle (dark → html.theme-dark)
        page.click('.theme-seg button[title="Night"]')
        page.wait_for_timeout(600)
        dark = page.evaluate("() => document.documentElement.classList.contains('theme-dark')")
        check("dark theme class", dark)
        page.click('.theme-seg button[title="Day"]')
        page.wait_for_timeout(400)

        # 11. language switch (FR)
        page.select_option(".lang-pick", "fr")
        page.wait_for_timeout(500)
        fr_text = page.locator(".sidebar").inner_text()
        check("french UI", "Bureau" in fr_text or "Projets" in fr_text, fr_text[:80])
        page.select_option(".lang-pick", "en")

        # Screenshots are opt-in so normal test runs leave the project clean.
        if screenshot := os.environ.get("SMOKE_SCREENSHOT"):
            page.screenshot(path=screenshot, full_page=False)
            print(f"screenshot → {screenshot}")

        browser.close()

    real_errors = [e for e in errors if "favicon" not in e.lower()]
    check("no console errors", len(real_errors) == 0,
          "; ".join(real_errors[:4]))

    print()
    if failed:
        print(f"❌ {len(failed)} FAILED: {failed}")
        return 1
    print("✅ all smoke tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
