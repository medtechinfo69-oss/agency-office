# Site Builder inside Agency Office

Site Builder is part of the **same Agency Office application**, not a separate server or project to start. Run `./run.sh`, open `http://localhost:5173`, and choose **Site Builder** in the sidebar. The existing Office, Chat, Projects, marketing and settings pages remain available.

## Using the builder

1. The Northstar Insurance demo opens first. Click **+** beside Studio chat to start a new website.
2. Choose an installed Ollama model from the builder toolbar, or open its model settings to refresh, activate, install or remove a model. Starting Ollama and downloading a model are separate prerequisites. A model around 1.5B–3B parameters is a practical starting point on a 12 GB CPU-only computer.
3. Describe a website, then use the chat to request changes. Switch between Preview, Code, Files, Versions and Marketing. Code edits update the preview; use **Save** or Ctrl/Cmd+S to persist a version.
4. Export downloads a ZIP. **Open in Lovable** offers an editable handoff prompt with best-effort secret masking; inspect the prompt yourself before sharing it.

Provider API keys already configured under **Settings → Connections** are available server-side to the builder for OpenRouter, Groq and Gemini. They are never returned in its provider settings response. Builder model/provider selection is separate from the Agency Office model selection; APInex remains in the pre-existing Agency Office settings but is not used by the builder. Free-tier limits and cloud-provider billing terms are controlled by the provider.

## Data and integration

- The existing agency data remains in `backend/data/agency.db`; website projects, files, snapshots and builder chat are in `backend/data/siteforge.db`. Both belong to this one application, but **website projects and agency projects are not automatically linked**. The two chat histories, task engines and model selections are also distinct. Back up both databases and their SQLite WAL files together, preferably while the app is stopped.
- Builder code lives under `frontend/src/sitebuilder/`, `backend/app/sitebuilder.py` and `prompts/sitebuilder/`. Its API is served by the existing backend under `/api/sitebuilder`. No separate SiteForge server or installation is needed.
- The builder follows the Agency Office light/dark theme. Leaving the page keeps its current unsaved editor state and running request in memory, but explicit Save is still required for persistence.

## Limitations and safety

The builder remains a **prototype**, not the full production product requested in the original brief. It makes one model-generated content plan and renders a fixed HTML/CSS/JS template; it does not implement section-by-section generated code or true multi-agent orchestration. Its team strip is a visual roster. Static checks do not constitute full accessibility, contrast, responsiveness or link validation. Review generated copy, code and the site manually before publishing.

Marketing in the builder is text-only; image generation, ad mockups, Meta publishing and a 30-day calendar guarantee are not implemented there. Other missing features include Monaco, element selection, autosave, undo/redo, screenshots, multi-page generation, per-task model routing, rate-limit backoff and reliable cloud failover. The existing Agency Office marketing features are separate and remain available.

The preview is an iframe with `sandbox="allow-scripts"` and restrictive CSP; external resources and network calls are blocked there. Exported files do not inherit this preview CSP. File validation is not a complete JavaScript sanitizer, so inspect generated and manually edited files before opening or publishing them. Secret detection in Lovable prompts is best-effort only. Do not send private information or credentials to Lovable.

The app has no authentication or multi-user isolation and is intended for a trusted local environment. Do not expose it to the internet. Initial dependency installation and model downloads need internet; the installed local builder can operate offline with Ollama. The Office and builder currently use separate generation queues, so concurrent activity can still overload a weak CPU.

## Verification

```bash
backend/.venv/bin/python -m pytest backend/tests -q
node --test frontend/src/sitebuilder/handoff.test.mjs
cd frontend && npm run build
```

The integrated builder was also checked with an actual Ollama generation and ZIP export. This does not verify every provider or every output against the complete original acceptance checklist.
