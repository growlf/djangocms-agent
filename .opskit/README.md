# djangocms-agent is OpsKit-aware

This project declares an OpsKit member manifest (`.opskit/pack.yml`), which lets
it be driven and developed as a **subagent** from OpsKit
(https://github.com/CascadeSTEAM/opskit) — its knowledge (docs) and any subagent/skill definitions are
mounted read-only into an OpsKit session, sandboxed per the manifest's `trust`.

Nothing here is required to use this project on its own; the manifest is purely
additive.

## Keeping it aligned (CI)

`.opskit/pack.yml` targets a versioned contract. Validate it so drift fails
your build:

```bash
# If you have the OpsKit repo available:
python3 <opskit>/bin/opskit-aware.py check .

# Standalone (schema only, no path checks) — fetch the published schema:
pip install check-jsonschema
curl -fsSL https://github.com/CascadeSTEAM/opskit/raw/main/schemas/project.schema.json -o /tmp/project.schema.json
check-jsonschema --schemafile /tmp/project.schema.json .opskit/pack.yml
```

## Rules (see the OpsKit `docs/opskit-aware.md` guide)

- Contribute documentation-range, environment-agnostic knowledge only — real
  facts (hosts, secrets, findings) never live in a member.
- Sandbox the subagent in its `agents/*.md` frontmatter; if this project's docs
  describe a dual-use or destructive procedure, the mounting subagent must gate
  it behind explicit per-invocation approval.
