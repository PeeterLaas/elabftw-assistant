"""MCP server exposing a small, lab-oriented slice of the eLabFTW API v2.

Configuration (environment variables):
  ELABFTW_URL        base URL of the instance, e.g. https://elab.example.org
  ELABFTW_API_KEY    API key (create one under User panel > API keys)
  ELABFTW_VERIFY_SSL "true" (default), "false" to skip certificate checks, or the
                     path to a CA certificate (PEM) for internally signed certificates
  ELABFTW_READ_ONLY  "true" to disable every tool that writes (default: false)
"""

from __future__ import annotations

import html
import json
import os
import re
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

EntityType = Literal["experiments", "items"]

READ_ONLY = os.environ.get("ELABFTW_READ_ONLY", "false").lower() == "true"
BODY_PREVIEW_CHARS = 4000

mcp = MCPServer(
    "elabftw",
    instructions=(
        "Tools for a lab electronic notebook (eLabFTW). 'experiments' are lab "
        "notebook entries; 'items' are resources such as samples, reagents, "
        "plasmids or equipment. Before writing, find the right entry with "
        "search_entries/get_entry and ask the user if more than one entry "
        "could match. Prefer append_note over rewriting existing text."
    ),
)

_READ = ToolAnnotations(readOnlyHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)


def _verify() -> bool | ssl.SSLContext:
    value = os.environ.get("ELABFTW_VERIFY_SSL", "true")
    if value.lower() in ("true", ""):
        return True
    if value.lower() == "false":
        return False
    return ssl.create_default_context(cafile=os.path.expanduser(value))


def _client() -> httpx.Client:
    url = os.environ.get("ELABFTW_URL")
    key = os.environ.get("ELABFTW_API_KEY")
    if not url or not key:
        raise ToolError("ELABFTW_URL and ELABFTW_API_KEY must be set")
    return httpx.Client(
        base_url=url.rstrip("/") + "/api/v2",
        headers={"Authorization": key},
        verify=_verify(),
        timeout=30,
    )


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    with _client() as client:
        res = client.request(method, path, **kwargs)
    if res.is_error:
        raise ToolError(f"eLabFTW {method} {path} failed ({res.status_code}): {res.text[:500]}")
    return res


def _id_from_location(res: httpx.Response) -> int:
    """Created resources are returned as a Location header ending in the new id."""
    match = re.search(r"/(\d+)/?$", res.headers.get("location", ""))
    if not match:
        raise ToolError("eLabFTW did not return the id of the created entry")
    return int(match.group(1))


def _check_writable() -> None:
    if READ_ONLY:
        raise ToolError("Server is in read-only mode (ELABFTW_READ_ONLY=true)")


def _summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        k: entry.get(k)
        for k in ("id", "title", "date", "category_title", "status_title", "tags", "fullname", "modified_at", "locked")
    }


# --- Reading ---------------------------------------------------------------


@mcp.tool(annotations=_READ)
def search_entries(entity_type: EntityType, query: str = "", limit: int = 10) -> list[dict[str, Any]]:
    """Search experiments or items (resources) by text in title, body or elabid.

    An empty query returns the most recently modified entries.
    """
    params: dict[str, Any] = {"limit": limit, "order": "lastchange", "sort": "desc"}
    if query:
        params["q"] = query
    return [_summary(e) for e in _request("GET", f"/{entity_type}", params=params).json()]


@mcp.tool(annotations=_READ)
def get_entry(entity_type: EntityType, id: int) -> dict[str, Any]:
    """Read one experiment or item: body text, extra fields, steps, links and attachment names."""
    entry = _request("GET", f"/{entity_type}/{id}").json()
    body = entry.get("body") or ""
    return {
        **_summary(entry),
        "body": body[:BODY_PREVIEW_CHARS] + ("\n[...truncated]" if len(body) > BODY_PREVIEW_CHARS else ""),
        "metadata": entry.get("metadata"),
        "steps": [
            {"id": s["id"], "body": s["body"], "finished": bool(s.get("finished"))}
            for s in entry.get("steps") or []
        ],
        "items_links": [{"id": l["entityid"], "title": l["title"]} for l in entry.get("items_links") or []],
        "experiments_links": [
            {"id": l["entityid"], "title": l["title"]} for l in entry.get("experiments_links") or []
        ],
        "uploads": [{"id": u["id"], "name": u["real_name"], "comment": u.get("comment")} for u in entry.get("uploads") or []],
    }


@mcp.tool(annotations=_READ)
def list_templates() -> list[dict[str, Any]]:
    """List experiment templates (protocols) available to the user."""
    return [{"id": t["id"], "title": t["title"]} for t in _request("GET", "/experiments_templates").json()]


@mcp.tool(annotations=_READ)
def list_resource_categories() -> list[dict[str, Any]]:
    """List resource types (e.g. Antibody, Plasmid, Microscope), needed to create items.

    Each type is a template carrying default text and extra fields for new items.
    """
    return [{"id": t["id"], "title": t["title"]} for t in _request("GET", "/items_types").json()]


# --- Writing ---------------------------------------------------------------


@mcp.tool(annotations=_WRITE)
def create_experiment(title: str, template_id: int = -1, tags: list[str] | None = None) -> dict[str, Any]:
    """Create a new experiment. Use template_id from list_templates, or -1 for an empty body."""
    _check_writable()
    new_id = _id_from_location(_request("POST", "/experiments", json={"title": title, "template": template_id}))
    # tags in the creation payload are ignored when a template is used, so add them afterwards
    for tag in tags or []:
        _request("POST", f"/experiments/{new_id}/tags", json={"tag": tag})
    return {"id": new_id, "title": title}


@mcp.tool(annotations=_WRITE)
def create_item(category_id: int, title: str, description: str = "") -> dict[str, Any]:
    """Create a new resource (sample, reagent...) in a category from list_resource_categories.

    The category's default text and extra fields are copied into the new item.
    """
    _check_writable()
    # categories are resource templates: creating from one copies its body and extra fields
    new_id = _id_from_location(_request("POST", "/items", json={"title": title, "template": category_id}))
    if description:
        _request("PATCH", f"/items/{new_id}", json={"bodyappend": f"<p>{html.escape(description)}</p>"})
    return {"id": new_id, "title": title}


@mcp.tool(annotations=_WRITE)
def append_note(entity_type: EntityType, id: int, text: str) -> str:
    """Append a timestamped note to the end of an entry's body. Existing text is never changed."""
    _check_writable()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines() if line.strip())
    _request("PATCH", f"/{entity_type}/{id}", json={"bodyappend": f"<p><strong>{stamp}</strong></p>{paragraphs}"})
    return f"Note appended to {entity_type} {id}"


@mcp.tool(annotations=_WRITE)
def set_extra_fields(entity_type: EntityType, id: int, values: dict[str, str]) -> str:
    """Set values of extra fields (structured metadata), e.g. {"Temperature": "37", "Yield": "4.2"}.

    Existing fields keep their type and units; unknown field names are added.
    """
    _check_writable()
    metadata = {"extra_fields": {name: {"value": value} for name, value in values.items()}}
    # the API casts every patched value to a string, so the JSON must be pre-encoded
    _request("PATCH", f"/{entity_type}/{id}", json={"metadatamerge": json.dumps(metadata)})
    return f"Updated {len(values)} field(s) on {entity_type} {id}"


@mcp.tool(annotations=_WRITE)
def attach_file(entity_type: EntityType, id: int, file_path: str, comment: str = "") -> str:
    """Attach a local file (photo, instrument output...) to an entry."""
    _check_writable()
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise ToolError(f"File not found: {path}")
    with path.open("rb") as fh:
        _request("POST", f"/{entity_type}/{id}/uploads", files={"file": (path.name, fh)}, data={"comment": comment})
    return f"Attached {path.name} to {entity_type} {id}"


@mcp.tool(annotations=_WRITE)
def add_step(entity_type: EntityType, id: int, body: str) -> dict[str, Any]:
    """Add a step (to-do in the protocol) to an entry."""
    _check_writable()
    step_id = _id_from_location(_request("POST", f"/{entity_type}/{id}/steps", json={"body": body}))
    return {"id": step_id, "body": body}


@mcp.tool(annotations=_WRITE)
def complete_step(entity_type: EntityType, id: int, step_id: int) -> str:
    """Mark a step as done. Does nothing if it is already done."""
    _check_writable()
    steps = _request("GET", f"/{entity_type}/{id}/steps").json()
    step = next((s for s in steps if s["id"] == step_id), None)
    if step is None:
        raise ToolError(f"Step {step_id} not found on {entity_type} {id}")
    if step.get("finished"):
        return f"Step '{step['body']}' was already done"
    # "finish" toggles, hence the check above
    _request("PATCH", f"/{entity_type}/{id}/steps/{step_id}", json={"action": "finish"})
    return f"Step '{step['body']}' marked as done"


@mcp.tool(annotations=_WRITE)
def link_item(entity_type: EntityType, id: int, item_id: int) -> str:
    """Link a resource (sample, reagent, equipment) to an experiment or another item."""
    _check_writable()
    _request("POST", f"/{entity_type}/{id}/items_links/{item_id}", json={"action": "create"})
    return f"Linked item {item_id} to {entity_type} {id}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
