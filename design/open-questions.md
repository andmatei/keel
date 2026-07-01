# Open contract questions

A parking lot for design questions that haven't been resolved yet. Move
items into `design/decisions/` (with rationale) once a call is made, or
delete them if they become moot. Date-stamp each entry so we can track
how long things have been open.

---

## 2026-05-05 — TOML contract questions raised after Plans 6/7 + first plugin

Surfaced during the post-publish review of `keel-cli` 0.0.2 + `keel-jira`
0.0.1. Pruned 2026-05-06 after Plan 8 shipped — items 3 and 6 were
resolved by T9.2 (CONTRIBUTING now documents the `[extensions]` selector
pattern).

### High value, low cost

1. ~~**Schema versioning.**~~ → resolved. `keel migrate` removed; no
   `schema` field. Pydantic `extra="forbid"` + `0.0.x` alpha versioning
   covers breaking changes. See `decisions/2026-05-12-discontinue-migrate-and-schema-versioning.md`.

2. ~~**`ticket_id` is a single string.**~~ → resolved. Replaced with
   `tickets: dict[str, str] = {}` on both Milestone and Task. Keys are
   provider names, values are ticket IDs. Breaking change (alpha).

3. ~~**State-name convention across lifecycles.**~~ → resolved. Enforced
   via Pydantic validator: lowercase alphanumeric + hyphens, must start
   with a letter (e.g. `scoping`, `in-review`). Both single words and
   kebab-case are valid.

### Worth discussing

4. ~~**`Task.branch` assumes git.**~~ → resolved. Kept as optional
   metadata (`branch: str | None = None`). Non-code projects simply leave
   it null. No need to move to extensions during alpha.

5. ~~**`Milestone.fan_out` is unvalidated.**~~ → resolved. Removed the
   field entirely — sub-milestones already link back via `parent`, so
   `milestone done` now scans deliverables for matching parent links
   instead of relying on an explicit list. Breaking change (alpha).

6. ~~**`lifecycle = "default"` implicit default.**~~ → resolved. Implicit
   default is fine — the lock file (`lifecycle.lock.toml`) snapshots the
   resolved lifecycle at `keel new` time, so existing projects don't
   drift. No need to require an explicit pick during alpha.

### Defer

7. ~~**`description = ""` proliferation.**~~ → resolved. Changed
   Milestone.description and Task.description to `str | None = None`.
   Omitted from TOML when not set. Breaking change (alpha).

8. ~~**`created` is date-only.**~~ → resolved. Date-only is fine —
   projects don't need sub-day precision, and TOML native dates are
   cleaner than datetime strings. Revisit only if audit requirements
   surface.

---

## 2026-05-11 — Feature ideas surfaced during Plan 9

### ~~Tags for projects and deliverables~~ → resolved

Resolved into full spec: `specs/2026-05-11-tags-design.md`. Shipping as
Plan 10 (keel-cli 0.0.5).

---

(Add more sections below as new questions surface.)
