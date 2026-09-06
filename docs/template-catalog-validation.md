# GitHub template catalog validation

Local branch: `codex/github-template-catalog`, based on `dd58970`.
Worktree: `/mnt/c/Users/xtomm/Documents/GitHub/tbd-template-catalog`.
These checks were completed before delivery. No database mutation or real
GitHub repository creation was performed by the validation suite.

## Checks

From the worktree root:

- `PYTHONPATH=api /tmp/tbd-role-tests-venv/bin/python -m pytest api/tests -q`
  — 106 passed, 5 subtests passed; three upstream deprecation warnings.
- `PYTHONPATH=api /tmp/tbd-role-tests-venv/bin/python -m pytest api/tests/test_template_catalog.py -q`
  — 25 passed. Includes empty catalog database, visibility overrides, authentication,
  GitHub failures, cache backoff, source SHA propagation and a mocked full repository copy.
- `/tmp/tbd-role-tests-venv/bin/python -m ruff check api --select E9,F63,F7,F82`
  — passed (repository CI correctness gate).
- `/tmp/tbd-role-tests-venv/bin/python -m ruff check api/app/services/template_catalog.py api/tests/test_template_catalog.py api/app/schemas/template.py`
  — passed.
- `git diff --check` — passed.

From `web/`, using the existing local dependency installation through a temporary
symlink (removed after verification):

- `/tmp/node-v20.19.5-linux-x64/bin/node node_modules/typescript/bin/tsc --noEmit`
  — passed.
- `/tmp/node-v20.19.5-linux-x64/bin/node node_modules/next/dist/bin/next lint --file src/components/template-gallery.tsx --file src/lib/types.ts`
  — passed without warnings.
- `/tmp/node-v20.19.5-linux-x64/bin/node node_modules/next/dist/bin/next lint`
  — passed with two warnings in unchanged files: missing hook dependencies in
  `src/app/dashboard/[projectId]/deploys/[deployId]/page.tsx:67` and
  `src/app/page.tsx:2027`.

The full configured Ruff style check on the existing templates router still has
15 pre-existing findings (12 B008, one E501, two B904), down from 16 at baseline
because the import block was cleaned up. No rule suppression was added.

The actual `source_folders()` service was run against public GitHub, without a
source token: seven starters found in `xdkaine/tbd-dev` at `main`, tree
`007e59d4270593035b930cd2021b21ee09fca27a`.

Independent read-only review completed; cache request volume and revision
consistency findings were fixed and re-reviewed with no remaining material finding.

## Limits

Docker is unavailable in this WSL distribution (`docker info` reports missing
WSL integration), so container build/tests were not run. No production frontend
build or browser interaction/responsive check was run. Live Kubernetes,
PostgreSQL and end-to-end GitHub repository creation/deployment were not tested.
No database migration or seed operation is needed for this change, provided the
existing `templates` table schema is already installed. The live API and web
must be deployed before this change appears in the gallery.
