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

**Paths are relative to the skill directory**, not to your project: `bin/new-site.py` means the script in the
skill (installed path `.claude/skills/djangocms-agent/bin/new-site.py`, or `~/.claude/skills/...`). The script
derives a **lowercase slug** from `--name` before it does anything (`NetYetiSite` becomes `netyetisite`; spaces
and punctuation become hyphens, e.g. `Acme Garden Club` becomes `acme-garden-club`) and uses it for the
directory, the OpsKit manifest name and (with underscores) the Python package. The dry run prints
`slug=... package=...`; check it, because the directory and package cannot be renamed by the script later.

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
| `--no-docker` | Omit the container files (Dockerfile, both compose files, `docker/*.sh`, `.dockerignore`, `bin/docker-*.sh`, `bin/dev-*.sh`, `bin/pin-images.sh`, `bin/pin_images.py`) and the Docker sections of README/AGENTS.md/CONTRIBUTING.md. Included by default. Settings, `/health/`, `requirements*.txt`, `bin/release.sh`, `CHANGELOG.md` and the map/video templates stay either way, and the site still passes its own tests and `bin/verify.sh` (container-file tests skip themselves) |
| `--dry-run` | Print the file plan, touch nothing |
| `--require-playwright` | Exit 2 before creating anything when Playwright or chromium is not ready (default: print a notice and continue) |
| `--yes` | Skip the confirmation asked after interactive prompts (each prompt re-asks until the answer is valid) |

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
- **Docker + PostgreSQL (default; `--no-docker` omits the files):**
  - `Dockerfile` with stages `base`, `dev` and `production` (the last, so a plain `docker build` makes the
    production image: gunicorn, non-root uid 1000, **no debug toolbar**); the base image is pinned by digest.
  - `docker-compose.yml` (`db` = postgres:16-alpine pinned by digest with no published port, `app` = the production
    image `${APP_IMAGE:-<project>}:${APP_VERSION:-latest}`, named volumes, healthchecks, `CREATE_VERSIONS`,
    `DJANGO_CACHE`, HSTS/SSL-redirect pass-through) and `docker/entrypoint.sh` (wait for DB, migrate,
    `createcachetable`, collectstatic, optional `CREATE_VERSIONS=1` repair, optional `SEED_ON_START=1` that runs
    `manage.py seed --first-run-only` so a restart never refills placeholders editors emptied,
    `gunicorn --no-control-socket`).
  - `bin/docker-env.sh` (generates both secrets first with python3 or an openssl fallback, writes nothing on
    failure, temp file then `mv`, mode 600, never overwrites), `bin/docker-up.sh`, `bin/docker-down.sh` (keeps
    volumes unless `--volumes`), `bin/docker-backup.sh` and `bin/docker-restore.sh` (`db.sql` + `media.tar.gz`; backup
    refuses an existing directory, restore refuses a non-empty database and only runs `down -v` with `--wipe`,
    and starts only `db`, restores with `ON_ERROR_STOP=1`, then starts the app).
  - **Dev stack:** standalone `docker-compose.dev.yml` (project `<project>-dev`, default `127.0.0.1:8880` via
    `DEV_PORT`, source bind-mounted, runserver autoreload, PostgreSQL, its own `dev_` volumes, debug toolbar), `docker/dev-entrypoint.sh`,
    `bin/dev-up.sh`, `bin/dev-down.sh` (never `-v` unless `--volumes`).
  - **Pins and releases:** `bin/pin-images.sh` (`--check`, `--dry-run`, write mode needs a clean git tree; registry HTTP API only,
    no Docker daemon) over `bin/pin_images.py`; `bin/release.sh vX.Y.Z` (semver, clean tree, on `main` unless
    `--force-branch`, newer than the latest tag; refreshes pins, runs check/migrations/tests, writes `VERSION`
    and moves `CHANGELOG.md` `[Unreleased]`, commits and tags; PRINTS the push commands, never pushes; `--dry-run`).
    The generated CONTRIBUTING.md and AGENTS.md state that pins are refreshed with each `vX.Y.Z` release.
  - The settings themselves are Docker-ready in every site: DB chosen by `DB_ENGINE` (unset = SQLite, so
    `verify.sh` and `runserver` are unchanged), shared DB cache with PostgreSQL, WhiteNoise, `/health/`,
    `DJANGO_SERVE_MEDIA`, CSRF/proxy env, Secure cookies behind a proxy, loopback always in `ALLOWED_HOSTS`.
  - **Default ports:** production `127.0.0.1:${APP_PORT:-8889}`, dev `127.0.0.1:${DEV_PORT:-8880}`. Add `-p <name>`
    to run a second copy (`bin/docker-up.sh -p other`; the same `-p` goes to `bin/docker-down.sh`). **CSRF origin note:**
    admin login fails with a 403 unless the browsed origin is trusted. The compose default follows
    `APP_PORT`/`DEV_PORT` for `localhost` and `127.0.0.1`; for any other host name or a TLS proxy set
    `DJANGO_CSRF_TRUSTED_ORIGINS` (scheme and port) and `DJANGO_ALLOWED_HOSTS`, and `DJANGO_BEHIND_PROXY=1` when the
    proxy sends `X-Forwarded-Proto` (never together with `APP_BIND=0.0.0.0` unless only the proxy reaches the port).
    Create the admin user inside the stack: `docker compose exec app python manage.py createsuperuser`. The
    scaffolder never runs Docker; the Docker run is a separate step the user (or you) starts.
- **Login throttling (every site, Docker or not):** django-axes 8.3.1 (database handler, shared by all gunicorn workers):
  5 failed logins lock username + IP for 60 minutes (`DJANGO_LOGIN_FAILURE_LIMIT`, `DJANGO_LOGIN_COOLOFF_MINUTES`,
  `DJANGO_LOGIN_LOCKOUT_BY`; limit 0 = off), friendly 429 page, unlock with `manage.py axes_reset`. `X-Forwarded-For` is
  trusted only with `DJANGO_BEHIND_PROXY=1` (`DJANGO_PROXY_COUNT` hops from the right). `bin/verify.sh` does one
  successful login (and the wrong-password check one failure), well under the limit; generated tests use `force_login`.
  Why axes and what was rejected: `references/plugins.md`.
- **Theme toggle:** header button, stored in `localStorage` (`theme`), OS default otherwise; see `references/templates-and-theme.md`.
- **Prod/dev packages:** `requirements.txt` is production only; `requirements-dev.txt` is `-r requirements.txt` plus
  `django-debug-toolbar`. `docutils` stays in production because `/admin/docs/` is enabled. The scaffolder's venv
  installs `requirements-dev.txt`.
- **Other generic hardening in every site:** CMS caches off under DEBUG (`DJANGO_CMS_CACHE=1` keeps them on), filer
  private storage inside `MEDIA_ROOT` (not served under `/media/`), Google Map plugins hidden from editors without
  `GOOGLE_MAPS_API_KEY` plus a no-script-error map template and `googlemap-guard.js`, a video template with a text
  link, a `<button>` dropdown toggle in the navbar, `seeding.py` that never edits published content in place.
- `CHANGELOG.md` (Keep a Changelog, `[Unreleased]` section for `bin/release.sh`).
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
The generated README documents the `treebeard.E001` warning (upstream, harmless) once. `VERIFY_ADMIN_PASSWORD` additionally logs in to `/admin/` and ASSERTS the login (if the login form is still showing afterwards the step fails and so does `VERIFY RESULT`). `PLAYWRIGHT_PYTHON` points at
a Python that has Playwright when the project venv does not. Final line: `VERIFY RESULT: PASS`
(exit 0), `FAIL` (1), or `INCOMPLETE` (3, visual step skipped).

Before and after any later change that affects rendering, take screenshots again and look at them.
