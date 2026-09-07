# Driving Edge through Edge Agent Bridge: a guide for agents

You control the user's real Microsoft Edge, on the tab they are looking at, with their cookies
and sessions. Every action you take is visible to them. Work the way a careful colleague
sitting next to them would.

## The loop

1. `edge_snapshot` first. It returns the page as a tree of roles and names with reference IDs:

   ```
   tab 1459 "Files - Example App" http://localhost:8080/files
   page "Files - Example App" url=http://localhost:8080/files
   - heading "Files" level=1
   - textbox "Search" [e1] value=""
   - button "Upload" [e2]
   - table "Files"
     - row "12080 spec.pdf 2026-09-01" [e4]
       - button "Open" [e5]
   ```

2. Act by ref: `edge_click {ref: "e5"}`, `edge_fill {ref: "e1", text: "spec"}`. Refs are exact;
   text targets (`target: "Open"`) are a fallback when you have no fresh snapshot. Only refs reach
   inside an iframe: a ref carries its frame (`f31e1`), while a text or selector target is looked
   up in the main frame alone and comes back `target_not_found`. If a control you can see in the
   snapshot under an `iframe` line will not resolve, use its ref.
3. After anything that navigates or re-renders, snapshot again. Refs from an old snapshot fail
   with `stale_snapshot`; a removed element fails with `stale_ref`. Both mean: snapshot again.
4. Prefer `edge_wait` over sleeping: `{text: "Saved"}`, `{url: "/done"}`, `{load: true}`, or
   `{idle: true}` for pages that fetch after load. A timeout tells you what was still loading.
5. When a page misbehaves, read `edge_console`: it holds recent console output, uncaught
   exceptions, and any dialogs the bridge answered for you.

## Read the `tab` line before acting

Every result carries `tab: {id, title, url}`. If the user didn't name a page, confirm from the
first snapshot that you are on the one they meant before you type into it. Your session pins
to that tab afterwards, so a tab the user switches to will not receive your commands.

## Filling forms the user started

Snapshots include current values (`value="..."`, `checked`, selected option). Fill only the
empty fields unless asked to change one. Passwords show as `value="••••"`; never ask for or
echo the real value.

## Things that are easy to get wrong

- Coordinates are a last resort. Snapshots and refs already know where things are.
- `edge_type` sends real key events one character at a time (use it for autocomplete
  widgets); `edge_fill` replaces the value in one step and is faster for plain inputs.
- `<select>` needs `edge_select`, not `edge_fill`.
- Hidden file inputs still appear in the snapshot with `hidden`; `edge_upload` on their ref or on
  the styled button next to them works. Paths must be absolute.
- `edge_tab_close` needs an explicit `tabId`. The bridge will not guess which tab to close.
- `edge_eval` runs JavaScript with full page access. Use it for reading state you cannot get
  from a snapshot, not as a substitute for clicks (page code sees `isTrusted: false` events).
- A native `confirm()`/`alert()` is accepted automatically by default. Set
  `edge_dialog {policy: "manual"}` when the user must decide; the next action then returns
  `dialog_open` until you call `edge_dialog` with `accept` or `dismiss`.

## Errors

Every failure is `{success: false, code, error}`. Codes you will meet most:

| code | meaning | what to do |
|---|---|---|
| `stale_snapshot`, `stale_ref` | refs are from an old page state | snapshot again |
| `target_not_found` | nothing matched within the timeout | snapshot, pick a ref |
| `tab_not_found` | the pinned tab is gone | the next call re-resolves the active tab |
| `extension_offline` | Edge is closed or the extension is off | tell the user to open Edge and check the popup |
| `extension_outdated` | the extension predates the daemon | tell the user to update it |
| `dialog_open` | a native dialog is waiting | `edge_dialog` accept or dismiss |
| `timeout` | the wait condition never held | report what `inflight` or `url` shows |

## Setup (once per machine)

```
pip install edge-agent-bridge
edge-bridge setup          # registers the MCP server with the agent clients it finds
edge-bridge status         # daemon, extension, and pairing state
```

The extension comes from the Edge Add-ons store ("Edge Agent Bridge"); developers can load
`edge-bridge extension path` unpacked instead.
