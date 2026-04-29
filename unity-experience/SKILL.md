---
name: unity-experience
description: Use when the user wants to record Unity development经验, severe bugs, debugging conclusions, project pitfalls, or reusable lessons into a persistent skill knowledge base.
---

# Unity Experience (project-local)

This skill is the **local knowledge + write-back engine** for the Unity self-evolving workflow.

## Attribution

二次开发：`https://github.com/Besty0728/Unity-Skills`

## Knowledge Layout

```text
UnityKnowledge/
  raw/<Domain>/
  summary/<Domain>/
  index/knowledge_index.json
  index/knowledge_index.db
  archive/<Domain>/
  templates/
  logs/task-logs/
  logs/session-logs/
  logs/tool-usage/tool-usage-YYYY-MM.jsonl
  logs/archive/
```

Domains: `UI`, `Scene`, `Prefab`, `Code`, `HotUpdate`, `Assets`, `Debug`, `Performance`.

SQLite tables:

- `knowledge_entries`, `knowledge_tags`
- `usage_aggregates`
- `task_logs`, `knowledge_usage_logs`
- `cleanup_runs`

## Commands

```bash
python scripts/self_evolving_knowledge.py
python scripts/self_evolving_knowledge.py --summary
python scripts/self_evolving_knowledge.py --cleanup --raw-retention-days 30 --task-retention-days 90
```

## Notes

- Do **not** commit local `UnityKnowledge/` logs/databases to Git.
- Commit templates + scripts only.

