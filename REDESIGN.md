# Agency Office UI redesign

> **Current UI/UX refresh (2026-11-26):** See [UI_UX_REVIEW.md](UI_UX_REVIEW.md) for the latest audit, implementation notes, complete-source delivery and verification. Historical implementation details below are retained for context.

For current hosting setup and security requirements, see [DEPLOYMENT.md](DEPLOYMENT.md).

## Design plan

- **Palette:** cool slate `#F5F7FB`, white surfaces and subtle borders; dark near-black navy `#0B0E14`; indigo `#4F46E5` for primary actions and selection. Semantic status colours distinguish working, waiting, thinking, researching, idle and failed states.
- **Typography and shape:** Inter-style system sans serif, monospace for compact technical metadata, tracked section labels, rounded bordered cards, and thin Lucide icons. Tokens and light/dark variants live in one theme file. The theme switch supports system, light and dark.
- **Layout:** persistent sidebar, header and clock, responsive page layouts and phone navigation. The Office combines a stats strip, isometric scene, floor selector, hierarchical roster and journal. Chat, task Kanban, workflows, skills, health, shop and settings have dedicated screens.
- **Artwork:** the isometric room and rounded robot characters are original inline SVG/React artwork; no reference-repository images are used. SVG scales to different resolutions without separate raster sprite sheets.

## Source files

The complete source code is in this project, at the following paths:

| Path | Purpose |
| --- | --- |
| `frontend/src/main.jsx` | React entry point and stylesheet imports |
| `frontend/src/App.jsx` | Application state, navigation, API/WebSocket wiring and shell |
| `frontend/src/api.js` | API client |
| `frontend/src/ws.js` | WebSocket client |
| `frontend/src/i18n.js` | Interface translations |
| `frontend/src/styles/theme.css` | Light/dark design tokens |
| `frontend/src/styles/app.css` | Layout, controls, page styling and responsive rules |
| `frontend/src/components/Sidebar.jsx` | Navigation, theme and language controls |
| `frontend/src/components/TopBar.jsx` | Page heading, connection status and clock |
| `frontend/src/components/ui.jsx` | Shared cards, status pills, KPIs, tabs and controls |
| `frontend/src/components/Characters.jsx` | Original vector robot characters |
| `frontend/src/components/IsometricOffice.jsx` | Original vector office, agents and camera controls |
| `frontend/src/components/AgentPanel.jsx` | Agent details |
| `frontend/src/components/NewProjectModal.jsx` | New project form |
| `frontend/src/components/SettingsScreen.jsx` | Provider, model and existing configuration tools |
| `frontend/src/components/PreviewScreen.jsx` | Campaign preview |
| `frontend/src/components/AnalyticsScreen.jsx` | Analytics panel |
| `frontend/src/pages/OfficePage.jsx` | Office dashboard and approvals |
| `frontend/src/pages/ChatPage.jsx` | Manager conversation and composer |
| `frontend/src/pages/ProjectsPage.jsx` | Project selector, task Kanban and filters |
| `frontend/src/pages/WorkflowsPage.jsx` | Scheduled workflow cards |
| `frontend/src/pages/PermissionsPage.jsx` | Browser-local permissions planning matrix |
| `frontend/src/pages/LogsPage.jsx` | Activity log |
| `frontend/src/pages/SkillsPage.jsx` | Skills catalog |
| `frontend/src/pages/SystemHealthPage.jsx` | Available health and browser-resource data |
| `frontend/src/pages/ShopPage.jsx` | Character and customization catalog |
| `frontend/src/pages/SettingsPage.jsx` | Settings sections and provider integration |
| `frontend/package.json`, `frontend/vite.config.js` | Frontend dependencies, build and proxy configuration |
| `backend/tests/smoke_ui.py`, `backend/tests/verify_auto.py` | Browser checks, updated for the new shell |

## Removed UI files

- `frontend/src/pixel/` — old procedural pixel sprites and tile-map implementation.
- `frontend/src/components/OfficeCanvas.jsx` — former pixel office.
- `frontend/src/components/LeftPanel.jsx`, `RightPanel.jsx`, `BottomBar.jsx` — replaced by the new shell and pages.

## Run

From the project directory, execute `./run.sh` (or double-click it where the desktop supports executing shell scripts). It builds the frontend and starts the API and web app. Open `http://localhost:5173`; API documentation is at `http://localhost:8000/docs`. Node/npm and Python are required; see `README.md` for setup and dependencies.

Configure a provider under **Settings → Connections → Providers**. Keys are submitted to and stored by the backend; the API does not return the stored key to the browser. Ollama can be configured and activated there without putting a key in `.env`.

## Historical verification and limitations (before the current refresh)

- The frontend production build succeeds and the offline backend suite passes 31 tests. The redesigned browser smoke suite passed 16/16 before the final health/label adjustments; a subsequent read-only navigation check visited all ten pages without JavaScript page errors. The full API sweep passed 55/55 before the redesign but was not rerun after it.
- Not all new visual controls are backed by server features: the permissions matrix is browser-local and **does not enforce permissions**; the users and roles shown in Settings are illustrative, not an authentication or authorization system. Shop choices are persisted to agent customization, but furniture, decoration and theme catalog entries do not change the office scene. Floor 1 and Gym are empty views. Some page content remains English when French is selected.
- Server CPU and disk telemetry are not provided by the API. Health displays available browser memory/storage measurements as such and reports unavailable metrics rather than fabricating system usage. Provider selection does not establish connectivity.
- During testing the SQLite database was briefly reset. The pre-reset main database was restored from `backend/data/agency.db.bak-redesign`; it contains four smoke-test projects. The most recent smoke-test project and any changes that existed only in the deleted SQLite WAL were not recovered. The backup is retained; inspect it before making further data changes.
