# Agency Office — UI/UX review and redesign

> Deployment follow-up: [DEPLOYMENT.md](DEPLOYMENT.md) documents the Vercel project, persistent backend setup and owner access gate added after this UI-only review. The preservation/testing notes below describe the original redesign scope, not the later hosting changes.

## 1. Audit before implementation

The review covered the application shell; Office, Site Builder, Chat, Workflows, Projects, Permissions, Logs, Skills, System health, Shop and Settings; and project creation, agent details, analytics and campaign preview dialogs. Backend/API code was inspected for context but not modified.

| Main issue | Usability impact | Resolution |
| --- | --- | --- |
| Eleven navigation destinations plus theme/language controls competed in a horizontally scrolling mobile bottom bar. | Hard to discover destinations and switch pages on a phone. | Sticky mobile header with an expanded two-column navigation menu; desktop sidebar retained. |
| Small text, tightly packed cards, irregular gaps and visually heavy task covers diluted hierarchy. | Important information was hard to scan. | Shared slate/indigo palette, clearer headings, stronger secondary-text contrast, quieter task covers and consistent 8/12/16/24/32 px spacing. |
| Small chips, tabs, icon buttons and inconsistent control styling. | Difficult touch interaction; unclear focus and selection. | Standard 44 px main controls; 36 px minimum segmented subcontrols; unified selected, hover, focus, disabled and pending states. |
| Dialogs did not consistently contain focus, support Escape or restore focus. | Keyboard users could leave the dialog or lose their place. | Shared dialog hook across project creation, preview, analytics, agent details and Site Builder settings/handoff/QA dialogs. |
| Analytics used placeholder-only fields, and provider fields lacked persistent labels. | Labels disappeared while editing; invalid metrics were easy to enter. | Persistent labels, required campaign name, non-negative numeric values and a 0–100 CTR range. |
| Header said “Live” while disconnected; illustrative settings looked functional. | Users could mistake configuration/demo UI for verified system state. | Explicit reconnecting state, real WebSocket diagnostics, unverified Ollama status and clear illustrative-role/user notices. |
| Request failures were sometimes silent or looked like empty results; saves could be repeated. | Users could not tell whether work had succeeded. | Startup error/retry banner, accessible notifications, action pending states, workflow retry, visible shop save failures and success messages. |
| Prompt deletion lacked confirmation; failed outfit saves changed undo history. | Accidental deletion or misleading recovery controls. | Explicit prompt-delete confirmation; outfit history updates only after successful persistence; history resets when changing agents. |
| Tables/toolbars/nested tabs needed small-screen containment; office controls escaped their scene card. | Horizontal page overflow and overlapping controls. | Scrollable table/tab containers, responsive grids and forms, wrapped action rows, and scene-local controls. |
| Blocked tasks were displayed under Done. | Stalled work appeared completed. | Blocked cards now display in In progress with their existing warning and risk filter. No task data/status is changed. |

## 2. What changed and why

### Shared visual system
- Cool neutral surfaces and an indigo primary accent, with coherent light/dark/system themes.
- System font stack: readable, offline-capable and no new external font requests.
- Shared spacing, border, radius, control-height and semantic color tokens.
- White-on-solid success/danger buttons retain readable contrast in dark mode instead of using bright status-text colors as their backgrounds.
- More generous card padding, clearer page headings, legible metadata and restrained hover feedback.
- Reduced-motion support and visible keyboard outlines.

### Navigation and workflows
- Compact mobile navigation with an explicit Menu button, expanded state, Escape dismissal and automatic closure after navigation.
- Skip-to-content link, accessible search names, keyboard-operable task/catalog cards and arrow-key navigation for shared tabs.
- Removed the redundant project selector from the Projects page header; the board toolbar retains project selection.
- Empty-office guidance provides a direct New project action after dismissing the initial creation dialog.
- Shared approval controls disable conflicting decisions while a request is pending. Office/Chat async tools show pending feedback and prevent repeat activation of the same action.
- Agent details are a clearly modal side drawer with a backdrop, close control and focus management.

### Forms, tables and feedback
- Analytics fields keep their labels while populated and use native constraint validation.
- Provider fields have visible labels without exposing stored keys.
- Calendar and analytics tables scroll within their containers. The permissions planning matrix retains all existing controls with clearer selection states.
- Notifications are announced to assistive technology and can be dismissed.
- Workflow errors have a retry action instead of being silently presented as “No workflows”.
- Shop save/undo/redo failures are visible, preserve the pending selection and do not advance history on failed persistence.
- Existing local-only permissions, illustrative users/roles and non-rendering catalog items remain available but are explicitly identified.

### Site Builder
- Its existing generation, editing, preview, models, versions, QA and handoff behavior is retained.
- Studio surfaces, typography, buttons, contrast, labeled model controls, modal behavior and mobile layout follow the same visual language as Agency Office.
- Styling targets the studio shell, not generated website content inside the preview iframe.

## 3. Scope and preservation

No backend files, API contracts, database schemas, orchestration rules, AI/provider routing, billing behavior, generated-site templates or application dependencies were changed. Existing features remain in place. Changes to async wrappers, validation, focus, confirmation and outfit-history handling are limited to usability and feedback. The Kanban change is display grouping only.

No real provider calls or destructive operations were used in browser regression testing. Browser tests intercept API requests with in-memory fixtures; they do not create/delete user projects or change credentials. Existing backend tests use their existing fixtures. The live preview runs the normal Vite frontend and local API.

## 4. Verification

Verified during this redesign:

- `npm run build --prefix frontend` — production build passed.
- `node --test frontend/src/sitebuilder/handoff.test.mjs` — **3 passed**.
- From `backend`: `.venv/bin/python -m pytest -q` — **39 passed**.
- New non-destructive browser suite: all **11 pages** at **1440, 768, 390 and 360 px**, plus settings subsections, with no document-level horizontal overflow.
- Browser interaction checks: task search, keyboard card activation, dialog focus containment, Escape dismissal, focus return, analytics labels/invalid numbers, shop save failure/history, workflow retry, prompt-delete accept/cancel and theme switching.
- No browser JavaScript page errors during those checks. A separate read-only navigation check also visited all 11 pages against the real local API without JavaScript errors.
- Optional axe-core scans: **zero reported WCAG A/AA rule violations on the default view of each of the 11 pages in both light and dark themes**, using fixture data. This is automated coverage, not a full accessibility certification or a claim about every modal/data combination.

### Reproduce the browser checks

Run the normal frontend dev server first. In an environment with Chromium and Playwright available:

```sh
# Optional test-only tools; not application dependencies.
cd frontend
npm install --no-save --package-lock=false playwright axe-core
npx playwright install chromium
cd ..
node frontend/tests/ui-review.cjs
UI_AXE=1 node frontend/tests/ui-review.cjs
```

The script also supports `UI_URL`, `CHROMIUM_PATH`, `CHROMIUM_ARGS` (a JSON array), `UI_SCREENSHOTS` and `UI_AXE_REPORT`. Screenshot/report output should be stored outside tracked source. Automated browser tests use mocked data, so real AI generation, external publishing, downloads and live provider credentials were not end-to-end retested. They still use their existing handlers and backend implementation.

## 5. Remaining limitations

- Permissions planning remains browser-local and does not enforce access. User/role panels remain illustrative; their Save button is now explicitly unavailable instead of implying persistence.
- Some catalog selections are stored but do not render in the office scene; they are labeled accordingly.
- Floor 1 and Gym remain unassigned/quiet views.
- Some interface strings remain English when another language is selected; this redesign is not a complete translation pass.
- Server CPU/disk telemetry and provider reachability cannot be inferred from selection/configuration; the UI now avoids implying otherwise.
- Automated scans do not replace testing with screen readers, physical touch devices, real production data and live provider integrations.

## 6. Complete updated source

`deliverables/agency-office-updated-source.zip` contains the **full contents of every modified/new source, test and documentation file**, at its repository-relative path, plus a SHA-256 manifest. It contains complete files, not patch snippets. Dependencies, build output, databases, credentials and screenshots are excluded. The same source changes are already applied directly in the working repository.
