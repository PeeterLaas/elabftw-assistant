# Add the eLabFTW assistant to Claude Code

These steps connect your Claude Code to your lab's eLabFTW. Afterwards you can ask Claude to find experiments, create entries, add notes, attach photos and tick off protocol steps in eLabFTW.

Expect about 10 minutes. You need nothing beyond a browser and a terminal.

## Before you start

You need:

- **Claude Code**, installed and logged in. Check with `claude --version`.
- **An eLabFTW account** that you can log in to in your browser.
- **The address of your eLabFTW**. Ask whoever runs it if you're unsure.
- **The `elabftw-assistant` folder** (see step 1).

## Step 1: Get the assistant

Put the `elabftw-assistant` folder somewhere permanent, for example `~/elabftw-assistant`. Claude Code runs it from that location every time, so don't use a temporary or Downloads folder.

```sh
git clone <repository-url> ~/elabftw-assistant
```

If you received the folder as a zip, unpack it to `~/elabftw-assistant` instead.

## Step 2: Install uv and the dependencies

The assistant is a small Python program. [uv](https://docs.astral.sh/uv/) installs the right Python version and the dependencies for it. You don't need to install Python yourself.

macOS / Linux:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Open a new terminal so `uv` is on your PATH, then:

```sh
cd ~/elabftw-assistant
uv sync
```

`uv sync` ends without errors when it's done.

## Step 3: Find your `ELABFTW_URL`

This is the address of your eLabFTW, the same one you use in the browser, with nothing after the host name and port.

1. Log in to eLabFTW in your browser.
2. Copy the address from the address bar.
3. Keep only `https://`, the host name, and the port if there is one. Remove everything after that.

| Address bar shows | `ELABFTW_URL` |
|---|---|
| `https://elab.lab.example.org/experiments.php?mode=view&id=12` | `https://elab.lab.example.org` |
| `https://192.168.1.50/login.php` | `https://192.168.1.50` |
| `https://elab-server:3148/dashboard.php` | `https://elab-server:3148` |

Don't add `/api/v2`, because the assistant adds it itself. Don't add a trailing `/` either.

## Step 4: Create your `ELABFTW_API_KEY`

The API key lets the assistant act **as you**. Everything it creates or changes appears in eLabFTW under your name, so every person needs their own key. Never share yours.

1. In eLabFTW, switch to the team you work in if you belong to several. A key only works in the team that was active when it was created.
2. Open your user menu (top right) → **Settings** → **API keys** tab. The direct link is `https://<your eLabFTW>/ucp.php?tab=3`.
3. Under **Create new key**:
   - **Name**: something recognizable, e.g. `claude-code laptop`.
   - **Permissions**: pick **Read Only** for now. You'll switch to Read/Write in step 9.
4. Click **Generate an API Key**.
5. **Copy the key now.** eLabFTW only shows it once. If you lose it, delete the key on the same page and create a new one.

The key looks like `3-a1b2c3...`.

## Step 5: Decide `ELABFTW_VERIFY_SSL`

This setting tells the assistant whether to trust eLabFTW's HTTPS certificate. Open your eLabFTW address in the browser and see what happens:

| What you see | Set `ELABFTW_VERIFY_SSL` to |
|---|---|
| Padlock, no warning | Leave it out (the default is `true`) |
| Warning, and your IT gave you an organization CA certificate (`.pem`/`.crt`) | The path to that file, e.g. `~/certs/lab-ca.pem` |
| Warning on a **test** instance with a self-signed certificate | `false` (test instances only, see below) |

`false` turns off certificate checking. Anyone on the network could then pretend to be your eLabFTW and capture your API key. Use it only for a test instance on your own machine, never with your real lab data.

## Step 6: Test the connection

Before involving Claude, check that the address and key work. Replace the two values with yours:

macOS / Linux:

```sh
curl -H "Authorization: YOUR_API_KEY" https://elab.lab.example.org/api/v2/users/me
```

Windows (PowerShell):

```powershell
curl.exe -H "Authorization: YOUR_API_KEY" https://elab.lab.example.org/api/v2/users/me
```

If you set `ELABFTW_VERIFY_SSL` to a CA file, add `--cacert path/to/lab-ca.pem`. If you set it to `false`, add `-k`.

| You get | Meaning |
|---|---|
| A block of JSON with your name in it | Everything works, go on to step 7 |
| `"code":401` | The key is wrong or was deleted. Redo step 4 |
| `Could not resolve host` / `Connection refused` / timeout | Wrong address, or you're not on the lab network/VPN |
| `SSL certificate problem` | See step 5 |

## Step 7: Add the assistant to Claude Code

Run this once, with your own values. `--scope user` makes the assistant available in all your Claude Code sessions.

macOS / Linux:

```sh
claude mcp add --scope user elabftw \
  -e ELABFTW_URL=https://elab.lab.example.org \
  -e ELABFTW_API_KEY=YOUR_API_KEY \
  -- uv run --directory ~/elabftw-assistant elabftw_mcp.py
```

Windows (PowerShell). Use the full path to the folder:

```powershell
claude mcp add --scope user elabftw `
  -e ELABFTW_URL=https://elab.lab.example.org `
  -e ELABFTW_API_KEY=YOUR_API_KEY `
  -- uv run --directory C:\Users\you\elabftw-assistant elabftw_mcp.py
```

If step 5 gave you a value, add `-e ELABFTW_VERIFY_SSL=...` next to the other two `-e` options.

Claude Code saves this in `~/.claude.json`, which stays on your computer. Don't put your key in a project's `.mcp.json`, because that file is usually committed to git.

## Step 8: Check that it works

1. Run `claude mcp list`. It should show `elabftw: ... ✔ Connected`.
2. Start a **new** Claude Code session. Sessions that were already open don't pick up new servers.
3. Type `/mcp`. `elabftw` should be listed with its tools.
4. Ask something read-only, for example:

   > List the experiment templates in eLabFTW.

   > What were my last five experiments about?

Claude asks your permission the first time it uses each tool.

## Step 9: Allow writing

Once you trust it, give the assistant a key that can write:

1. In eLabFTW → **Settings** → **API keys**, create a new key with **Read/Write**. Delete the old read-only key.
2. Replace the key in Claude Code:

   ```sh
   claude mcp remove elabftw -s user
   ```

   Then run the command from step 7 again with the new key.

Then try it out:

> Start a new experiment "Miniprep pUC19" from the miniprep template, link the pUC19 glycerol stock, and attach ~/Pictures/gel.png with the comment "1% agarose, lane 3".

Keep eLabFTW open in the browser to watch the changes come in.

## What the assistant can and can't do

| Can | Can't |
|---|---|
| Search and read experiments and resources | Delete anything |
| Create experiments (optionally from a template) and resources | Overwrite or edit existing text |
| Append timestamped notes | Lock, sign or timestamp entries |
| Fill extra fields, add and complete steps | Change permissions |
| Attach files from **your** computer, link resources | |

Every change is recorded in eLabFTW under your name, and body edits keep a revision history. To make the assistant strictly read-only regardless of the key, add `-e ELABFTW_READ_ONLY=true` in step 7.

## Troubleshooting

| Problem | Fix |
|---|---|
| `claude mcp list` shows `✘ Failed to connect` | Run `uv run --directory ~/elabftw-assistant elabftw_mcp.py` yourself. A Python error there points to the cause, usually a wrong folder path or a skipped `uv sync`. Stop it with Ctrl+C |
| Claude says the eLabFTW tools don't exist | Start a new session (step 8.2) |
| Tool errors mention `401` | The key is wrong, deleted, or belongs to another team (step 4) |
| Tool errors mention `CERTIFICATE_VERIFY_FAILED` | See step 5 |
| `File not found` when attaching | The path must exist on the computer running Claude Code |
| Search finds nothing you know exists | You're probably in a different team than the key's. Create the key from the right team |
| You want to change a setting | `claude mcp remove elabftw -s user`, then add it again (step 7) |
