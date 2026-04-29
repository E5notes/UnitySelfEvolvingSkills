#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local Unity self-evolving knowledge helpers.

This module intentionally stays file-based so the skill can work without a
separate database service. It mirrors the workflow in UnitySelfEvolvingWorkflowSpec:
raw markdown, summaries, JSON/SQLite-ready index data, and task/usage logs.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DOMAINS = ("UI", "Scene", "Prefab", "Code", "HotUpdate", "Assets", "Debug", "Performance")
TASK_TYPES = (
    "create",
    "create_template",
    "create_scene",
    "create_prefab",
    "create_panel",
    "create_system",
    "update",
    "refactor",
    "resize",
    "reposition",
    "restructure",
    "rebind",
    "fix_layout",
    "fix_reference",
    "fix_compile",
    "fix_load",
    "fix_hotupdate",
    "fix_addressables",
    "optimize_layout",
    "optimize_structure",
    "optimize_loading",
    "optimize_performance",
    "optimize_ux",
    "validate_scene",
    "validate_ui",
    "validate_prefab",
    "validate_dependency",
    "validate_hotupdate",
    "migrate_project",
    "migrate_framework",
    "migrate_assets",
    "migrate_ui",
)
FRAMEWORK_TAGS = (
    "Unity",
    "UGUI",
    "TextMeshPro",
    "C#",
    "HybridCLR",
    "Addressables",
    "ZMUI",
    "ZMGC",
    "BattleWorld",
    "Unity2022",
    "Mobile",
    "PC",
    "Commercial",
    "Prototype",
)
DB_SCHEMA_VERSION = 1
RAW_LOG_MAX_BYTES = int(os.environ.get("UNITY_KNOWLEDGE_RAW_LOG_MAX_BYTES", str(50 * 1024 * 1024)))


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def knowledge_root() -> Path:
    configured = os.environ.get("UNITY_KNOWLEDGE_ROOT")
    return Path(configured).expanduser().resolve() if configured else skill_root() / "UnityKnowledge"


def db_path() -> Path:
    return knowledge_root() / "index" / "knowledge_index.db"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def slugify(value: str, fallback: str = "unity-note") -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip(), flags=re.UNICODE)
    value = re.sub(r"-+", "-", value).strip("-_")
    return value[:80] or fallback


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


def init_knowledge_base() -> None:
    root = knowledge_root()
    for base in ("raw", "summary", "archive"):
        for domain in DOMAINS:
            (root / base / domain).mkdir(parents=True, exist_ok=True)
    for path in ("index", "templates", "logs/task-logs", "logs/session-logs", "logs/tool-usage", "logs/archive"):
        (root / path).mkdir(parents=True, exist_ok=True)
    index_path = root / "index" / "knowledge_index.json"
    if not index_path.exists():
        write_json(index_path, {"entries": [], "relations": [], "usage_logs": [], "updated_at": now_iso()})
    init_database()


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    root = knowledge_root()
    (root / "index").mkdir(parents=True, exist_ok=True)
    conn = connect_db()
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT,
                category TEXT,
                subcategory TEXT,
                task_type TEXT,
                frameworks_json TEXT,
                project_name TEXT,
                status TEXT,
                weight REAL DEFAULT 0,
                usage_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                last_used_at TEXT,
                md_path TEXT,
                summary_path TEXT,
                fingerprint TEXT,
                version_tag TEXT,
                is_core INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_entries_lookup
                ON knowledge_entries(category, task_type, status, weight DESC, updated_at DESC);
            CREATE TABLE IF NOT EXISTS knowledge_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                tag_type TEXT NOT NULL,
                UNIQUE(entry_id, tag, tag_type)
            );
            CREATE INDEX IF NOT EXISTS idx_tags_lookup ON knowledge_tags(tag, tag_type);
            CREATE TABLE IF NOT EXISTS usage_aggregates (
                fingerprint TEXT PRIMARY KEY,
                category TEXT,
                task_type TEXT,
                frameworks_json TEXT,
                tool_family TEXT,
                skill_names_json TEXT,
                target_type TEXT,
                total_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                first_seen_at TEXT,
                last_seen_at TEXT,
                sample_task_ids_json TEXT,
                sample_errors_json TEXT,
                sample_params_json TEXT,
                weight REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_aggregates_lookup
                ON usage_aggregates(category, task_type, tool_family, weight DESC, last_seen_at DESC);
            CREATE TABLE IF NOT EXISTS task_logs (
                task_id TEXT PRIMARY KEY,
                input_summary TEXT,
                output_summary TEXT,
                project_name TEXT,
                category TEXT,
                task_type TEXT,
                frameworks_json TEXT,
                success INTEGER,
                risk_level TEXT,
                recalled_entry_ids_json TEXT,
                created_at TEXT,
                finished_at TEXT,
                log_path TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_task_logs_lookup
                ON task_logs(category, task_type, created_at DESC);
            CREATE TABLE IF NOT EXISTS knowledge_usage_logs (
                id TEXT PRIMARY KEY,
                entry_id TEXT,
                task_id TEXT,
                project_name TEXT,
                frameworks_json TEXT,
                used_at TEXT,
                result TEXT,
                score REAL,
                notes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_usage_logs_entry ON knowledge_usage_logs(entry_id, used_at DESC);
            CREATE TABLE IF NOT EXISTS cleanup_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                finished_at TEXT,
                raw_archived_count INTEGER DEFAULT 0,
                raw_deleted_count INTEGER DEFAULT 0,
                task_archived_count INTEGER DEFAULT 0,
                merged_count INTEGER DEFAULT 0,
                deprecated_count INTEGER DEFAULT 0,
                errors_json TEXT
            );
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(DB_SCHEMA_VERSION),),
        )
        conn.commit()
    finally:
        conn.close()
    migrate_json_index_to_db()


def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def month_log_path(prefix: str = "tool-usage") -> Path:
    base = knowledge_root() / "logs" / "tool-usage"
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m")
    path = base / f"{prefix}-{stamp}.jsonl"
    if path.exists() and path.stat().st_size >= RAW_LOG_MAX_BYTES:
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = base / f"{prefix}-{stamp}-{suffix}.jsonl"
    return path


def tool_family(skill_name: str) -> str:
    return skill_name.split("_", 1)[0] if "_" in skill_name else skill_name


def target_type_from_params(skill_name: str, params: Dict[str, Any]) -> str:
    if "primitiveType" in params:
        return str(params.get("primitiveType") or "GameObject")
    if "componentType" in params:
        return str(params.get("componentType") or "Component")
    if "assetPath" in params:
        return "Asset"
    if skill_name.startswith("ui_"):
        return skill_name.replace("ui_create_", "").replace("ui_set_", "ui_")
    if skill_name.startswith("shader_"):
        return "Shader"
    if skill_name.startswith("material_"):
        return "Material"
    if skill_name.startswith("scene_"):
        return "Scene"
    return tool_family(skill_name)


def fingerprint_for(task: Dict[str, Any], skill_name: str = "", params: Optional[Dict[str, Any]] = None) -> str:
    params = params or {}
    frameworks = "+".join(sorted(task.get("frameworks") or ["Unity"]))
    parts = [
        task.get("category", "Debug"),
        task.get("task_type", "update"),
        frameworks,
        tool_family(skill_name) if skill_name else "task",
        skill_name or task.get("intent", "manual"),
        target_type_from_params(skill_name, params) if skill_name else "task",
    ]
    return ":".join(slugify(str(part), "unknown") for part in parts)


def row_to_entry(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    data["frameworks"] = json_loads(data.pop("frameworks_json", "[]"), [])
    data["is_core"] = bool(data.get("is_core"))
    return data


def upsert_entry_db(entry: Dict[str, Any]) -> None:
    frameworks = entry.get("frameworks", [])
    fingerprint = entry.get("fingerprint") or fingerprint_for(entry)
    conn = connect_db()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO knowledge_entries (
                id, title, summary, category, subcategory, task_type, frameworks_json,
                project_name, status, weight, usage_count, success_count, failure_count,
                last_used_at, md_path, summary_path, fingerprint, version_tag, is_core,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("id"),
                entry.get("title"),
                entry.get("summary"),
                entry.get("category"),
                entry.get("subcategory", ""),
                entry.get("task_type"),
                json_dumps(frameworks),
                entry.get("project_name"),
                entry.get("status", "active"),
                float(entry.get("weight", 0)),
                int(entry.get("usage_count", 0)),
                int(entry.get("success_count", 0)),
                int(entry.get("failure_count", 0)),
                entry.get("last_used_at"),
                entry.get("md_path"),
                entry.get("summary_path"),
                fingerprint,
                entry.get("version_tag", "v1"),
                1 if entry.get("is_core") else 0,
                entry.get("created_at", now_iso()),
                entry.get("updated_at", now_iso()),
            ),
        )
        conn.execute("DELETE FROM knowledge_tags WHERE entry_id = ?", (entry.get("id"),))
        for framework in frameworks:
            conn.execute(
                "INSERT OR IGNORE INTO knowledge_tags(entry_id, tag, tag_type) VALUES(?, ?, 'framework')",
                (entry.get("id"), framework),
            )
        for tag, tag_type in (
            (entry.get("category"), "category"),
            (entry.get("task_type"), "task_type"),
            (entry.get("status", "active"), "status"),
        ):
            if tag:
                conn.execute(
                    "INSERT OR IGNORE INTO knowledge_tags(entry_id, tag, tag_type) VALUES(?, ?, ?)",
                    (entry.get("id"), tag, tag_type),
                )
        conn.commit()
    finally:
        conn.close()


def migrate_json_index_to_db() -> None:
    index_path = knowledge_root() / "index" / "knowledge_index.json"
    index = read_json(index_path, {"entries": []})
    entries = index.get("entries", [])
    if not entries:
        return
    conn = connect_db()
    try:
        existing = conn.execute("SELECT COUNT(*) AS count FROM knowledge_entries").fetchone()["count"]
    finally:
        conn.close()
    if existing:
        return
    for entry in entries:
        upsert_entry_db(entry)


def infer_domain(text: str, skill_name: str = "") -> str:
    haystack = f"{skill_name} {text}".lower()
    rules = (
        ("HotUpdate", ("hybridclr", "hotupdate", "hot update", "addressables", "bundle", "aot")),
        ("UI", ("ui_", "canvas", "button", "panel", "textmeshpro", "tmp", "ugui", "layout")),
        ("Prefab", ("prefab", "variant", "override")),
        ("Scene", ("scene", "hierarchy", "gameobject", "camera", "light", "navmesh", "terrain")),
        ("Code", ("script", "compile", "asmdef", "c#")),
        ("Assets", ("asset", "texture", "model", "audio", "material", "shader")),
        ("Performance", ("optimize", "profiler", "memory", "batch", "overdraw", "lod")),
        ("Debug", ("debug", "console", "error", "exception", "validate", "missing")),
    )
    for domain, needles in rules:
        if any(needle in haystack for needle in needles):
            return domain
    return "Debug"


def infer_task_type(text: str, skill_name: str = "") -> str:
    haystack = f"{skill_name} {text}".lower()
    if "validate" in haystack:
        if "ui" in haystack:
            return "validate_ui"
        if "prefab" in haystack:
            return "validate_prefab"
        return "validate_scene"
    if "fix" in haystack or "missing" in haystack or "error" in haystack:
        if "reference" in haystack:
            return "fix_reference"
        if "compile" in haystack:
            return "fix_compile"
        if "hot" in haystack or "hybridclr" in haystack:
            return "fix_hotupdate"
        return "fix_load"
    if "optimize" in haystack or "profiler" in haystack:
        return "optimize_performance"
    if "create" in haystack or "instantiate" in haystack:
        if "scene" in haystack:
            return "create_scene"
        if "prefab" in haystack:
            return "create_prefab"
        if "ui" in haystack or "panel" in haystack:
            return "create_panel"
        return "create"
    if "move" in haystack or "reposition" in haystack or "transform" in haystack:
        return "reposition"
    if "refactor" in haystack:
        return "refactor"
    return "update"


def infer_frameworks(text: str, skill_name: str = "") -> List[str]:
    haystack = f"{skill_name} {text}".lower()
    frameworks = ["Unity"]
    checks = {
        "UGUI": ("ugui", "canvas", "recttransform", "ui_"),
        "TextMeshPro": ("textmeshpro", "tmp"),
        "C#": ("script", "c#", ".cs", "compile"),
        "HybridCLR": ("hybridclr", "hotupdate", "aot"),
        "Addressables": ("addressables", "assetbundle", "bundle"),
        "ZMUI": ("zmui",),
        "ZMGC": ("zmgc",),
        "BattleWorld": ("battleworld",),
        "Mobile": ("android", "ios", "mobile"),
        "PC": ("standalone", "pc"),
    }
    for framework, needles in checks.items():
        if any(needle in haystack for needle in needles):
            frameworks.append(framework)
    return list(dict.fromkeys(frameworks))


def score_entry(entry: Dict[str, Any], task: Dict[str, Any]) -> float:
    score = float(entry.get("weight", 0))
    if entry.get("task_type") == task.get("task_type"):
        score += 4
    if entry.get("category") == task.get("category"):
        score += 3
    entry_frameworks = set(entry.get("frameworks", []))
    task_frameworks = set(task.get("frameworks", []))
    score += len(entry_frameworks & task_frameworks) * 2
    if entry.get("is_core"):
        score += 1
    if entry.get("status") in ("archived", "deprecated"):
        score -= 5
    return score


def parse_task(
    intent: str,
    project_name: str = "CurrentProject",
    skill_name: str = "",
    frameworks: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    inferred_frameworks = infer_frameworks(intent, skill_name)
    if frameworks:
        inferred_frameworks.extend(frameworks)
    return {
        "target": infer_domain(intent, skill_name),
        "category": infer_domain(intent, skill_name),
        "action": infer_task_type(intent, skill_name).split("_", 1)[0],
        "task_type": infer_task_type(intent, skill_name),
        "intent": intent,
        "frameworks": list(dict.fromkeys(inferred_frameworks)),
        "constraints": [],
        "project": project_name,
        "priority": "high" if any(tag in inferred_frameworks for tag in ("HybridCLR", "Addressables", "ZMUI")) else "normal",
    }


def recall(task: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    init_knowledge_base()
    conn = connect_db()
    try:
        rows = conn.execute(
            """
            SELECT * FROM knowledge_entries
            WHERE status NOT IN ('deprecated', 'merged')
              AND (category = ? OR task_type = ? OR frameworks_json LIKE ?)
            ORDER BY weight DESC, updated_at DESC
            LIMIT ?
            """,
            (
                task.get("category"),
                task.get("task_type"),
                f"%{(task.get('frameworks') or ['Unity'])[0]}%",
                max(limit * 8, 20),
            ),
        ).fetchall()
    finally:
        conn.close()
    candidates = [row_to_entry(row) for row in rows]
    ranked = sorted(candidates, key=lambda entry: score_entry(entry, task), reverse=True)
    return ranked[:limit]


def update_usage_aggregate(skill_name: str, params: Dict[str, Any], result: Dict[str, Any], project_name: str) -> str:
    task = parse_task(json.dumps(params, ensure_ascii=False), project_name=project_name, skill_name=skill_name)
    fingerprint = fingerprint_for(task, skill_name, params)
    success = bool(result.get("success"))
    error = result.get("error") or result.get("message")
    conn = connect_db()
    try:
        row = conn.execute("SELECT * FROM usage_aggregates WHERE fingerprint = ?", (fingerprint,)).fetchone()
        if row:
            skill_names = set(json_loads(row["skill_names_json"], []))
            skill_names.add(skill_name)
            sample_errors = json_loads(row["sample_errors_json"], [])
            if error and error not in sample_errors:
                sample_errors = (sample_errors + [error])[-5:]
            samples = json_loads(row["sample_params_json"], [])
            if len(samples) < 5:
                samples.append(params)
            weight_delta = 1.0 if success else -1.5
            conn.execute(
                """
                UPDATE usage_aggregates
                SET skill_names_json = ?, total_count = total_count + 1,
                    success_count = success_count + ?, failure_count = failure_count + ?,
                    last_seen_at = ?, sample_errors_json = ?, sample_params_json = ?,
                    weight = weight + ?, updated_at = ?
                WHERE fingerprint = ?
                """,
                (
                    json_dumps(sorted(skill_names)),
                    1 if success else 0,
                    0 if success else 1,
                    now_iso(),
                    json_dumps(sample_errors),
                    json_dumps(samples),
                    weight_delta,
                    now_iso(),
                    fingerprint,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO usage_aggregates (
                    fingerprint, category, task_type, frameworks_json, tool_family,
                    skill_names_json, target_type, total_count, success_count, failure_count,
                    first_seen_at, last_seen_at, sample_task_ids_json, sample_errors_json,
                    sample_params_json, weight, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    fingerprint,
                    task.get("category"),
                    task.get("task_type"),
                    json_dumps(task.get("frameworks", [])),
                    tool_family(skill_name),
                    json_dumps([skill_name]),
                    target_type_from_params(skill_name, params),
                    1 if success else 0,
                    0 if success else 1,
                    now_iso(),
                    now_iso(),
                    json_dumps([]),
                    json_dumps([error] if error else []),
                    json_dumps([params]),
                    1.0 if success else -1.5,
                    now_iso(),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return fingerprint


def log_tool_call(skill_name: str, params: Dict[str, Any], result: Dict[str, Any], project_name: str = "CurrentProject") -> None:
    init_knowledge_base()
    task = parse_task(json.dumps(params, ensure_ascii=False), project_name=project_name, skill_name=skill_name)
    fingerprint = update_usage_aggregate(skill_name, params, result, project_name)
    append_jsonl(
        month_log_path(),
        {
            "id": str(uuid.uuid4()),
            "created_at": now_iso(),
            "fingerprint": fingerprint,
            "skill_name": skill_name,
            "task": task,
            "params": params,
            "success": bool(result.get("success")),
            "error": result.get("error") or result.get("message"),
        },
    )


def merge_similar_aggregates(threshold: float = 0.85) -> int:
    init_knowledge_base()
    conn = connect_db()
    merged = 0
    try:
        rows = conn.execute("SELECT * FROM usage_aggregates WHERE status = 'active'").fetchall()
        groups: Dict[Tuple[str, str, str, str], List[sqlite3.Row]] = {}
        for row in rows:
            key = (row["category"], row["task_type"], row["tool_family"], row["target_type"])
            groups.setdefault(key, []).append(row)
        for group_rows in groups.values():
            if len(group_rows) < 2:
                continue
            group_rows = sorted(group_rows, key=lambda row: (row["weight"], row["total_count"]), reverse=True)
            keeper = group_rows[0]
            keeper_frameworks = set(json_loads(keeper["frameworks_json"], []))
            for row in group_rows[1:]:
                frameworks = set(json_loads(row["frameworks_json"], []))
                union = keeper_frameworks | frameworks
                similarity = len(keeper_frameworks & frameworks) / max(len(union), 1)
                if similarity < threshold:
                    continue
                skill_names = sorted(set(json_loads(keeper["skill_names_json"], [])) | set(json_loads(row["skill_names_json"], [])))
                sample_errors = (json_loads(keeper["sample_errors_json"], []) + json_loads(row["sample_errors_json"], []))[-5:]
                sample_params = (json_loads(keeper["sample_params_json"], []) + json_loads(row["sample_params_json"], []))[-5:]
                conn.execute(
                    """
                    UPDATE usage_aggregates
                    SET frameworks_json = ?, skill_names_json = ?,
                        total_count = total_count + ?,
                        success_count = success_count + ?,
                        failure_count = failure_count + ?,
                        sample_errors_json = ?, sample_params_json = ?,
                        weight = weight + ?, last_seen_at = MAX(last_seen_at, ?),
                        updated_at = ?
                    WHERE fingerprint = ?
                    """,
                    (
                        json_dumps(sorted(union)),
                        json_dumps(skill_names),
                        row["total_count"],
                        row["success_count"],
                        row["failure_count"],
                        json_dumps(sample_errors),
                        json_dumps(sample_params),
                        row["weight"],
                        row["last_seen_at"],
                        now_iso(),
                        keeper["fingerprint"],
                    ),
                )
                conn.execute(
                    "UPDATE usage_aggregates SET status = 'merged', updated_at = ? WHERE fingerprint = ?",
                    (now_iso(), row["fingerprint"]),
                )
                keeper_frameworks = union
                merged += 1
        conn.commit()
    finally:
        conn.close()
    return merged


def cleanup_logs(raw_retention_days: int = 30, task_retention_days: int = 90) -> Dict[str, Any]:
    init_knowledge_base()
    started = now_iso()
    run_id = f"cleanup-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    raw_cutoff = datetime.now() - timedelta(days=raw_retention_days)
    task_cutoff = datetime.now() - timedelta(days=task_retention_days)
    root = knowledge_root()
    errors: List[str] = []
    raw_archived = 0
    raw_deleted = 0
    task_archived = 0

    for path in (root / "logs" / "tool-usage").glob("*.jsonl"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) >= raw_cutoff:
                continue
            gz_path = path.with_suffix(path.suffix + ".gz")
            with path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            path.unlink()
            raw_archived += 1
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    for path in (root / "logs" / "tool-usage").glob("*.jsonl.gz"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < raw_cutoff - timedelta(days=raw_retention_days):
                path.unlink()
                raw_deleted += 1
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    archive_dir = root / "logs" / "archive" / "task-logs"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for path in (root / "logs" / "task-logs").glob("task-*.json"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) >= task_cutoff:
                continue
            target = archive_dir / path.name
            if not target.exists():
                shutil.move(str(path), str(target))
                task_archived += 1
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    merged = merge_similar_aggregates()
    finished = now_iso()
    return {
        "run_id": run_id,
        "started_at": started,
        "finished_at": finished,
        "raw_archived_count": raw_archived,
        "raw_deleted_count": raw_deleted,
        "task_archived_count": task_archived,
        "merged_count": merged,
        "deprecated_count": 0,
        "errors": errors,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Unity self-evolving knowledge helper")
    parser.add_argument("--cleanup", action="store_true", help="Run log cleanup and aggregate compaction")
    parser.add_argument("--summary", action="store_true", help="Print top usage aggregates")
    parser.add_argument("--raw-retention-days", type=int, default=30)
    parser.add_argument("--task-retention-days", type=int, default=90)
    args = parser.parse_args()

    init_knowledge_base()
    if args.cleanup:
        payload = cleanup_logs(args.raw_retention_days, args.task_retention_days)
    elif args.summary:
        payload = {"success": True, "message": "Use SQLite queries to inspect aggregates."}
    else:
        payload = {"success": True, "knowledge_root": str(knowledge_root()), "db_path": str(db_path())}
    print(json.dumps(payload, ensure_ascii=False, indent=2))

