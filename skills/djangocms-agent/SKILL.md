---
name: djangocms-agent
description: >-
  DjangoCMS specialist agent for django-cms 4.x. Handles page trees,
  placeholders, templates, content plugins, admin customization, middleware,
  and migrations. Includes django-ai-plugins and agentic-django as Django
  foundation dependencies. Use for any DjangoCMS work: creating pages with
  placeholders, building custom CMS plugins, configuring CMS settings,
  writing CMS migrations, and customizing the CMS admin.
  
  This agent credits and builds on:
  - vintasoftware/django-ai-plugins (MIT) for multi-host agent structure
  - MohamedMandour10/agentic-django for Django architecture patterns
  
  DO NOT USE FOR: general Django work not involving CMS — use the
  django-expert skill from vintasoftware/django-ai-plugins for that.
  DO NOT USE FOR: Azure OpenAI, infrastructure, security — use the
  appropriate domain-specific agent for those.
license: MIT
metadata:
  author: growlf
  version: "0.1.0"
  compatibility: claude-code, opencode, codex, cursor
---

# DjangoCMS Agent

> **DjangoCMS specialist** — handles the entire django-cms 4.x stack.
> 
> **Credit:** Built on patterns from [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) (MIT) and [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django).

## When to Use

Invoke this agent when working with any DjangoCMS-related code:

- Creating/editing CMS pages, page trees, slugs
- Configuring `CMS_TEMPLATES`, placeholders, sekizai
- Writing custom CMS content plugins or apphooks
- Customizing the CMS admin (`PageAdmin`, plugin admin)
- Writing CMS migrations or data migrations
- Configuring CMS middleware, settings, `CMS_CONFIRM_VERSION4`
- CMS template development (`{% load cms_tags %}`, `{% show_menu %}`)
- Debugging CMS page rendering, nav, or placeholder issues

## When NOT to Use

- **General Django work** (models, views, serializers, DRF) → use `django-expert` from [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins)
- **Django architecture patterns** (service layer, selectors) → use `agentic-django` from [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django)
- **Azure OpenAI / Foundry** → use `microsoft-foundry`
- **Security auditing** → use `secure-code-auditor`
- **Infrastructure / DevOps** → use `OpsKit`

## Dependency: Django Foundation

When working on Django code that touches both CMS and non-CMS areas (models,
views, admin, migrations), follow the relevant skill from the Django foundation
agents in addition to CMS-specific guidance:

1. **Django models/ORM** → follow `django-expert` models guidance
2. **Django views/DRF** → follow `django-expert` views/API guidance
3. **Django admin** → follow `django-expert` admin guidance (non-CMS parts)
4. **Django migrations** → follow `django-expert` migrations + `djangocms-migration` for CMS-specific patterns
5. **Django testing** → follow `django-expert` testing guidance

## Skills

| Skill | Trigger Files |
|-------|---------------|
| `djangocms-architecture` | `cms/urls.py`, `CMS_TEMPLATES`, `cms.py` |
| `djangocms-pages` | `Page`, `PageUrl`, `PageContent`, `create_page` |
| `djangocms-placeholders` | `Placeholder`, `render_block`, `{% cms_placeholder %}` |
| `djangocms-templates` | CMS templates, `{% load cms_tags %}`, `{% show_menu %}` |
| `djangocms-admin` | `cms.admin.*`, `PageAdmin`, plugin admin files |
| `djangocms-plugins` | Custom plugin files, `CMSConfig`, apphooks |
| `djangocms-middleware` | `MIDDLEWARE`, CMS settings, `CMS_CONFIRM_VERSION4` |
| `djangocms-migration` | CMS migrations, `RunPython` on CMS models |

## CMS Gotchas (from TheNetYeti)

These are captured from production experience with DjangoCMS 4.1 + Django Templates:

- **`create_page` requires `language="en-us"`** — no `published=` kwarg (uses `CMS_DEFAULT_INTENT`)
- **CMS 4.1 page lookup** — slugs live in `PageUrl`: `PageUrl.objects.get(slug=slug).page`
- **Re-pointing page templates** — use `PageContent.objects.filter(page=page, language="en-us").first().template`
- **`{% render_block %}`** — cannot live inside a `{% block %}` (swallows following `{% endblock %}`)
- **`{% show_menu %}`** — requires `menus.context_processors.menus` which may not be available
- **`{% %}` inside `{# #}` comments** — tokenizes/parse-fails; keep DTL comments free of `{% %}`

## References

- [CMS API Cheatsheet](references/cms-api-cheatsheet.md)
- [CMS Settings Reference](references/cms-settings-reference.md)
- [CMS Commands Reference](references/cms-commands-cheatsheet.md)
