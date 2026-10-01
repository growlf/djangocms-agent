---
name: djangocms-agent
description: 'DjangoCMS 5.x specialist. Use for: django-cms, cms pages, placeholders, cms plugins, cms templates, cms migrations, toolbar, apphooks.'
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

- **Project setup** (TEMPLATES, X-Frame, toolbar, versioning, admindocs, debug toolbar): read `references/project-setup.md` only when creating or fixing `settings.py` / `urls.py`.
- **Templates & themes** (default theme, template structure, menu, mobile checklist, CSS): read `references/templates-and-theme.md` only when creating or editing templates.
- **Plugin lists** (proven, untested, transitive pins): read `references/plugins.md` only when adding or changing CMS plugins.

## CMS Gotchas (from TheNetYeti)

- **`create_page` requires `language="en-us"`** — no `published=` kwarg
- **CMS page lookup** — slugs live in `PageUrl`: `PageUrl.objects.get(slug=slug).page`
- **Re-pointing page templates** — use `PageContent.objects.filter(page=page, language="en-us").first().template`
- **`{% render_block %}`** — cannot live inside a `{% block %}` (swallows following `{% endblock %}`)
- **`{% show_menu %}`** — requires `{% load menu_tags %}` and `cms.context_processors.cms_settings` context processor; `menus.context_processors.menus` does not exist
- **`{% %}` inside `{# #}` comments** — tokenizes/parse-fails; keep DTL comments free of `{% %}`

## CMS 5.x Notes

- **`CMS_CONFIRM_VERSION4` removed** — only needed for CMS 4.x migration from 3.x
- **sekizai** — still requires `{% render_block "css" %}`; `{% slot %}` is not used
- **menus** — see show_menu gotcha above

## References

- [CMS API Cheatsheet](references/cms-api-cheatsheet.md)
- [CMS Settings Reference](references/cms-settings-reference.md)
- [CMS Commands Reference](references/cms-commands-cheatsheet.md)
