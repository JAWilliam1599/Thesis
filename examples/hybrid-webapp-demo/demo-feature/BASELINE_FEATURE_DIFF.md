# Baseline → Feature: What Changed to Add the "Like" Counter

| File | Layer | Baseline (before) | Feature (after) |
|------|-------|--------------------|-------------------|
| [`ansible/files/schema.sql`](demo-materials/feature/ansible/files/schema.sql) | Schema (on-prem) | `guestbook` table has no `likes` column. | Adds `ALTER TABLE guestbook ADD COLUMN IF NOT EXISTS likes INTEGER NOT NULL DEFAULT 0;` — idempotent, existing rows default to `0`. |
| [`ansible/site.yml`](demo-materials/feature/ansible/site.yml) | Provisioning (on-prem) | No task guarantees the `likes` column exists on hosts provisioned before the feature. | New task `Ensure the reactions (likes) column exists on the guestbook table` runs the same idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS likes ...` via `become_user: postgres`, so already-provisioned DBs gain the column on re-run. |
| [`cdk/app.py`](demo-materials/feature/cdk/app.py) | API Gateway (AWS) | `guestbook` resource only has `GET` and `POST` methods. | Adds a nested resource `guestbook/{id}/like` with a `POST` method — purely additive, so existing `GET`/`POST` on `guestbook` are untouched. |
| [`cdk/lambda/handler.py`](demo-materials/feature/cdk/lambda/handler.py) | Lambda logic | `_list_entries`/`_add_entry` select/return `id, name, message, created_at`; no route handles `/like`. | Queries now also select/return `likes`; new `_like_entry()` runs `UPDATE guestbook SET likes = likes + 1 ... RETURNING ...`; `handler()` routes any `resource` ending in `/like` with `POST` to it, validating a numeric `id` (400) and a missing entry (404). |
| [`frontend/app.js`](demo-materials/feature/frontend/app.js) | Frontend | Each entry renders `who`, `when`, `message` only. | Each entry also renders a `♥ <count>` `<button class="like">` that calls `likeEntry()`, which `POST`s to `/guestbook/{id}/like` and updates the button text from the response. |
| [`frontend/styles.css`](demo-materials/feature/frontend/styles.css) | Frontend styling | `.entries li` has no flex layout; no `.like` button styles. | `.entries li` becomes a column flex container; new `.entries button.like` (+ `:hover`, `:disabled`) styles render the pill-shaped like button. |

## Net effect

- **Baseline:** the guestbook lists and accepts entries, but there is no way
  to react to one — no DB column, no API route, no UI control.
- **Feature:** every entry has a persistent, on-prem-stored like counter that
  can be incremented from the UI via a new, additive API route.

## How it ships

Every change is additive (new column with `DEFAULT`, new API resource/method,
new Lambda branch, new UI element) — no existing schema, route, or resource is
modified or removed. `cdk deploy` therefore produces a changeset with
`UPDATE_COMPLETE` and no replacement, and the Ansible playbook re-applies
idempotently (`ADD COLUMN IF NOT EXISTS`, `GRANT` is naturally idempotent),
preserving the already-deployed VPC, CloudFront distribution, DB secret value,
and existing rows (which simply default to `likes = 0`). See
[`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for the full narrated walkthrough.
