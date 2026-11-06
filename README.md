# Blinders

Save the exact text of a selected passage or a PNG of a browser viewport in a local SQLite inbox. Codex and Claude Code can request a capture from a paired Chrome tab and receive its ID, timestamp, source path, byte count and SHA-256 digest. The capture runs locally, without a model call. Blinders works on its own and shares the capture table used by Stencil’s Blinders preview.

## Install and open

Run in a terminal on the Mac or Linux computer where you use Chrome. Requires Git and Python 3.9 or newer. The application uses the Python standard library.

```sh
curl -fsSL https://raw.githubusercontent.com/Swixixle/Blinders/main/setup.sh | sh
```

The installer clones the source into `~/.local/share/blinders/app`, links the command at `~/.local/bin/blinders`, registers Blinders with each available Codex CLI or Claude Code client, and opens the inbox. Keep that terminal open while capturing. To reopen later:

```sh
"$HOME/.local/bin/blinders" open
```

**Pair Chrome once per browser session.** The inbox normally opens at [127.0.0.1:8787/blinders](http://127.0.0.1:8787/blinders). Use Chrome to open it. Go to `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select the **browser** folder printed by the installer. Then click the Blinders extension on **the inbox tab first** and on **the research tab second**. Keep the inbox open. Click the extension on a new source to switch tabs. Reconnect after a cross-site navigation or Chrome restart. Chrome’s Extensions menu also exposes the action if you have not pinned it.

Start a new local Codex or Claude Code session after registration. Tell it:

> Use Blinders on my connected research tab. Save the selected passage and a screenshot of the current viewport. Return both capture IDs.

## Give an assistant the repository

Point it at [AGENTS.md](AGENTS.md). Claude Code also has a [CLAUDE.md](CLAUDE.md) entry point. An assistant running on the same computer can use the registered MCP tools or the CLI. A browser-capable assistant with access to the Mac can operate the paired inbox directly. A hosted chat can read this public repo; using your Mac’s live tab requires a connected local tool or browser.

| Request | MCP tool |
| --- | --- |
| Check which tab is paired | `blinders_status` |
| Save the current selection | `blinders_capture_text` |
| Save one identified rendered element | `blinders_capture_text` with a CSS selector |
| Save the current visible viewport | `blinders_capture_viewport` |
| Find receipts or explicitly read an excerpt | `blinders_list`, `blinders_read_text` |

Selection captures save the browser’s selection string. Selector captures save the visible element’s rendered text. Screenshots preserve the pixels in the visible page viewport, including layout. Offscreen material requires separate captures. Browser frame permissions apply. Only receipts are returned by capture tools. A separate read tool can return a specified piece of saved text to an assistant.

## CLI

Use `~/.local/bin/blinders` if that directory is outside your PATH.

```sh
blinders status
blinders capture text
blinders capture text --selector '#question'
blinders capture png
blinders text --source 'https://example.org/article' --title 'Article' < original.txt
blinders png --source 'https://example.org/article' < viewport.png
blinders list
blinders export CAPTURE_UUID > exact-original.png
```

The two standard-input commands preserve the supplied bytes and work without Chrome or an open inbox. Each save supports up to 12 MiB. A panelless agent can use these commands with the actual output of its browser tool. A receipt identifies the bytes supplied and the source attributed to them.

## Local storage and Stencil

On macOS the default database is `~/Library/Application Support/Stencil/stencil.sqlite3`. On Linux it is `~/.local/share/stencil/stencil.sqlite3`. Blinders owns the `blinders_captures` table only. It never publishes captures to GitHub. Source receipts omit URL queries and fragments. Use `BLINDERS_DATA_DIR` or `STENCIL_DATA_DIR` to opt into another records location. Use the same setting for the CLI, inbox and MCP processes. To share the earlier isolated preview’s records, point them to `~/Library/Application Support/Stencil Blinders Preview/records`.

The standalone inbox serves the live assistant bridge. The earlier Stencil preview can display shared captures when both apps point to the same database. Use the standalone inbox for MCP capture requests.

## Setup details

If you already cloned this repo, run `sh install.sh --agents`. Use `sh install.sh` for CLI-only setup. The installer preserves existing MCP entries named `blinders` and reports missing clients. After installing a client, rerun the installer. For a custom port set `BLINDERS_PORT` for the inbox and the assistant process. For an update, fast-forward your installer-owned checkout using `git -C "$HOME/.local/share/blinders/app" pull --ff-only`, rerun the installer, reload the unpacked extension and restart the inbox.

## Verify

```sh
python3 -m unittest discover -s tests -v
```

The optional `tests/ui_blinders_check.cjs` uses jsdom for the browser UI and simulated Chrome extension APIs against a real local server and database. Set `STENCIL_JSDOM_PATH` to an installed jsdom module to run it. For a live Chrome check, pair a disposable page, select a passage with repeated spaces, request text and PNG, and open the saved entries.
