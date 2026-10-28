# elabftw-assistant

An MCP server that lets an AI assistant (Claude Desktop, Claude Code, or any other MCP client) work in an eLabFTW notebook through its API v2.

## Tools

| Tool | What it does |
|---|---|
| `search_entries` | Find experiments or resources by text (most recent first) |
| `get_entry` | Read an entry: body, extra fields, steps, links, attachments |
| `list_templates` / `list_resource_categories` | Discover templates and resource categories |
| `create_experiment` | New experiment, optionally from a template, with tags |
| `create_item` | New resource (sample, reagent...) in a category |
| `append_note` | Append a timestamped note; existing text is never modified |
| `set_extra_fields` | Fill structured fields, e.g. `{"Yield": "4.2"}` |
| `attach_file` | Upload a photo or instrument file |
| `add_step` / `complete_step` | Add protocol steps or tick them off |
| `link_item` | Link a resource to an experiment |

There are deliberately no tools for deleting, overwriting the body, locking, signing or timestamping entries.

## Guides

- [Add the assistant to Claude Code](docs/claude-code-setup.md), step by step for colleagues
- [Run eLabFTW on your local network](docs/elabftw-lan-server.md), for whoever hosts the server

## Setup

1. In eLabFTW: user menu → **Settings** → **API keys**. Create a key with **Read Only** access first, then switch to **Read/Write** once you trust it.
2. Install [uv](https://docs.astral.sh/uv/), then run `uv sync` in this directory.
3. Register the server with your client.

**Claude Code**

```sh
claude mcp add elabftw \
  -e ELABFTW_URL=https://your-elab.example.org \
  -e ELABFTW_API_KEY=your-key \
  -- uv run --directory /home/peeter/elabftw-assistant elabftw_mcp.py
```

**Claude Desktop**: add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "elabftw": {
      "command": "uv",
      "args": ["run", "--directory", "/home/peeter/elabftw-assistant", "elabftw_mcp.py"],
      "env": {
        "ELABFTW_URL": "https://your-elab.example.org",
        "ELABFTW_API_KEY": "your-key"
      }
    }
  }
}
```

### Environment variables

| Variable | Default | |
|---|---|---|
| `ELABFTW_URL` | required | Base URL of the instance |
| `ELABFTW_API_KEY` | required | API key |
| `ELABFTW_VERIFY_SSL` | `true` | Path to a CA file (PEM) for internally signed certificates, or `false` for throwaway test instances |
| `ELABFTW_READ_ONLY` | `false` | `true` disables every writing tool, regardless of key permissions |

## Example

> "I'm starting a miniprep of the pUC19 culture, use the miniprep protocol."
> *(photo of gel)* "Here's the gel, lane 3 looks good. Mark the elution step done and note the yield was 4.2 µg/µl."

The assistant searches for the template and the pUC19 resource, creates the experiment, links the resource, attaches the photo, ticks the step, appends the note and fills the `Yield` field.

## Local test instance

`dev/docker-compose.yml` runs a throwaway eLabFTW 5.6.15 at https://localhost:3149. Its data lives in tmpfs and is lost on `down`.

```sh
docker compose -p elab-assistant -f dev/docker-compose.yml up -d
docker exec elab-assistant-web bin/init db:populate /elabftw/src/tools/populate-config.yml.dist -y
```

Log in as `toto@yopmail.com` / `totototototo` (team Alpha). The API key is `apiKey4Test`. Use `ELABFTW_VERIFY_SSL=false`, because the certificate is self-signed. Stop it with `docker compose -p elab-assistant -f dev/docker-compose.yml down`.

## Tests

```sh
uv run pytest
```

The tests run every tool against a fake API and check the exact requests sent. They do not replace a test against a real instance.

## Notes

- Every change is recorded in eLabFTW as the owner of the API key. Body edits create revisions.
- `attach_file` reads files on the machine where the server runs. Photos taken on a phone need to reach that machine first.
