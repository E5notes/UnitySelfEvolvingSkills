---
name: unity-skills
description: "Unity Editor automation via REST API (project-local wrapper)."
---

# Unity Editor Control Skill (project-local)

This is the **execution layer** used by this repo to control Unity Editor through the UnitySkills REST server.

## Attribution

二次开发：`https://github.com/Besty0728/Unity-Skills`

## Prerequisites

1. Unity Editor is running with the UnitySkills package installed
2. Start server: **Window > UnitySkills > Start Server**
3. Endpoint: `http://127.0.0.1:8090` (this repo uses loopback IP due to host validation)

## Quick Start

```python
import sys
sys.path.insert(0, 'CursorSkills/unity-skills/scripts')
from unity_skills import call_skill, is_unity_running

if is_unity_running():
    call_skill('gameobject_create', name='MyCube', primitiveType='Cube', x=0, y=1, z=0)
```

## Self-Evolving Workflow Integration

When used together with `CursorSkills/unity-experience`, this helper:

- logs tool calls to rotated raw logs
- updates SQLite `usage_aggregates`
- supports task-level start/finish hooks for recall + write-back

See `CursorSkills/unity-experience/SKILL.md`.

