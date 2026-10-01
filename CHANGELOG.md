# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

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
