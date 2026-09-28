# Djangocms Agent

## OpenCode Plugin

This package registers the `skills/` directory as an OpenCode skills path.
OpenCode will automatically load skills from `.opencode/skills/djangocms-agent/`.

## Installation

Run this from your project root:

```bash
# Copy skills to your opencode skills directory
cp -r skills ~/.config/opencode/skills/

# Or clone as a submodule
git submodule add https://github.com/growlf/djangocms-agent .agents/skills/djangocms-agent
```

## After Installation

The DjangoCMS agent will trigger automatically when CMS-related context is
detected in your project files.

To invoke explicitly:

```
/djangocms-agent
```
