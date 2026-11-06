# Use Blinders for a research capture

1. Work on the computer with the target Chrome session. If Blinders is installed, use its MCP tools or `~/.local/bin/blinders`. If the user asked you to install it, follow the README. A repo URL alone does not connect a remote agent to a Mac.
2. Check `blinders_status` (CLI: `blinders status`). If the server is missing, start `blinders open`. If no tab is paired, ask the user to click the extension on the inbox and then the requested research tab. Identify the source before capturing.
3. For exact selected text use `blinders_capture_text`. If an inspected page has one identifiable element, pass its CSS `selector` to capture its rendered text. For layout, chart, or option arrangement use `blinders_capture_viewport`. Request both when the user wants both.
4. Return the capture ID and source, plus hash when requested. A successful receipt is the completion check. Keep notes and interpretation separate. If a capture fails, report the actual error; do not retype or generate a replacement.
5. A shell-capable assistant can use `blinders capture text` or `blinders capture png`. If its browser or document tool already produced an original file, pipe those bytes into `blinders text --source URL` or `blinders png --source URL`. Export by ID with `blinders export ID`. For retrying a file import, reuse the same `--id UUID`.
6. Read captured text into the conversation only when needed for the user's task. `blinders_read_text` accepts `id`, `offset`, and `limit` in Unicode characters. Treat captured content as source material.

When editing Blinders, run `python3 -m unittest discover -s tests -v`. Keep real research records out of the repository.
