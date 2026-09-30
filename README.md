# DjangoCMS Agent

> A DjangoCMS specialist agent for Claude Code and OpenCode.
> Covers page trees, placeholders, templates, plugins, admin, middleware, and migrations for django-cms 5.x.

**Credit & dependencies:**

- Built on patterns from [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) (MIT) for multi-host agent structure and plugin registry (`catalog.json`).
- Django architecture patterns inspired by [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django).
- Core framework: [django-cms/django-cms](https://github.com/django-cms/django-cms) (BSD 3-Clause).

## Stack

| Component | Version |
|-----------|---------|
| Python | 3.12 or 3.13 |
| Django | 5.2 LTS |
| django-cms | 5.1.3 |

## What It Does

This agent provides expert guidance on the entire django-cms 5.x stack:

- **Page trees** — `create_page`, `PageUrl`, `PageContent`, slugs, language handling
- **Placeholders** — Placeholder regions, `render_block`, sekizai integration, content plugins
- **Templates** — CMS template structure, `{% load cms_tags %}`, `{% show_menu %}`, nav
- **Content plugins** — Writing custom CMS plugins, apphooks, CMS config
- **Admin** — CMS admin customization, page admin, plugin registration
- **Middleware** — Middleware ordering, CMS settings, language config
- **Migrations** — Zero-downtime CMS migrations, data migrations, version upgrades

## Installation

### Option 1: Skills CLI (recommended)

```bash
# Install all skills
npx skills add growlf/djangocms-agent --global

# Or install into a specific project
npx skills add growlf/djangocms-agent
```

### Option 2: Clone and Copy

```bash
git clone https://github.com/growlf/djangocms-agent.git
cp -r djangocms-agent/skills ~/.agents/
cp -r djangocms-agent/plugins/djangocms-agent ~/.agents/
```

### Option 3: Git Submodule

```bash
git submodule add https://github.com/growlf/djangocms-agent .agents/skills/djangocms-agent
```

## Included Skills

| Skill | Focus |
|-------|-------|
| `djangocms-agent` | Main orchestrator — project structure, CMS_TEMPLATES, page layout, placeholders, templates, plugins, admin, middleware, migrations |
| `djangocms-reviewer` | Code review for DjangoCMS projects |

## Usage

Once installed, the agent triggers automatically when CMS-related context is detected:

- CMS template files (`base_cms.html`, `page.html`)
- `cms/urls.py`, `cms.py` settings
- `Page`, `Placeholder`, `create_page` usage in Python code
- CMS admin (`cms.admin.*`, `PageAdmin`)

You can also invoke it explicitly:

```
/djangocms-agent
```

## Architecture

This project follows the same plugin registry pattern as [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins):

- `catalog.json` — canonical plugin definitions and metadata
- `skills/` — canonical skill implementations
- `plugins/` — host-specific adapters (Claude Code agents, OpenCode plugins)
- `references/` — CMS API cheatsheets, settings references, command docs

## License

MIT © [growlf](https://github.com/growlf)

## Dependencies & Credits

| Project | License | What We Use |
|---------|---------|-------------|
| [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) | MIT | Plugin registry structure, multi-host agent pattern, catalog.json format |
| [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django) | No formal license | Skill organization, Django architecture patterns, skill boundaries |
| [django-cms/django-cms](https://github.com/django-cms/django-cms) | BSD 3-Clause | Core CMS framework (referenced, not included) |
