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

## Visual Validation

Before and after every CMS change, run the visual check script
(one-time setup: `pip install playwright && playwright install chromium`;
tests: `python3 -m unittest scripts/test_visual_check.py`):

```bash
# Check a page (default desktop 1280×800)
python scripts/visual_check.py http://localhost:8000/ --expect-text "Welcome"

# Mobile viewport
python scripts/visual_check.py http://localhost:8000/ --mobile

# Save screenshot to custom path
python scripts/visual_check.py http://localhost:8000/ --out /tmp/verify.png

# With login (password from environment variable)
python scripts/visual_check.py http://localhost:8000/ --login admin:DJANGO_PASS
```

Exit code 0 = no issues, 1 = issues found, 2 = script/browser error.
If you cannot view images, rely on the printed text and exit code; do not claim visual confirmation.

## Create a new site

```bash
python3 bin/new-site.py --name "Acme Garden Club" --purpose "Member news and events" --parent-dir ~/Projects
```

Builds the full default site in a new folder: Bootstrap 5 theme (landing, About, Style & Capabilities),
plugins, versioning, DEBUG-only debug toolbar, admindocs, FOSS files (LICENSE, CODE_OF_CONDUCT,
CONTRIBUTING, SECURITY, issue/PR templates, AGENTS.md + CLAUDE.md recording the purpose), an OpsKit
`.opskit/pack.yml`, a venv with pinned requirements, migrated and seeded database, an `admin` user with a
random password printed once, a git repo, and `bin/verify.sh` (check, migrations, tests, seed idempotency,
Playwright screenshots desktop + mobile) and, unless `--no-docker`, a Docker + PostgreSQL stack
(`bin/docker-up.sh`, WhiteNoise, `/health/`, default port 8889 via `APP_PORT`). Name and purpose must come from the human; `--dry-run` shows the
plan. Exit codes 0 ok, 1 step failed, 2 usage error. Full reference: `references/new-site.md`.
Tests: `python3 -m pytest tests/`.

## Find packages (Django Packages)

```bash
python3 bin/djangopackages.py search "django cms blog"     # packages + related grids + PyPI facts + compat heuristic
python3 bin/djangopackages.py grids forms                  # comparison grids about forms
python3 bin/djangopackages.py grid djangocms-plugins       # members of a grid, ranked
python3 bin/djangopackages.py show djangocms-versioning
python3 bin/package-trial.py djangocms-markdown --app djangocms_markdown   # throwaway install + check + migrate
```

Stdlib-only; uses the key-less Django Packages API v4 and the PyPI JSON API, caches for 6 hours, never
installs anything itself. `package-trial.py` builds a throwaway copy of the default site in a temp dir and
reports PASS/FAIL per step; PASS means only install + import + `check` + `migrate`, not that the package
renders. The agent searches and recommends, and installs only when you ask. Checklist, supply-chain care,
verified API facts and the install/configure/record procedure: `references/django-packages.md`.

## Installation

### Recommended: the installer

One command installs the skills and subagents for Claude Code, OpenCode and Crush.
Skills go in `.claude/skills/` (all three tools read it, so each skill is installed once);
Claude Code agents go in `.claude/agents/`; OpenCode agents are generated into `.opencode/agent/`.
Crush has no agent files and just uses the skills.

```bash
git clone https://github.com/growlf/djangocms-agent.git
cd djangocms-agent

python3 bin/install.py --project /path/to/your/project        # symlink skills (default; follows `git pull`)
python3 bin/install.py --project /path/to/your/project --copy # copy instead of symlink
python3 bin/install.py --global                               # install for your user (~/.claude, ~/.config/opencode)
python3 bin/install.py --dry-run --project /path/to/project   # show what would happen, change nothing

python3 bin/install.py doctor --project /path/to/your/project # is the install present and current?
python3 bin/install.py --uninstall --project /path/to/your/project
```

Options: `--hosts claude,opencode,crush` (default `claude,opencode`).
The installer only touches files it created (tracked in `.djangocms-agent.lock`), refuses to
overwrite anything else, and changes nothing if it finds a conflict. Exit codes: 0 ok,
1 conflict/behind/missing files, 2 error or no lockfile.
Tests: `python3 -m unittest tests/test_install.py`.

### From OpsKit

This repo is an OpsKit member (`.opskit/pack.yml`). From an OpsKit checkout, mount it with
`opskit member sync-mount`.

### Manual (no installer)

Copy the two skill folders into `.claude/skills/` (project) or `~/.claude/skills/` (global):

```bash
cp -r skills/djangocms-agent skills/djangocms-reviewer /path/to/your/project/.claude/skills/
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
