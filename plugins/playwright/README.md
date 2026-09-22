# Playwright plugin

This opt-in plugin gives OmegaClaw a fresh, unauthenticated browser session
with a deliberately narrow interface:

- `browser-open "https://example.org"` opens a public HTTP(S) page in a new
  selected tab and returns its tab ID and page snapshot.
- `browser-tabs` lists open tab IDs and URLs, marking the selected tab.
- `browser-switch 2` selects tab 2 and returns a fresh snapshot.
- `browser-close-tab 2` closes tab 2 and lists the remaining tabs. Closing the
  selected tab selects the oldest remaining tab; use `browser-read` to get
  fresh click targets before clicking or downloading.
- `browser-navigate "https://example.org"` navigates the selected tab without
  opening another tab.
- `browser-read` returns visible text and numbered click targets.
- `browser-screenshot` saves a full-page PNG of the selected tab in
  `playwrightDownloadDir` (by default, `SAVE_PERMANENT_FILES_DIR/browser_downloads`).
  Each image has a unique `screenshot-tab-<id>-*.png` filename. Returns the
  full saved path, byte count, and tab ID, or `BROWSER-SCREENSHOT-FAILED` with
  the reason. It returns a file path, not inline image content. Screenshots
  are not subject to the download byte limit.
- `browser-back` and `browser-forward` navigate the selected tab's history
  and return a fresh snapshot. With no history entry, the page stays unchanged.
- `browser-reload` reloads the selected tab and returns a fresh snapshot.
- `browser-find "text"` searches current page text without case sensitivity,
  returning surrounding excerpts and zero-based character offsets. Results
  are limited to 50 matches and `playwrightMaxTextChars` excerpt characters;
  truncated results are marked. No matches returns `NO_MATCHES`.
- `browser-read-more` returns the next `playwrightMaxTextChars` characters
  from the latest captured text until `END_OF_TEXT`. Every fresh page snapshot
  (including read, switch, click, scroll, and wait) restarts this cursor.
  Continuation uses captured text, so asynchronous changes require a fresh
  `browser-read`. Character ranges are zero-based with an exclusive end.
- `browser-links` lists up to 200 visible link labels and resolved destination
  URLs, respecting the page's base URL. Truncation is marked. These URLs have
  not been validated for navigation; the existing public-URL checks still
  apply when opening them. This list does not assign click target numbers.
- `browser-click 3` clicks target 3 from the latest snapshot.
- `browser-type 3 "search terms"` replaces the contents of editable target 3
  and returns a fresh snapshot. Empty text clears the field. Supports native
  text/search/email/password/URL/telephone/number inputs, textareas, and
  contenteditable fields. Use the refreshed target numbers to click a search
  or submit button separately; typing does not press Enter, though site input
  handlers may trigger searches or other actions. Invalid targets, unsupported
  field types, read-only/disabled fields, and execution errors return
  `BROWSER-TYPE-FAILED`. Supplied text is omitted from fill error messages.
- `browser-select 3 "English"` selects an option in native dropdown target 3
  and returns a fresh snapshot. Snapshots mark dropdowns and show option labels,
  values, disabled state, and currently selected option text. Up to 200 options
  per dropdown are shown, with truncation marked. Matching is exact and
  case-sensitive: labels take precedence over values. Missing, ambiguous,
  disabled, or non-dropdown targets/options return `BROWSER-SELECT-FAILED`;
  browser execution errors use the same prefix. Selection chooses one option
  and replaces previous selections, including in multi-select controls.
  Custom menus continue to use `browser-click`. Selection can trigger a site's
  change handlers, including navigation or automatic submission.
- `browser-scroll 900` scrolls down 900 pixels and refreshes the snapshot;
  negative values scroll upward.
- `browser-wait 1500` waits for asynchronous output and refreshes the snapshot.
- `browser-download 4` explicitly downloads target 4 to the dedicated download
  directory and returns its verified byte count and SHA-256 digest.
- `browser-close` closes all tabs and destroys the browser context and its
  session data.

There is no plugin-imposed tab limit; capacity depends on available memory
and browser/OS resources. Read, click, scroll, wait, and download act on the
selected tab. Tab IDs remain stable until closed and reset after
`browser-close`. Click target numbers belong to the latest snapshot of the
selected tab; switching tabs refreshes them. Popups are also listed as tabs,
but do not automatically change the selection.

Tabs share one browser context, including cookies and origin-scoped local
storage. Closing the last tab keeps that context alive; `browser-close`
discards it. Each `browser-open` now creates a tab; use `browser-navigate`
for the previous behavior of navigating the current page.

Every browser command returns `BROWSER-<COMMAND>-FAILED: <reason>` when
validation or execution fails, and logs the error. For example, reading
without a selected tab returns `BROWSER-READ-FAILED`, and an invalid tab ID
for `browser-close-tab` returns `BROWSER-CLOSE-TAB-FAILED`. A command may have
partially completed before failing; use `browser-tabs` and `browser-read`
to inspect the current state. After an exception, obtain a fresh snapshot
before using numbered click targets.

The additional commands use `BROWSER-BACK-FAILED`, `BROWSER-FORWARD-FAILED`,
`BROWSER-RELOAD-FAILED`, `BROWSER-FIND-FAILED`, `BROWSER-READ-MORE-FAILED`, and
`BROWSER-LINKS-FAILED`. Empty link lists, no search matches, and end of text
are normal results, not failures.

Standard controls and common custom click controls (`role`, `onclick`, and
`tabindex`) are numbered. A configurable settling delay allows client-rendered
output to appear after a click, typing, or scroll. There are no skills for
directly setting cookies, uploading files,
evaluating JavaScript, or restoring a prior browser profile. Downloads require
the explicit `browser-download` skill; downloads triggered by ordinary clicks
are cancelled. Local,
loopback, link-local, and private-network URLs are rejected, including requests
reached through redirects.

## Enabling

Install the Python dependency and the browser binary outside the agent, then
set:

```yaml
playwrightEnabled: enabled
```

Optional settings are `playwrightBrowser` (`chromium`, `firefox`, or `webkit`),
`playwrightHeadless`, `playwrightTimeoutMs`, and `playwrightMaxTextChars`.
`playwrightSettleMs` controls the post-click/scroll delay and defaults to 750.
`playwrightDownloadDir` defaults to `memory/browser_downloads`, and
`playwrightMaxDownloadBytes` defaults to 10 MiB. Suggested filenames are
sanitized and existing files are never overwritten.

The default is `enabled`. Set `playwrightEnabled: disabled` to
turn it off. Playwright browser binaries are not installed or downloaded
automatically by OmegaClaw.
