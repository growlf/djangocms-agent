---
name: djangocms-agent
description: 'DjangoCMS 5.x specialist. Use for: django-cms, cms pages, placeholders, cms plugins, cms templates, cms migrations, toolbar, apphooks, finding or adding packages (djangopackages, is there a package for, add a blog/forms/SEO/search/shop plugin).'
license: MIT
metadata:
  author: growlf
  version: "0.5.0"
  compatibility: claude-code, opencode, codex, cursor
  stack:
    python: "3.12|3.13"
    django: "5.2 LTS"
    django-cms: "5.1.3"
---

# DjangoCMS Agent

DjangoCMS specialist for django-cms 5.x. Handles page trees, placeholders, templates,
content plugins, admin customization, middleware, and migrations.

**Credit:** Built on patterns from [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) (MIT) and [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django).

## Hard Rules

1. **Never invent settings or APIs.** Before using a CMS setting or API you are not certain of, grep the installed django-cms package (for settings: `cms/utils/conf.py`) to confirm it exists.
2. **Visual validation.** After any change that affects rendering, run `scripts/visual_check.py` and report the `RESULT:` line.

## VISUAL VALIDATION (MANDATORY)

One-time setup: `pip install playwright && playwright install chromium`.

```bash
python scripts/visual_check.py http://localhost:8000/ [--mobile] [--expect-text "Text"] [--login USER:ENV_VAR] [--out PATH]
```
Exit 0 = no issues; 1 = issues found; 2 = script/browser error. Output ends with `RESULT: PASS` or `RESULT: FAIL (N issues)`. If you cannot view images, rely on the printed text and exit code; do not claim visual confirmation.

## When to Use

- Creating/editing CMS pages, page trees, slugs
- Configuring `CMS_TEMPLATES`, placeholders, sekizai
- Writing custom CMS plugins or apphooks
- Customizing the CMS admin, migrations, middleware, settings
- CMS template development, debugging rendering or nav issues

## When NOT to Use

- General Django work (models, views, serializers, non-CMS admin, migrations, testing) → follow `django-expert`; use it alongside this skill when a task touches both
- Django architecture patterns → use `agentic-django`
- Azure OpenAI → use `microsoft-foundry`; Security → `secure-code-auditor`; Infra → `OpsKit`

## Scope

This single skill covers pages, placeholders, templates, plugins, admin, middleware and migrations. Detailed material is in references/:

- **Project setup** (TEMPLATES, MIDDLEWARE, X-Frame, toolbar, versioning, admindocs, debug toolbar, production hardening): read `references/project-setup.md` only when creating or fixing `settings.py` / `urls.py`.
- **Templates & themes** (Bootstrap default theme, template structure, menu, what was verified): read `references/templates-and-theme.md` only when creating or editing templates.
- **New site scaffolder** (name/purpose questions, flags, verify.sh, what is generated): read `references/new-site.md` when asked to create a site.
- **Plugin compatibility** (works / fails matrix, bootstrap5 caveats, transitive pins): read `references/plugins.md` only when adding or changing CMS plugins.
- **Finding packages** (Django Packages search, evaluation checklist, supply-chain care, trial, install/configure/record): read `references/django-packages.md` when the user asks whether a package exists or wants a feature a plugin could provide.

## Finding packages (Django Packages)

When the user asks "is there a package for X?" or for a feature a package could give (blog, forms, SEO, search, e-commerce, gallery, ...): (1) `bin/djangopackages.py search "<words>"` (and `grids <text>` / `grid <slug>`); it is a starting point, not a vetting authority; (2) shortlist 2-3 and apply the evaluation checklist in `references/django-packages.md` (Django 5.2, Python 3.12-3.14, django-cms 5.1.x, maintenance, license, migrations, extra services/CDN, `references/plugins.md` findings, supply chain); (3) tell the user, recommend one, and **ask before installing: never install unprompted**; (4) after a yes, `bin/package-trial.py NAME --app DOTTED` in a throwaway site; (5) install in the real site as described in the reference; (6) run `bin/verify.sh` and look at the screenshots; (7) record the result in `references/plugins.md`. **Never claim a package works until the trial and verify passed**: the table's compatibility column is a metadata heuristic, and a trial PASS means only check + migrate + import.

## New site (the one workflow to follow)

When asked to create a new DjangoCMS site: (1) **ask the human for the site name and its general purpose; never guess them**; (2) **check Playwright before scaffolding** (`bin/new-site.py` also runs this preflight and prints the exact setup; if missing, set it up once in a scratch venv, never system Python: `python3 -m venv /tmp/pw-venv && /tmp/pw-venv/bin/pip install playwright && /tmp/pw-venv/bin/playwright install chromium`, then `export PLAYWRIGHT_PYTHON=/tmp/pw-venv/bin/python`; `--require-playwright` makes a missing setup fatal); (3) run `bin/new-site.py --name ... --purpose ...` (from an installed skill: `<skills dir>/djangocms-agent/bin/new-site.py`); (4) run the generated `bin/verify.sh` and **look at the screenshots** in `verify-shots/`; (5) report honestly what was and was not verified (`VERIFY RESULT: INCOMPLETE` means no visual check happened, and the verify.sh coverage summary says what the visual step does not check). **Which URL to give the user:** pick the first free port >= 8000 (`ss -ltn`), print the exact command `DJANGO_DEBUG=1 DJANGO_SECRET_KEY=dev venv/bin/python manage.py runserver <port>`, and report `http://localhost:<port>/`. Report the `Admin login:` line exactly as the scaffolder printed it; never write the password to a file. Only then tell the user to look. The scaffolder derives a lowercase slug for the directory and package (`NetYetiSite` becomes `netyetisite`) and `bin/` paths are relative to the skill directory. Generated sites include a hardened Docker + PostgreSQL stack by default (`bin/docker-up.sh`, port 8889 via `APP_PORT`; separate dev stack `bin/dev-up.sh`, 8880; backup/restore, digest-pinned images, `bin/release.sh`; `--no-docker` opts out of the container files). Details, flags, exit codes: `references/new-site.md`. The script never runs `opskit` commands; OpsKit integration is just the generated `.opskit/pack.yml`.

**Link-mode installs:** `bin/`, `assets/`, `references/` and `scripts/` under the installed skill directory are symlinks into the repo clone, so these paths resolve and `readlink -f` shows the real source; copy-mode installs hold real copies.

## Default site

The site it installs is in `assets/default-site/` (see its `README.md`): a complete, verified Bootstrap 5 site (templates, static, `starter` app with seed commands, settings, urls, pinned requirements). Use it rather than memory; it carries the settings and gotchas above already worked out. Theme docs: `references/templates-and-theme.md`.

## CMS Gotchas (from TheNetYeti)

- **`create_page` requires a language code that is in your `LANGUAGES`/`CMS_LANGUAGES`** (the examples here use `en-us`; use whatever your project defines) — no `published=` kwarg. With djangocms-versioning it creates a **draft**; publish with `page.get_admin_content("en").versions.first().publish(user)`. Pass `in_navigation=True` for pages that belong in menus. Set the home page with `with transaction.atomic(): page.set_as_homepage()`.
- **Language codes are project-specific** — `en-us` in these docs is only an example. A project with `LANGUAGES = [("en", ...)]` must use `"en"` everywhere (`create_page`, `add_plugin`, `PageContent` filters), or lookups silently return nothing.
- **`create_page(created_by=...)`** — `None` crashes on a fresh DB with no superuser. A username string is accepted for creation, but **publishing needs a real user object**: the `"python-api"` string fallback cannot publish. In seed scripts get-or-create an (inactive) system user and pass that.
- **Versioning hides drafts from the normal API** — `Page.get_placeholders(lang)` only sees PUBLISHED content, so a freshly created draft page looks empty. Use `page.get_placeholders(lang, admin_manager=True)` or `PageContent.admin_manager.current_content()` when seeding or editing drafts, then publish.
- **Content that predates versioning** has no `Version` rows after installing djangocms-versioning and renders as missing. Fix once with `manage.py create_versions --state published --username <user>` (or create the `Version` yourself in code).
- **Seed scripts** — key idempotency on `PageUrl(slug=..., language=...)`, not on title (titles are not unique), and wrap each page's create/plugin/homepage work in one `transaction.atomic()` so a failed `add_plugin` can't leave an empty page that later runs skip.
- **Apphooks** — see `references/cms-api-cheatsheet.md` ("Apphooks"). Three things bite: set `CMSApp.app_name` to match the `app_name` in your `urls.py` and pass `apphook_namespace=` to `create_page` (else `{% url %}` raises `NoReverseMatch`); `cms.middleware.utils.ApphookReloadMiddleware` must be in `MIDDLEWARE`; tests must call `reload_urlconf()` (`from cms.utils.apphook_reload import reload_urlconf`) after creating apphook pages, because the urlconf is cached.
- **djangocms-versioning is optional** — without it there is no draft/publish step and pages are live on creation; the `.versions.first().publish()` recipe above only applies when it is installed.
- **Python 3.14** — the `djangocms` installer CLI fails (needs `distutils`/`pytz`, pulls Django 6.x); build the project by hand per `references/project-setup.md`.
- **`treebeard.E001` warning** on `cms.PageManager` with django-treebeard 5.3.x is upstream (cms 5.1.3); harmless until treebeard 6.
- **CMS page lookup** — slugs live in `PageUrl`: `PageUrl.objects.get(slug=slug).page`
- **Re-pointing page templates** — use `PageContent.objects.filter(page=page, language="en-us").first().template`
- **`{% render_block %}`** — cannot live inside a `{% block %}` (swallows following `{% endblock %}`)
- **`{% show_menu %}`** — needs `{% load menu_tags %}` and pages created with `in_navigation=True` (`create_page` defaults to `False`, so the menu renders empty). `cms.context_processors.cms_settings` is recommended but not required (`show_menu` builds its own renderer without it); `menus.context_processors.menus` does not exist
- **`{% %}` inside `{# #}` comments** — tokenizes/parse-fails; keep DTL comments free of `{% %}`

## CMS 5.x Notes

- **`CMS_CONFIRM_VERSION4` removed** — only needed for CMS 4.x migration from 3.x
- **sekizai** — still requires `{% render_block "css" %}`; `{% slot %}` is not used
- **menus** — see show_menu gotcha above

## References

- [CMS API Cheatsheet](references/cms-api-cheatsheet.md)
- [CMS Settings Reference](references/cms-settings-reference.md)
- [CMS Commands Reference](references/cms-commands-cheatsheet.md)
