# LATZ frontend

How the redesigned frontend is put together, what still needs a real asset, and what to know before changing it.

## Run it

```
cd frontend
npm install
npm run dev      # http://127.0.0.1:5173
npm run lint
npm run build
```

The backend address defaults to `http://127.0.0.1:8000`, the address the app has always used. To point at another backend, set `VITE_API_URL` in `frontend/.env.local`.

## Structure

```
src/
  App.tsx                     Session gate: landing → sign in → onboarding → workspace
  app/layouts/                Workspace shell: sidebar, header, command bar, page transitions
  features/
    landing/                  Public landing page
    auth/  onboarding/        Sign in, registration, first-run setup
    chat/                     LATZ Chat (streaming, history, memory prompts)
    workspace/                Mission Control, engineering modes, projects, Experiments Lab
  shared/
    api/client.ts             Backend address and token storage (one place)
    api/useBackendStatus.ts   Health check behind the header's Connected / Offline status
    brand/                    WolfHead and Wordmark
    components/               CommandBar, EngineeringCompass
    notifications/            LATZ notifications (the wolf reacts to success and failure)
    theme/theme.ts            Dark / light theme store
    markdown/                 Markdown renderer, table repair, syntax highlighter
    ui/                       Button, Modal, Notice, States (Menu, PageHeader, ConfirmDialog are ready for Milestone 2)
    styles/                   tokens.css, ui.css, globals.css
```

Navigation uses React Router (see "Routes" below). `app/session/` holds who is signed in, and `app/workflow.ts` carries a first message from a mode, a project or the command bar into chat.

## Routes

| Address | Screen |
|---|---|
| `/` | Landing (signed-in users go to Mission Control) |
| `/login`, `/register` | Sign in and registration |
| `/onboarding` | First-run setup |
| `/mission-control` | Mission Control |
| `/chat`, `/chat/:id`, `/chat?project=:id` | Chat: latest conversation, a named one, or one project's conversations |
| `/projects`, `/projects/:id` | Project list and project details |
| `/goals`, `/memories` | Goals and Memories |
| `/experiments` | Experiments Lab |
| `/profile`, `/settings` | My Profile and Account Settings |
| `/forge`, `/learn`, `/research`, `/explore`, `/solve` | Engineering modes |
| anything else | Not-found page |

- Workspace addresses need a session. A signed-out visitor is sent to `/login` and returned to the page they asked for after signing in.
- `/profile` and `/settings` are the account pages (Milestone 2A).
- `/memories` is not registered yet; they arrive later in Milestone 2 and show the not-found page until then.
- Every screen is a separate chunk, loaded when first opened.
- Hosting: the server must answer unknown paths with `index.html` (single-page fallback), or a refresh on `/chat/12` returns 404. `npm run dev` and `npm run preview` already do this. On Nginx: `try_files $uri /index.html;`.

## Design system

- `tokens.css` holds every colour, type size, radius and spacing value. Tokens are scoped to `[data-theme]`, so a subtree can stay dark (the sidebar and the landing page do) while the rest follows the user's choice.
- `ui.css` holds the shared primitives: `.btn`, `.icon-btn`, `.input`, `.field`, `.panel`, `.status`, `.tag`, `.notice`, `.empty`, `.modal`, `.toast`, `.markdown`.
- Type: Syncopate for display text (the `.display` and `.label` classes), Sora for body, JetBrains Mono for code. They load from Google Fonts in `index.html`. For offline or self-hosted use, replace that link with local `@font-face` rules; the token names stay the same.
- Theme: `setTheme` / `toggleTheme` / `useTheme` in `shared/theme/theme.ts`. The choice is saved in `localStorage` under `latz-theme` and applied before first paint by the inline script in `index.html`. It is stored per browser; the backend has no preference endpoint.
- Motion honours the operating system's reduced-motion setting (`MotionConfig reducedMotion="user"` plus a CSS guard).

## The wolf

`shared/brand/WolfHead.tsx` is the one wolf used everywhere: landing hero, sidebar wordmark, chat avatar, loading screens, notifications, favicon.

It takes a `mood`:

| Mood | Look | Where it is used |
|---|---|---|
| `idle` | steady blue eyes | default |
| `thinking` | eyes and rim light pulse | chat while streaming, loading screens, a running experiment |
| `success` | green flare, once | project created, experiment finished, saved notifications |
| `error` | amber eyes | failed chat reply, sign-in error, error notifications |

### Assets still needed

The current head is a faceted vector drawing made in code. It stands in for the final artwork.

1. **3D wolf-head render.** Front-facing, metallic navy and silver, electric-blue glowing eyes, blue rim light, transparent background. Square, at least 1024 × 1024, PNG or WebP, plus a 512 px version. Ideally four variants matching the moods above (or one neutral render and separate eye-glow layers). To use it, render an `<img>` inside `WolfHead` and keep the same props; nothing else in the app changes.
2. **Full-body wolf character.** Not present. The brief asks for it to appear only in context while working, never on the landing page. Today those moments (task finished, error, thinking) are played by the head. When the character exists, `NotificationsProvider` is the place to show it.

## Behaviour changes made during the redesign

- The fixed bottom command input, which had no behaviour, is now a working command bar: open it from the header or with Ctrl/Cmd + K to jump between screens, switch theme, sign out, or send a typed question to chat.
- The header's connection status now reflects a real call to `GET /health/` instead of a fixed "Connected" label.
- Mission Control reads projects (`GET /projects`) and conversations (`GET /conversations`) in addition to `GET /users/context`. All three endpoints already existed.
- Deleting a project asks for confirmation in an in-app dialog instead of the browser's `confirm`.
- Chat: when the first message of a brand-new conversation was sent, the message disappeared from view until reload. It now stays.
- Projects: a project created from the Projects screen appears in the list without leaving the screen.
- Experiment output renders as Markdown.

No backend file and no API contract was changed.

## Known limits

- `src/shared/components/TopBar.*` and `src/features/workspace/Home.*` are not imported anywhere. They were left in place untouched.
- `package-lock.json` is out of sync with `package.json` (`npm ci` fails on `@emnapi/*`). It was like this before the redesign and was not modified; `npm install` regenerates it.

## Phase 2, Milestone 1: chat rendering and routing

No backend file changed in this milestone.

### Chat rendering

- Tables: models put fenced code and line breaks inside table cells, which Markdown tables cannot hold. `shared/markdown/normalize.ts` repairs the three shapes seen (literal `\n`, `<br>` tags, real newlines that split the row) before parsing, so the cell shows a small code block with its lines intact. The Phase 1 renderer turned every `<br>` into a newline, which broke table rows; that is gone.
- Tables scroll sideways inside their own frame, prose cells wrap, and no column is narrower than 12 characters.
- Syntax highlighting comes from `shared/markdown/highlight.ts`, a small tokenizer written for this app. It adds no dependency. It colours comments, strings, numbers, keywords, variables and call names; it is not a full parser.
- Images whose address the sanitiser rejects (`data:`, `javascript:`) show their description instead of a broken image.
- The Markdown renderer is its own chunk (172 kB), loaded only by chat and Experiments.

### Chat behaviour

- Stop button while a reply streams. The partial text stays on screen, marked as stopped. The backend saves a reply only when the stream finishes, so a stopped reply is not in the saved history; the screen says so.
- Incomplete replies: the backend ends every stream with a status marker (`shared/api/streamEnd.ts` parses and strips it). Only `stop` counts as finished. A reply cut off by the model's output limit, a provider error, or a connection that closed early keeps its partial text, shows an "Incomplete reply" notice with the reason, and is never shown as complete. Experiments shows the same as an "Incomplete" status and notice with no success toast. See `docs/BACKEND_CHANGES.md`.
- Retry after a failed or stopped reply, and a scroll-to-latest button when scrolled up.
- Conversation search and pinning. Pins are stored in this browser (`latz-pinned-conversations`); the backend has no pin field.
- A workflow from a mode, a project or the command bar now starts its own conversation, filed under the mode's category. Before, it was appended to whichever conversation was most recent.
- Reloading chat never resends a workflow's first message.
- Clicking a project in Mission Control opens that project's conversations. Before, it sent an automatic "let's continue" message each time.

### Other

- One shared cache (`shared/api/resources.ts`) serves projects, conversations and user context to Mission Control and chat, so moving between screens does not refetch within 20 seconds.
- The profile is fetched once per session (it was fetched by both the app and the layout).
- Each page has exactly one `h1`, and the browser tab title follows the page.
- Largest JavaScript chunk: 401 kB (130 kB gzipped), down from 595 kB.

### Tested

`npm run lint` and `npm run build` pass. A 114-check browser pass against the real backend passed (SQLite, model call stubbed): guest and protected redirects, onboarding gate, every sidebar route, refresh, Back and Forward, direct links, the full Phase 1 flow, the table repair in dark, light and mobile, stop, retry, search, pin, and overflow at 390, 820, 1280, 1440 and 1920 px.

Not tested: real model output (no API key here), and the backend pytest suite (no backend change).

## Phase 2, Milestone 2A: profile and account settings

No backend file changed in this milestone.

### What was added

- Account menu (`features/account/AccountMenu.tsx`): the header avatar and the sidebar identity row open the same menu with My Profile, Account Settings, Appearance and Sign Out. The sidebar's separate sign-out icon is replaced by this menu.
- `/profile` (`ProfilePage.tsx`): display name, username, email, bio, time zone and roles from the signed-in account. Edit profile switches the panel to a form; Save changes and Cancel act on the whole form, roles included.
- `/settings` (`SettingsPage.tsx`): theme, time zone, account information and sign-out.
- The command bar lists My Profile and Account Settings.
- The role suggestions moved from onboarding to `shared/config/lifeRoles.ts`, so onboarding and the profile share one list.

### Endpoints used (all existing)

| Request | Used for |
|---|---|
| `GET /users/me` | username and email (read-only) |
| `GET /users/profile` | display name, bio, time zone |
| `PUT /users/profile` | saving the profile; saving the time zone alone from settings |
| `GET /users/roles` | role list |
| `POST /users/roles` | each role added in an edit |
| `DELETE /users/roles/{id}` | each role removed in an edit |

All of them go through `apiFetch`, which attaches the session token and signs the user out on a 401.

### Behaviour worth knowing

- Role changes are held in the form and sent only on Save, so Cancel discards them. Save sends the profile first, then deletions, then additions. If a role request fails after the profile was saved, the page reloads the roles from the server and says which part was not saved.
- `PUT /users/profile` ignores fields sent as null, so an emptied bio or time zone is sent as an empty string. The page treats an empty string as "not set".
- Limits enforced in the form: display name and role 100 characters (the column sizes), bio 2000 (a frontend choice; the column is unbounded).
- The time zone list comes from the browser (`Intl.supportedValuesOf`). The browser may name a zone differently from the saved value (Asia/Calcutta and Asia/Kolkata are the same zone).
- Theme is stored in the browser, as before. The backend has no preference field.

### Tested

`npm run lint` and `npm run build` pass. A 67-check browser pass against the real backend passed: both menus, keyboard use of the menu, profile loading, read-only username and email, validation, Cancel, a forced API failure, role add and delete, the exact requests sent and their tokens, the saved values read back from the API, persistence after refresh, theme switching, time zone, the three sign-out paths, direct and protected navigation, an expired token on save, and overflow at 390, 820, 1280, 1440 and 1920 px. The 114-check Milestone 1 regression was rerun and passed.

Not tested: the backend pytest suite (no backend change).

## Phase 2, Milestone 2B.1: project details

### What was added
- `/projects/:projectId` (`features/workspace/ProjectDetailPage.tsx`, lazy chunk, own `ProjectDetail.css`): name, description, status, engineering mode, created/updated dates and technology stack, with edit (save/cancel, name required), delete (confirmed), and the project's conversations.
- Project cards on `/projects` link to it (title and "View details").
- Only fields the backend returns are shown. There are no files or activity sections because the backend has none.

### Endpoints used (all existing, no backend changes)
`GET /projects/{id}`, `PATCH /projects/{id}`, `DELETE /projects/{id}`, `GET /conversations?project_id=`.

### Behaviour worth knowing
- Invalid (`abc`, `-1`), missing and other users' project ids all show the same "Project not found" state; a non-numeric id sends no request.
- The backend skips `null` fields on update, so emptied fields are sent as `""`. The `/projects` list edit modal had the same bug (clearing a description did nothing) and now sends `""` too.
- A failed conversation request shows its own retry inside the page and does not hide the project.
- Conversations open at `/chat/:id?project=:projectId`; "Open project chat" goes to `/chat?project=:projectId`.

## Phase 2, Milestone 2B.2: goals

- `/goals` (`GoalsPage.tsx`, own chunk and CSS) with a "Goals" sidebar entry. Lists goals with title, description, category, priority, target date, created date and a status selector; create modal; confirmed delete; loading, empty and error states.
- Endpoints (existing, no backend changes): `GET/POST /users/goals`, `PATCH /users/goals/{id}/status?status=`, `DELETE /users/goals/{id}`.
- Status: the backend stores free text with no validation. The page offers `active`, `paused`, `completed` (Mission Control treats only `completed` specially) and keeps any other existing value selectable.
- Not offered, because the backend has no support: editing goal details, linking goals to projects, progress tracking.

## Final sprint (Stages 1 to 5)

### Memories (`/memories`)
`MemoriesPage.tsx`. Lists, creates and deletes (confirmed) memories with `GET/POST /memory` and `DELETE /memory/{id}`. Filter chips show a count per type (preference, fact, project) and are applied in the browser on the one list. There is no edit endpoint, so a memory is deleted and re-added.

### Conversation management
- Chat list rows have rename (dialog, validated) and delete (confirmed) next to pin. Deleting the open conversation moves to the next most recent one, or starts a fresh chat if it was the last. The buttons stay visible on touch screens, where there is no hover.
- Backend: `PATCH` and `DELETE /conversations/{id}`; see `docs/BACKEND_CHANGES.md` at the repository root.
- A history request that returns 404 (the conversation was deleted) now shows a clean start rather than logging an error.

### Workspace
- Projects: search, status filter and sort (recently updated, newest, name).
- Engineering mode pages list that mode's projects when there are any (matched on the project's engine); each links to its details. Nothing is shown when there are none.
- Mission Control: the four stat tiles are links; Open goals has View all. Stat details are now valid `dd` elements.
- Command bar: also finds projects and conversations once you type (up to six of each kind, never listed on an empty query); Goals and Memories are in the page list.
- Experiments: Stop button (keeps the partial output), Copy, and a "runs this session" list that reopens a run. This history is in the tab only; the backend has no experiment history endpoint.

### Wolf
`WolfHead` gained an `offline` mood (dim eyes, no motion), used by the sidebar mark when the backend health check fails, and a `depth` option for hero placements (landing, Mission Control): a metallic sheen plus pointer parallax on four layers (halo, head, rim, eyes). Parallax is off under reduced motion and on touch screens, and the static mark is what renders then. Still pure SVG and CSS, no new dependency.

### Accessibility and robustness
- `ErrorBoundary` around each page (keeps the sidebar and navigation usable; resets when you change section) and around the whole app. A page chunk that fails to download shows it.
- Skip-to-content link; `main` is focusable.
- axe-core (WCAG 2 A/AA, serious and critical) found: three controls whose accessible name did not contain their visible text, light-theme contrast on muted text and the active/paused tags, and a `dl` holding a stray element. All fixed; the scan now reports none on ten pages in both themes.
- Modals focus their first field themselves; `autoFocus` on an input inside a modal made the modal remember the input as the element to return focus to, so Escape did not restore focus. Removed from the new dialogs.
