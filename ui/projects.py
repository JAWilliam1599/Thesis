"""Project registry for the multi-project / multi-workflow UI.

Projects are persisted in ``logs/projects.json``. Each project selects a
workflow and owns a separate artifact directory so gate reports, approvals,
rejections, and monitoring history never mix between projects:

- ``default`` project  -> legacy flat ``logs/`` layout (backward compatible)
- any other project    -> ``logs/projects/<id>/``

Workflows:
- ``cdk``    — code generation + regen loop + gate + deploy (generated_cdk).
- ``hybrid`` — bring-your-own CDK + Ansible dirs; gate + deploy per branch,
  no code generation.

The active project's logs root is exported to pipeline subprocesses via the
``SYSSECOPS_LOG_DIR`` environment variable (see ui/pipeline_runner.py).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui import config

DEFAULT_PROJECT_ID = "default"
WORKFLOWS = ("cdk", "hybrid")

_DEFAULT_PROJECT: dict[str, Any] = {
    "id": DEFAULT_PROJECT_ID,
    "name": "Default (CDK)",
    "workflow": "cdk",
    "cdk_path": "generated_cdk",
    "ansible_path": "",
    "playbook": "",
    "inventory": "",
    "target_host": "",
    "created_at": None,
}


def _registry_path() -> Path:
    return config.LOGS_DIR / "projects.json"


def load_registry() -> dict[str, Any]:
    """Load the registry, always including the built-in default project."""
    registry: dict[str, Any] = {"projects": [], "active_id": DEFAULT_PROJECT_ID}
    path = _registry_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                registry["projects"] = [
                    p for p in data.get("projects", [])
                    if isinstance(p, dict) and p.get("id") and p["id"] != DEFAULT_PROJECT_ID
                ]
                registry["active_id"] = data.get("active_id") or DEFAULT_PROJECT_ID
        except (json.JSONDecodeError, OSError):
            pass
    registry["projects"] = [dict(_DEFAULT_PROJECT)] + registry["projects"]
    if registry["active_id"] not in {p["id"] for p in registry["projects"]}:
        registry["active_id"] = DEFAULT_PROJECT_ID
    return registry


def _save_registry(registry: dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    persisted = {
        "projects": [p for p in registry["projects"] if p["id"] != DEFAULT_PROJECT_ID],
        "active_id": registry.get("active_id", DEFAULT_PROJECT_ID),
    }
    path.write_text(json.dumps(persisted, indent=2), encoding="utf-8")


def list_projects() -> list[dict[str, Any]]:
    return load_registry()["projects"]


def get_project(project_id: str) -> dict[str, Any] | None:
    for project in list_projects():
        if project["id"] == project_id:
            return project
    return None


def get_active_project() -> dict[str, Any]:
    registry = load_registry()
    active_id = registry["active_id"]
    for project in registry["projects"]:
        if project["id"] == active_id:
            return project
    return registry["projects"][0]


def set_active_project(project_id: str) -> None:
    registry = load_registry()
    if project_id in {p["id"] for p in registry["projects"]}:
        registry["active_id"] = project_id
        _save_registry(registry)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "project"


def create_project(
    name: str,
    workflow: str,
    *,
    cdk_path: str = "",
    ansible_path: str = "",
    playbook: str = "",
    inventory: str = "",
    target_host: str = "",
) -> dict[str, Any]:
    """Create, persist, and activate a new project. Returns the project dict."""
    if workflow not in WORKFLOWS:
        raise ValueError(f"Unknown workflow: {workflow!r}")
    registry = load_registry()
    existing_ids = {p["id"] for p in registry["projects"]}
    base = _slugify(name)
    project_id = base
    counter = 2
    while project_id in existing_ids:
        project_id = f"{base}-{counter}"
        counter += 1
    project = {
        "id": project_id,
        "name": name.strip() or project_id,
        "workflow": workflow,
        "cdk_path": cdk_path.strip(),
        "ansible_path": ansible_path.strip(),
        "playbook": playbook.strip(),
        "inventory": inventory.strip(),
        "target_host": target_host.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    registry["projects"].append(project)
    registry["active_id"] = project_id
    _save_registry(registry)
    logs_root(project).mkdir(parents=True, exist_ok=True)
    return project


def update_project(project_id: str, **fields: Any) -> None:
    """Update stored fields of a non-default project."""
    if project_id == DEFAULT_PROJECT_ID:
        return
    registry = load_registry()
    for project in registry["projects"]:
        if project["id"] == project_id:
            for key, value in fields.items():
                if key in project and key not in ("id", "created_at"):
                    project[key] = value
            break
    _save_registry(registry)


def delete_project(project_id: str) -> None:
    """Remove a project from the registry (its logs directory is kept)."""
    if project_id == DEFAULT_PROJECT_ID:
        return
    registry = load_registry()
    registry["projects"] = [p for p in registry["projects"] if p["id"] != project_id]
    if registry["active_id"] == project_id:
        registry["active_id"] = DEFAULT_PROJECT_ID
    _save_registry(registry)


def logs_root(project: dict[str, Any]) -> Path:
    """Artifact root for a project (legacy flat logs/ for the default project)."""
    if project.get("id", DEFAULT_PROJECT_ID) == DEFAULT_PROJECT_ID:
        return config.LOGS_DIR
    return config.LOGS_DIR / "projects" / project["id"]
