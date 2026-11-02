"""Exercises every tool through MCP against a fake eLabFTW that records requests."""

import asyncio
import json

import httpx
import pytest

import elabftw_mcp

STEPS = [{"id": 7, "body": "Spin down cells", "finished": 0}]


def fake_api(request: httpx.Request) -> httpx.Response:
    path, method = request.url.path.removeprefix("/api/v2"), request.method
    fake_api.calls.append((method, path, request))
    if method == "GET" and path == "/teams/current/resources_categories":
        return httpx.Response(200, json=[
            {"id": 2, "title": "Antibody", "is_current_team": 1},
            {"id": 3, "title": "Empty", "is_current_team": 1},
            {"id": 9, "title": "Shared by another team", "is_current_team": 0},
        ])
    if method == "GET" and path == "/items_types":
        return httpx.Response(200, json=[{"id": 7, "title": "Antibody stock", "category": 2}, {"id": 8, "title": "Other", "category": None}])
    if method == "POST" and path == "/teams/current/resources_categories":
        return httpx.Response(201, headers={"location": f"https://elab.test/api/v2{path}/5"})
    if method == "POST" and path in ("/experiments", "/items", "/items_types"):
        return httpx.Response(201, headers={"location": f"https://elab.test/api/v2{path}/42"})
    if method == "POST" and path.endswith("/steps"):
        return httpx.Response(201, headers={"location": "https://elab.test/api/v2/experiments/1/steps/9"})
    if method == "GET" and path.endswith("/steps"):
        return httpx.Response(200, json=STEPS)
    if method == "GET" and path == "/experiments/1":
        return httpx.Response(200, json={
            "id": 1, "title": "Miniprep", "body": "<p>x</p>", "metadata": None,
            "steps": STEPS, "items_links": [{"entityid": 3, "title": "pUC19"}],
            "experiments_links": [], "uploads": [{"id": 5, "real_name": "gel.png", "comment": ""}],
        })
    if method == "GET" and path == "/experiments":
        return httpx.Response(200, json=[{"id": 1, "title": "Miniprep", "body": "long"}])
    return httpx.Response(200 if method == "GET" else 204, json=[] if method == "GET" else None)


@pytest.fixture(autouse=True)
def mock_api(monkeypatch):
    fake_api.calls = []
    monkeypatch.setattr(elabftw_mcp, "_client", lambda: httpx.Client(
        base_url="https://elab.test/api/v2", transport=httpx.MockTransport(fake_api)))
    monkeypatch.setattr(elabftw_mcp, "READ_ONLY", False)
    return fake_api.calls


def call(name, **args):
    return asyncio.run(elabftw_mcp.mcp.call_tool(name, args))


def body(request):
    return json.loads(request.content)


def test_all_tools_registered():
    names = {t.name for t in asyncio.run(elabftw_mcp.mcp.list_tools())}
    assert names == {
        "search_entries", "get_entry", "list_templates", "list_resource_categories", "create_experiment",
        "create_item", "append_note", "set_extra_fields", "attach_file", "add_step", "complete_step", "link_item",
        "create_resource_category",
    }


def test_search_and_get(mock_api):
    call("search_entries", entity_type="experiments", query="miniprep")
    assert mock_api[0][2].url.params["q"] == "miniprep"
    result = str(call("get_entry", entity_type="experiments", id=1))
    assert "pUC19" in result and "gel.png" in result


def test_create_experiment_from_template_adds_tags_separately(mock_api):
    call("create_experiment", title="Miniprep", template_id=3, tags=["plasmid", "dna"])
    assert body(mock_api[0][2]) == {"title": "Miniprep", "template": 3}
    assert [(m, p, body(r)) for m, p, r in mock_api[1:]] == [
        ("POST", "/experiments/42/tags", {"tag": "plasmid"}),
        ("POST", "/experiments/42/tags", {"tag": "dna"}),
    ]


def posts(calls):
    return [(p, body(r)) for m, p, r in calls if m == "POST"]


def test_list_categories_keeps_own_team_and_shows_templates(mock_api):
    out = call("list_resource_categories").structured_content["result"]
    assert [(c["id"], [x["id"] for x in c["templates"]]) for c in out] == [(2, [7]), (3, [])]


def test_create_item_starts_from_the_categorys_template(mock_api):
    out = call("create_item", category_id=2, title="pUC19 stock", description="from Alice").structured_content
    assert posts(mock_api) == [("/items", {"title": "pUC19 stock", "template": 7})]
    assert [body(r) for m, p, r in mock_api if m == "PATCH"] == [{"bodyappend": "<p>from Alice</p>"}]
    assert out["category"] == "Antibody" and out["template_id"] == 7


def test_create_item_without_template_sets_category(mock_api):
    call("create_item", category_id=3, title="Thing")
    assert posts(mock_api) == [("/items", {"title": "Thing", "category": 3})]


def test_create_item_with_other_template_still_sets_category(mock_api):
    call("create_item", category_id=2, title="Thing", template_id=8)
    assert posts(mock_api) == [("/items", {"title": "Thing", "template": 8})]
    assert [body(r) for m, p, r in mock_api if m == "PATCH"] == [{"category": 2}]


@pytest.mark.parametrize("args, message", [
    ({"category_id": 9, "title": "X"}, "not in your team"),
    ({"category_id": 2, "title": "X", "template_id": 99}, "not found"),
])
def test_create_item_refuses_bad_ids(mock_api, args, message):
    with pytest.raises(Exception, match=message):
        call("create_item", **args)
    assert not posts(mock_api)


def test_search_can_include_other_teams(mock_api):
    call("search_entries", entity_type="items", query="MinION", include_other_teams=True)
    assert mock_api[-1][2].url.params["scope"] == "3"
    call("search_entries", entity_type="items", query="MinION")
    assert "scope" not in mock_api[-1][2].url.params


def test_append_note_escapes_and_appends(mock_api):
    call("append_note", entity_type="experiments", id=1, text="OD600 < 0.5\nlooks fine")
    sent = body(mock_api[0][2])["bodyappend"]
    assert "<p>OD600 &lt; 0.5</p><p>looks fine</p>" in sent


def test_extra_fields_sent_as_json_string(mock_api):
    call("set_extra_fields", entity_type="items", id=3, values={"Concentration": "120"})
    sent = body(mock_api[0][2])["metadatamerge"]
    assert json.loads(sent) == {"extra_fields": {"Concentration": {"value": "120"}}}


def test_attach_file(mock_api, tmp_path):
    photo = tmp_path / "gel.png"
    photo.write_bytes(b"\x89PNG")
    call("attach_file", entity_type="experiments", id=1, file_path=str(photo), comment="1% agarose")
    request = mock_api[0][2]
    assert request.url.path.endswith("/experiments/1/uploads")
    assert b'filename="gel.png"' in request.content and b"1% agarose" in request.content


def test_complete_step_only_toggles_unfinished(mock_api):
    call("complete_step", entity_type="experiments", id=1, step_id=7)
    assert body(mock_api[1][2]) == {"action": "finish"}
    STEPS[0]["finished"] = 1
    try:
        mock_api.clear()
        call("complete_step", entity_type="experiments", id=1, step_id=7)
        assert [m for m, _, _ in mock_api] == ["GET"]
    finally:
        STEPS[0]["finished"] = 0


def test_link_item(mock_api):
    call("link_item", entity_type="experiments", id=1, item_id=3)
    assert mock_api[0][1] == "/experiments/1/items_links/3"


def test_read_only_blocks_writes(mock_api, monkeypatch):
    monkeypatch.setattr(elabftw_mcp, "READ_ONLY", True)
    with pytest.raises(Exception, match="read-only"):
        call("append_note", entity_type="experiments", id=1, text="x")
    assert mock_api == []


def test_verify_ssl_values(monkeypatch, tmp_path):
    monkeypatch.delenv("ELABFTW_VERIFY_SSL", raising=False)
    assert elabftw_mcp._verify() is True
    monkeypatch.setenv("ELABFTW_VERIFY_SSL", "false")
    assert elabftw_mcp._verify() is False
    monkeypatch.setenv("ELABFTW_VERIFY_SSL", str(tmp_path / "missing.pem"))
    with pytest.raises(FileNotFoundError):
        elabftw_mcp._verify()


def test_create_resource_category_makes_category_and_template(mock_api):
    out = call("create_resource_category", title="Instruments", description="Lab equipment", fields=[
        {"name": "Serial number"},
        {"name": "Last service", "type": "date"},
        {"name": "Status", "type": "select", "options": ["In use", "Broken"]},
        {"name": "Max temperature", "type": "number", "unit": "°C"},
    ]).structured_content
    created = posts(mock_api)
    assert created[0] == ("/teams/current/resources_categories", {"name": "Instruments"})
    path, sent = created[1]
    fields = json.loads(sent["metadata"])["extra_fields"]
    assert path == "/items_types" and sent["title"] == "Instruments" and sent["category"] == 5 and "Lab equipment" in sent["body"]
    assert list(fields) == ["Serial number", "Last service", "Status", "Max temperature"]
    assert fields["Status"]["options"] == ["In use", "Broken"] and fields["Max temperature"]["unit"] == "°C"
    assert fields["Last service"]["type"] == "date" and fields["Serial number"]["position"] == 1
    assert out["id"] == 5 and out["template_id"] == 42


def test_create_resource_category_without_fields_makes_no_template(mock_api):
    out = call("create_resource_category", title="Plain").structured_content
    assert [p for p, _ in posts(mock_api)] == ["/teams/current/resources_categories"] and out["template_id"] is None


def test_another_teams_category_name_can_be_reused(mock_api):
    call("create_resource_category", title="Shared by another team")
    assert posts(mock_api)


@pytest.mark.parametrize("args, message", [
    ({"title": "antibody"}, "already exists"),
    ({"title": "X", "fields": [{"name": "A", "type": "colour"}]}, "type must be one of"),
    ({"title": "X", "fields": [{"name": "A", "type": "select"}]}, "needs options"),
    ({"title": "X", "fields": [{"name": "A"}, {"name": "A"}]}, "listed twice"),
])
def test_create_resource_category_refuses_bad_input(mock_api, args, message):
    with pytest.raises(Exception, match=message):
        call("create_resource_category", **args)
    assert not [c for c in mock_api if c[0] == "POST"]
