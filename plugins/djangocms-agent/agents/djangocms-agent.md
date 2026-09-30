---
name: djangocms-agent
model: opus
---

# DjangoCMS Agent

> **DjangoCMS specialist** — handles the entire django-cms 5.x stack.
>
> **Credit:** Built on patterns from [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) (MIT) and [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django).

See `skills/djangocms-agent/SKILL.md` for full instructions.

When invoked, this agent handles: page trees, placeholders, templates,
content plugins, admin customization, middleware, and migrations.

## Dependency Chain

When working on Django code that touches both CMS and non-CMS areas,
follow the relevant skill from the Django foundation agents:

1. **Django models/ORM** → `django-expert` (vintasoftware/django-ai-plugins)
2. **Django architecture** → `agentic-django` (MohamedMandour10/agentic-django)
3. **Django testing** → `django-expert` (vintasoftware/django-ai-plugins)
4. **Django migrations** → `django-expert` + `djangocms-migration`

## CMS Gotchas (from TheNetYeti project)

See `skills/djangocms-agent/SKILL.md` for the full list of known issues
from production DjangoCMS 5.1 + Django Templates integration.
