# Backend gaps

Features the frontend brief asks for that the current backend cannot support. Nothing here is faked in the interface; each item is left out or shown as plain information until an endpoint exists.

## Account (found in Milestone 2A)

| Wanted | What is missing | What the interface does today |
|---|---|---|
| Change password | No endpoint | Not shown as a control. Settings says it is not available yet. |
| Change email or username | No endpoint; `GET /users/me` is read-only | Shown read-only |
| Delete account | No endpoint | Not shown as a control |
| Profile picture | No upload endpoint or image field | Avatar is the user's initial with the LATZ wolf badge |
| Interests | No field on the profile | Not shown |
| "Member since" | `GET /users/me` does not return `created_at` (the column exists) | Not shown |
| Theme saved to the account | No preference field | Saved in the browser |
| Edit a role's description or priority | Roles can only be added and deleted | A role is removed and re-added |
| Clear a profile field with null | `PUT /users/profile` skips null fields | The frontend sends an empty string |

## Conversations (found in Milestone 1)

| Wanted | What is missing | Status |
|---|---|---|
| Rename and delete a conversation | Was missing | Added (see `docs/BACKEND_CHANGES.md`): `PATCH` and `DELETE /conversations/{id}` |
| Pin a conversation | No field | Pins are stored in the browser |
| Keep a stopped reply | A reply is saved only when its stream finishes | The screen says a stopped reply is not saved |

## Goals, memories and experiments (found in the final sprint)

| Wanted | What is missing | What the interface does today |
|---|---|---|
| Edit a goal's details | No `PUT`/`PATCH` for goals other than status | Not offered; delete and re-create |
| Goal status list | Status is free text with no validation or list endpoint | Offers active, paused, completed |
| Link goals to projects | No `project_id` on goals | Not shown |
| Goal progress | No progress field | Not shown |
| Edit a memory | No update endpoint | Delete and re-add |
| Experiment history | Experiment runs are saved as ordinary chat rows with no experiment id, and there is no list endpoint for them | The Experiments page keeps this tab's runs only and says so |
| Sort or search on the server | List endpoints take no query or sort parameters | Search, filter and sort run in the browser |
