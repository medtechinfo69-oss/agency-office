"""E2E verification: first-open → New Project modal; Settings → Providers →
key auto-validated + free-model dropdowns populated automatically."""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("[PASS] " if ok else "[FAIL] ") + name + (f" — {extra}" if extra else ""))


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1440, "height": 860})
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    # 1. empty office → New Project modal auto-opens (no demo project)
    modal_open = page.locator(".modal textarea").count() >= 1
    check("first open auto-shows New Project modal", modal_open)

    # 2. close modal → office visible, no seeded demo project in picker
    if modal_open:
        page.locator(".modal .ap-close, .modal .btn.ghost").first.click()
        page.wait_for_timeout(600)
    page.locator(".sidebar").get_by_text("Settings", exact=False).first.click()
    page.wait_for_timeout(1500)

    # 3. Providers tab is the default
    tab_active = page.locator(".settings-tabs button.active").inner_text()
    check("Providers tab is default", "Providers" in tab_active, tab_active)

    # 4. wait for the automatic key check on OpenRouter (stored key)
    status = page.locator(".provider-card").first.locator(".p-status")
    page.wait_for_function(
        """() => {
            const s = document.querySelector('.provider-card .p-status');
            return s && (s.textContent.includes('key valid') || s.textContent.includes('✗'));
        }""", timeout=45000)
    txt = status.first.inner_text()
    check("stored key auto-validated", "key valid" in txt, txt)

    # 5. model dropdown has multiple free options
    opts = page.locator(".provider-card").first.locator("select.p-select").first.locator("option").count()
    check("free-model dropdown populated", opts >= 5, f"{opts} options")

    # 6. image dropdown auto-set to pollinations-free
    img_val = page.locator(".provider-card").first.locator("select.img").input_value()
    check("image model auto-selected", img_val == "pollinations-free", img_val)

    # 7. active model auto-picked from free list (endswith :free)
    model_val = page.locator(".provider-card").first.locator("select.p-select").first.input_value()
    check("model auto-selected from free list", model_val.endswith(":free"), model_val)

    # 8. demo controls are gone
    demo_gone = page.locator("text=Demo mode").count() == 0
    check("demo mode control removed", demo_gone)

    # 9. token never exposed
    tok = page.content()
    check("token not in DOM", "sk-or-v1-" not in tok)

    if screenshot := os.environ.get("VERIFY_SCREENSHOT"):
        page.screenshot(path=screenshot)
        print(f"saved → {screenshot}")
    b.close()

failed = [n for n, ok in results if not ok]
if failed:
    print(f"\n❌ {len(failed)} FAILED: {failed}")
    sys.exit(1)
print(f"\n✅ all {len(results)} checks passed")
