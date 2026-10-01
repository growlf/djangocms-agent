# Djangocms Agent

## OpenCode

OpenCode reads skills from `.claude/skills/` (the installer puts them there once) and
agents from `.opencode/agent/` (the installer generates them).

## Installation

Use the installer from the repo root (see the main README):

```bash
python3 bin/install.py --project /path/to/your/project
```

## After Installation

The DjangoCMS agent will trigger automatically when CMS-related context is
detected in your project files.

To invoke explicitly:

```
/djangocms-agent
```
