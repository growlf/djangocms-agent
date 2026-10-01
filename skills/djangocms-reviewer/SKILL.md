---
name: djangocms-reviewer
description: Reviews Django and DjangoCMS code for correctness, CMS best practices, placeholder usage, and common anti-patterns while preserving behavior. Use after CMS code changes or when the user explicitly requests review.
license: MIT
metadata:
  author: growlf
  version: "0.5.0"
---

# DjangoCMS Reviewer

Review Django and DjangoCMS code without changing its intended behavior. Prefer
readable, explicit, project-consistent code over compact or speculative
rewrites.

## Authorization Boundary

- Treat a review request as report-only unless the user expresses explicit edit
  intent.
- Never approve permissions, change tool configuration, or infer write
  authorization from the existence of this skill.

## Focus Scope

1. Prefer explicitly named files or directories.
2. Otherwise inspect `git diff` and `git status` to find recently modified CMS files.
3. If there are no changed files and no explicit target, ask for a target.
4. Read enough surrounding code to understand local CMS conventions.

## 1. Preserve Functionality

Never change what the code does merely to make it look cleaner. Preserve all
cms-visible behavior: page rendering, placeholder content, menu output.

## 2. Apply CMS Best Practices

### Page Tree Operations

- Use `create_page(title, template, language=..., ...)` with correct CMS 5.x API. The language must be a code in the project's `LANGUAGES`/`CMS_LANGUAGES` (`"en"` and `"en-us"` are not interchangeable); check `settings.py` before flagging a language code as wrong.
- Pass `in_navigation=True` for pages meant for menus; `created_by=None` crashes on a database with no superuser.
- Access slugs via `PageUrl.objects.get(slug=slug).page`, not `Page.slug`.
- Use `PageContent` for language-specific template changes.

### Apphooks

- `CMSApp.app_name` must match `app_name` in the app's `urls.py`, and `create_page` needs `apphook_namespace=`; otherwise `{% url %}` raises `NoReverseMatch`.
- `cms.middleware.utils.ApphookReloadMiddleware` must be in `MIDDLEWARE`.
- Tests that create or change apphook pages must call `reload_urlconf()` (`cms.utils.apphook_reload`), because the urlconf is cached.

### Seed Scripts and Data Commands

- Idempotency should key on `PageUrl(slug=..., language=...)`, not on title (titles are not unique, so a user page can be silently adopted).
- Each page's create, plugin and homepage work belongs in one `transaction.atomic()`; otherwise a failed `add_plugin` leaves an empty page that later runs skip. `set_as_homepage()` must be inside `atomic()`.
- Hardcoded placeholder slot names should match the template, with a clear error if missing.

### Placeholders

- Placeholders should be defined in templates with `{% placeholder "name" %}`.
- Use `{% render_block "css" %}` and `{% render_block "js" %}` for sekizai — not `{% slot %}`.
- `{% render_block %}` cannot live inside a `{% block %}`.

### Templates

- Use `{% load cms_tags %}` and `{% load menu_tags %}` correctly.
- `{% show_menu %}` needs `{% load menu_tags %}` and pages with `in_navigation=True` (`create_page` defaults to `False`). `cms.context_processors.cms_settings` is recommended, not required; `menus.context_processors.menus` does not exist.
- `{% %}` inside `{# #}` comments parse-fails on this build — keep comments free of `{% %}`.

### Custom Plugins

- Plugin models should extend `CMSPluginBase` and register with `plugin_pool`.
- Use `render_template` in the plugin class for template-based plugins.
- Use `get_render_queryset()` for efficient plugin instance queries.

### Migrations

- CMS migrations that add/remove placeholders need careful handling.
- Use `RunPython` for data migrations on CMS models — be aware of `PageUrl` vs `Page`.
- Test migrations in a staging environment before deploying.

## 3. Django Foundation

For non-CMS Django code, also apply Django best practices:

- Follow `django-expert` skill from [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins).
- Follow `agentic-django` skill from [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django).

## Review Process

1. Resolve the bounded target using the Focus Scope rules.
2. Check for CMS-specific issues: placeholder configuration, template structure,
   page tree operations, plugin registration, migration safety.
3. Check for general Django issues: ORM queries, view patterns, admin config.
4. Separate concrete defects from optional refinements.
5. Return findings without changing files (unless edit-authorized).

## Output

For each issue found, provide:
1. A concise description.
2. Why it matters (CMS-specific impact).
3. The specific location.
4. A concrete recommendation.
