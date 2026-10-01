# Creating a new DjangoCMS site

`bin/new-site.py` builds the complete default site deterministically. Do not assemble a site by hand
or from memory.

## The workflow an agent follows

1. **Ask the human** for the site **name** and its general **purpose** (one or two sentences). Never
   guess or invent either; the script exits 2 if they are missing and stdin is not a terminal. Optional
   questions: display name (`--site-name`), license (default MIT), author for the copyright line, where
   the folder goes (`--parent-dir`).
2. **Check Playwright before scaffolding.** `verify.sh` can only do its visual step with it, and finding
   out afterwards wastes a run. `bin/new-site.py` runs this preflight at startup (before creating
   anything): it checks that `playwright` is importable with `PLAYWRIGHT_PYTHON` (else `python3`) and that
   chromium is installed, and otherwise prints a non-fatal NOTICE with the setup. Do it once in a scratch
   venv, never system Python:

       python3 -m venv /tmp/pw-venv && /tmp/pw-venv/bin/pip install playwright && /tmp/pw-venv/bin/playwright install chromium
       export PLAYWRIGHT_PYTHON=/tmp/pw-venv/bin/python

   Pass `--require-playwright` to make a missing setup fatal (exit 2, nothing created).
3. **Run the scaffolder** (below). Show the user the dry run first if the location is unclear.
4. **Run the generated `bin/verify.sh`** and **look at the screenshots** it writes to `verify-shots/`
   (desktop and mobile for `/`, `/about/`, `/style-and-capabilities/`). Open the PNGs with your image
   viewer; if you cannot view images, say so and rely on the printed `RESULT:` lines only.
   It prints, per step, what it covers (see "bin/verify.sh" below); relay what the visual step does
   not check.
5. **Report honestly**: what ran and passed, what did not run (for example Playwright missing gives
   `VERIFY RESULT: INCOMPLETE`, which is not a pass), the URL and port, and the admin login. Only then tell
   the user to look.

### Which URL and credentials to report

- Pick the first free port >= 8000 (check with `ss -ltn`; the scaffolder prints a suggestion that is only
  a guess), print the exact run command and report that URL:
  `DJANGO_DEBUG=1 DJANGO_SECRET_KEY=dev venv/bin/python manage.py runserver <port>` then
  `http://localhost:<port>/` (admin at `/admin/`).
- Report the `Admin login:  admin / <password>` line exactly as the scaffolder printed it. It is shown
  once, stored nowhere; never write the password to a file (a reset is `manage.py changepassword admin`).
- Link-mode installs: `bin/`, `assets/`, `references/` and `scripts/` under the installed skill directory
  are symlinks into the repo clone, so the paths resolve and `readlink -f` shows the real source.

## Running it

From a repo checkout: `python3 bin/new-site.py ...`. From an installed skill the script is
`<skills dir>/djangocms-agent/bin/new-site.py` (for example `~/.claude/skills/djangocms-agent/bin/new-site.py`
or `<project>/.claude/skills/djangocms-agent/bin/new-site.py`). `bin/` is exposed next to `assets/`,
`references/` and `scripts/` in both link and copy installs; the script finds its assets relative to itself.

```bash
python3 bin/new-site.py --name "Acme Garden Club" \
    --purpose "Member news, events and plot sign-ups for the Acme garden club" \
    --parent-dir ~/Projects --yes
```

| Flag | Meaning |
|---|---|
| `--name` | Human site name. Directory = lowercase hyphenated slug, Python package = slug with underscores. Must start with a letter, no path separators or `..`, not a reserved/shadowing module name |
| `--purpose` | Purpose of the site; written to README, AGENTS.md, CLAUDE.md and the OpsKit manifest |
| `--site-name` | Display name in navbar/title/footer (default: derived from `--name`) |
| `--parent-dir` | Folder to create the project folder in (default: cwd); must exist |
| `--license` | `MIT` (default), `ISC`, `BSD-3-Clause`, `Unlicense` |
| `--author` | Copyright holder (default: git `user.name`, else "The <site> contributors") |
| `--no-venv` / `--skip-install` | Only write files and `git init`: no venv, pip, migrate, seed |
| `--no-opskit` | Do not write `.opskit/pack.yml` |
| `--dry-run` | Print the file plan, touch nothing |
| `--require-playwright` | Exit 2 before creating anything when Playwright or chromium is not ready (default: print a notice and continue) |
| `--yes` | Skip the confirmation asked after interactive prompts |

Exit codes: **0** ok, **1** a build step failed (partial project left in place, step named), **2** usage
or validation error (missing name/purpose non-interactively, bad name, unsupported license, target exists
and is not empty, or `--require-playwright` with Playwright not ready). It never overwrites a file and refuses a non-empty target.

## What it produces

- The `assets/default-site/` site with `__PROJECT_NAME__`/`__SITE_NAME__` substituted in contents and
  paths, plus `wsgi.py`, `asgi.py`, `__init__.py` for the project package, `.gitignore`, `.env.example`.
- FOSS files from `assets/foss/`: `LICENSE`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `.github/` issue and PR templates, `AGENTS.md` plus a thin `CLAUDE.md` (imports AGENTS.md) that record
  the site's purpose, and a `README.md`. Content follows the `foss-init` skill's governance module.
- `.opskit/pack.yml` (OpsKit member manifest, contract 1, `data_classification: internal`,
  `sync: symlink`; adjust when the site gets a remote). It is a file only: the scaffolder never runs any
  `opskit` command. Do not run `opskit member sync-mount` / `opskit init <path>` to "finish" the
  integration; they have a known prune bug that deletes native agents and skills.
- `scripts/visual_check.py` (copy) and `bin/verify.sh`.
- Unless `--no-venv`: `venv/`, installed pinned requirements, migrated SQLite DB, superuser `admin` with a
  random password printed once at the end (never written to disk or git), `seed_pages` + `seed_site`
  (landing, About, Style & Capabilities, all published), and an initial git commit without any trailer
  (neutral identity `site-scaffold` only when git has no user configured). `create_versions` is not
  needed: seeding publishes through versioning on a fresh database.

## bin/verify.sh

`check`; `makemigrations --check` for the project's own apps (`OWN_APPS` at the top of the script; the
installed `djangocms_bootstrap5.contrib.*` drift is upstream and excluded); the tests; seed idempotency
(page/content counts unchanged after re-seeding); then Playwright `visual_check.py` on key URLs, desktop
and mobile, against a temporary dev server (first free port from 8010, or `VERIFY_PORT`; always stopped
on exit) started with `DJANGO_DEBUG_TOOLBAR=0`. Each step prints what it covers. The visual step asserts:
HTTP status below 400, no console errors, no failed same-origin requests, not a 404 or Django error page,
non-empty body text, the site name present, and no horizontal overflow (`scrollWidth > clientWidth`). It does
not judge layout, colour or contrast, images that return 200 but look wrong, JavaScript behaviour, or the
logged-in CMS toolbar (only `/admin/` is loaded, when `VERIFY_ADMIN_PASSWORD` is set): look at the PNGs.

The green tab on the right edge with `DJANGO_DEBUG=1` is the django-debug-toolbar handle, not the CMS toolbar;
it exists only when DEBUG is on and `DJANGO_DEBUG_TOOLBAR=0` removes it (app, middleware and url together).
The generated README documents the `treebeard.E001` warning (upstream, harmless) once. `VERIFY_ADMIN_PASSWORD` additionally checks `/admin/` logged in. `PLAYWRIGHT_PYTHON` points at
a Python that has Playwright when the project venv does not. Final line: `VERIFY RESULT: PASS`
(exit 0), `FAIL` (1), or `INCOMPLETE` (3, visual step skipped).

Before and after any later change that affects rendering, take screenshots again and look at them.
