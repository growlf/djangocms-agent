# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- `assets/default-site/`: a complete, copyable Bootstrap 5.3 default site ported from the verified testsite build: templates (base, landing, standard, menu), static (site.css, theme.js, vendored Bootstrap 5.3.3 with its MIT LICENSE), a `starter` app (generic trusted-editors-only `HtmlBlock` plugin, `seeding.py`, idempotent `seed_pages`/`seed_site`, 20 tests), `settings_fragment.py`, `urls_fragment.py`, context processor, pinned `requirements.txt`. Project-specific tokens are `__PROJECT_NAME__` and `__SITE_NAME__` (a scaffold script is a later change). Testsite-only parts (testlog app, findings text) were removed and `CMS_PLACEHOLDER_CONF` now names `feature_1..3`.
- `skills/djangocms-agent/assets` symlink so installed skills (link and copy modes) can read the assets; installer tests cover both modes, doctor and uninstall.

### Fixed (found by the default-site build)
- `references/plugins.md` rewritten as a works/fails matrix: bootstrap5 passes only for its base app and the alerts/badge/card/collapse/content/jumbotron/listgroup/picture/tabs/utilities contrib apps; `bootstrap5_grid`, `bootstrap5_link`, `bootstrap5_carousel` fail, djangocms-snippet is unsuitable, text-ckeditor must stay out of `INSTALLED_APPS`; bootstrap5 quirks (picture replaces stock picture, no default classes via `add_plugin`, unfixable migration drift, Google Map needs an API key).
- `SKILL.md` gotchas: `get_placeholders(lang)` sees only published content (use `admin_manager=True`); `create_versions` for pre-versioning content; the `"python-api"` string cannot publish, a real user object is required.
- `references/project-setup.md`: debug toolbar inserted at index 1 and DEBUG-only (index 0 broke the ApphookReloadMiddleware-first rule); TEMPLATES `loaders` conflicts with `APP_DIRS: True`; admindocs prefix (`admin/docs/` vs Django's `admin/doc/`); toolbar settings note that `CMS_TOOLBAR_REQUIRE_SUPERUSER`/`ANONYMOUS_EDIT` do not exist.
- `references/templates-and-theme.md` rewritten for the Bootstrap theme (hamburger and Bootstrap are now implemented); the checklist ticks only what was run and lists what was not (logged-in toolbar and `/admin/docs/` in a browser, numeric contrast).

### Removed
- `references/default-theme.html`, `default-theme-two-column.html`, `default-menu.html`, `default.css`: superseded by `assets/default-site/` (no duplicated copies to drift).

### Changed
- Default theme reference files replaced with the version built and checked in the testsite project (all pages passed `visual_check.py` on desktop and mobile): `default-theme.html` (base), new `default-theme-two-column.html` and `default-menu.html`, and `default.css` (now `--site-*` tokens, dark mode, `:focus-visible`, skip link, restored text spacing, styled nested menu with dropdowns). The `netyeti` prefix is gone. `templates-and-theme.md` rewritten to match, with a verification checklist that only ticks what was run; hamburger and Bootstrap compatibility are listed as not implemented.
- `references/project-setup.md`: new "Static files and site name" section (`STATICFILES_DIRS`, `STATIC_ROOT`, `SITE_NAME` + context processor).
- Fixed in the old reference theme: undefined `{{ site_name }}`, claimed-but-missing dark mode, menu selectors that never matched `{% show_menu %}` output, `* { margin:0; padding:0 }` stripping content spacing, links with no underline, hardcoded `cms-home` class, always-on sidebar, bare `<li>` directly in `<nav>`, no `{% block %}` hook, `default.html` vs `default-theme.html` naming, `CMS_TEMPLATES` entry that was not a template path.

### Fixed (found by the testsite exercise, 2026-09-30)
- `skills/djangocms-reviewer/SKILL.md`: no longer hardcodes `language="en-us"` (it must match the project's `LANGUAGES`); adds apphook checks (`app_name`/`apphook_namespace`, `ApphookReloadMiddleware`, `reload_urlconf()` in tests) and seed-script checks (slug+language idempotency, `atomic()`, `created_by`).
- `skills/djangocms-agent/` now contains `references` and `scripts` symlinks to the repo-level directories. In link-mode installs only `SKILL.md` was visible, so `scripts/visual_check.py` and every `references/` link it names appeared missing.
- `SKILL.md` gotchas: project-specific language codes, `created_by=None` crash, seed idempotency keyed on slug+language inside `atomic()`, optional djangocms-versioning, Python 3.14 installer failure, upstream `treebeard.E001`.
- `references/cms-api-cheatsheet.md`: new Apphooks section (`app_name`/`apphook_namespace`, `ApphookReloadMiddleware`, `reload_urlconf()` in tests).

### Added
- `references/project-setup.md`: verified `MIDDLEWARE` section (the docs listed none; a project built from them lacked `SecurityMiddleware`, `XFrameOptionsMiddleware`, `LocaleMiddleware` and `ApphookReloadMiddleware`) and a production hardening checklist checked with `manage.py check --deploy`.

## 0.5.0 - 2026-09-30

### Fixed (found by building a scratch django-cms 5.1.3 project from the docs)
- `show_menu` does NOT require `cms.context_processors.cms_settings` (it falls back to its own renderer); it needs pages with `in_navigation=True`. The earlier claim was wrong.
- The documented `INSTALLED_APPS` omitted `django.contrib.sites` (+ `SITE_ID`): startup crashed.
- `docutils` is not installed with Django; admindocs needs `pip install docutils`.
- Plugin list: `djangocms-form` does not exist on PyPI; `djangocms-social` 0.4a1 crashes on Django 5.2. Removed. Alias/picture/video/file/style/bootstrap5/googlemap pass check + migrate.
- `create_page` creates a draft under djangocms-versioning; publishing, `in_navigation` and homepage recipes documented.
- Both menu variants and the page template now verified to render.

### Added
- `bin/install.py`: idempotent installer for Claude Code, OpenCode and Crush (`--project`/`--global`, `--link`/`--copy`, `--dry-run`, `--uninstall`, `doctor`), lockfile-tracked so it only ever touches its own files; 20 tests.
- `agents/djangocms-agent.md` and `agents/djangocms-reviewer.md`: canonical subagent definitions (OpenCode format is generated from them).
- `.opskit/pack.yml`: OpsKit member manifest.
- `references/project-setup.md`, `references/templates-and-theme.md`, `references/plugins.md`.

### Changed
- `SKILL.md` slimmed from ~420 to ~75 lines; detail moved to `references/` (read on demand).
- `scripts/visual_check.py` rewritten: real exit codes (0 pass / 1 issues / 2 error), console-error and failed-subresource detection, exact 404 detection (no more false 404s on pages that mention "not found"), `--mobile`, `--expect-text`, `--login`; unit tests added.


### Fixed (earlier review rounds)
- Removed duplicate sections from djangocms-agent SKILL.md (deduplicated ~160 lines)
- Removed invalid settings: `CMS_TOOLBAR_ANONYMOUS_EDIT`, `CMS_TOOLBAR_REQUIRE_SUPERUSER`, `CMS_TOOLBAR_URL__EDIT_ON`, `CMS_TOOLBAR_URL__EDITMODE`
- Removed non-existent setting `CMS_DEFAULT_INTENT` from all docs
- Corrected `{% show_menu %}` guidance (`menus.context_processors.menus` does not exist; see Unreleased for the later correction that `cms_settings` is recommended but not required)
- Aligned references and adapters with django-cms 5.x (replaced all 4.x references)
- Replaced `djangocms-text-ckeditor` with `djangocms-text` (correct package for CMS 5.x)
- Removed references to 8 sub-skills that do not exist
- Removed further non-existent settings from references: `CMS_SEO_FIELDS`, `CMS_TOOLBAR_URL__PASTE`, `CMS_NAVIGATION_EXTENDERS`
- Fixed root-redirect example that redirected `/` to itself; relabelled unproven template/checklist sections as unverified
- Gated debug toolbar configuration on `DEBUG` flag; removed unsafe "Safe for production" claim

### Verification status
- Proven (scratch project, cms 5.1.3 / Django 5.2.17, 2026-09-30): documented settings boot with `sites` added; `show_menu` and the hand-rolled menu render; versioning publish recipe; installer output is discovered by OpenCode (both skills once, from `.claude/skills`; `djangocms-agent` loads as a subagent).
- Not proven: Crush discovery (not run on purpose), plugin rendering (only check/migrate), mobile layout, `CMS_TOOLBAR_*` behaviour.
