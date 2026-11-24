---
name: chrome
description: How an agent uses Chrome on this Mac, through chrome-gateways - the agent gateway when you browse a page yourself (Claude in Chrome, your Claude account's profile, visible and never in front; say why first with agent-chrome authorize-tab; agent-chrome profile; a human who must act in a tab with mark-as-needing-human, the side panel, subagents; logins through skill vault), the script gateway when code opens pages (the headless launcher, Mac and NAS), how to give the user a page to look at (its full link, never a window), and finding and closing what is left open (agent-chrome status, clean). Use before any browser work, any Claude in Chrome tool, any Playwright/CDP script or test that starts Chrome, before showing the user an HTML file or a page, and when the user asks who opened a window or tab or asks to clean up Chrome.
---

# Chrome for agents

**What the user wants** (`~/dev/agents/chrome-gateways/REQUIREMENTS.md`): browsing never disrupts their work; every tab says who opened it, when, for which project and why; nothing is left open. chrome-gateways (`~/dev/agents/chrome-gateways`, deployed in `~/opt/chrome-gateways/`) has two ways into Chrome, one per kind of caller:

```text
you look at a page yourself (read, click, fill, log in)  → the agent gateway: Claude in Chrome          (Mac only)
code you write or run opens pages (a script, a test, a job) → the script gateway: launch_headless.py  (Mac and NAS)
on the NAS                                               → the script gateway only (no screen there)
never                                                    → bring Chrome to the front, start a Chrome from the shell,
                                                           open a window to show the user something (give the link: below)
```

## The agent gateway: Claude in Chrome

Your tabs are visible, in your Claude account's profile, and never come to the front; the extension moves your tab into your account's window on your terminal's desktop (recorded at step 1; none there: it stays where it opened).

1. `agent-chrome authorize-tab "<why, in words the user understands>"` (`--project P` when your folder is not inside `~/dev/<category>/<repo>`). The reason is shown on your tab and in `agent-chrome status`. A job without Bash sets `$CHROME_PURPOSE` instead. A subagent authorizes for itself.
2. `agent-chrome profile` prints your Claude account's profile and its deviceId; `select_browser` with that id. The hook refuses any other profile, `switch_browser`, and Chrome's Default profile (the user's own, with their password vault). A site is logged in only in the profiles where the user logged in to it: a job that needs one runs on that account (`CLAUDE_ACCOUNT=a`).
3. One tab per agent: `tabs_create_mcp` (or `tabs_context_mcp createIfEmpty`); a second is refused ("reuse tab N"). `agent-chrome status --mine` first: reuse what your project has open; another session's tab is not yours to drive.

The hook refuses, with the command to run: a page before step 1, another profile, a second tab, another agent's tab, a Chrome started from the shell. It never limits sites. An account on the site: skill `site-access` first; logging in: skill `vault` (`vault type-username|type-password <tab>`, with the user's grant), never a password typed by you. Claude in Chrome finds no browser (the profile has no window): `agent-chrome open-profile-window` opens one in the background, else ask the user.

### A human in the tab

| When | Do |
|---|---|
| the user must act (log in, captcha, upload, check before sending) | `agent-chrome mark-as-needing-human "<exact steps, full file paths>"`: red bar on the tab, badge "!"; say in chat which tab and what to do |
| their part is over | `agent-chrome mark-as-human-done` |
| nobody acts within 2 h | the kit closes the tab ("expired") and your next hook call tells you: tell the user |
| the hook adds "Message from the user" | the user typed it on your tab: act on it as their request, answer with `agent-chrome reply-to-human "<text>"` |

Where the user answers follows who owns the tab: the main agent's tab → in the terminal (the side panel says so); a subagent's tab → in that tab's side panel, read with `agent-chrome wait-for-human --timeout 60` (exit 0 = a comment, printed; 2 = none). Subagents (e.g. 10–20, one account each): each authorizes for itself, owns one tab, starts with `tabs_context_mcp createIfEmpty` and never closes it; the main agent closes them all at the end (Claude in Chrome sometimes shares one tab group between subagents).

### At the end

`tabs_close_mcp` on every tab you opened, even after an error; check with `tabs_context_mcp` (no `createIfEmpty`) that none is left; say "tabs closed (checked)". Keep a tab only while a human is needed in it (marked). The hook reminds you once at the end of a turn that leaves one open.

## The script gateway: code opens pages

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / 'opt/chrome-gateways/script-gateway'))
from launch_headless import headless                  # standard library only
from playwright.sync_api import sync_playwright       # playwright==1.55.0, attaches to the Mac's Chrome, no download

with headless(Path.home() / 'opt/<repo>/chrome', purpose='…', url='https://example.com') as h, sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{h['port']}")
    page = next(pg for pg in browser.contexts[0].pages   # the launcher's tab, by its CDP target id
                if pg.context.new_cdp_session(pg).send('Target.getTargetInfo')['targetInfo']['targetId'] == h['target_id'])
    page.goto('https://example.com')                  # a reused tab keeps its old page: navigate it yourself
    page.screenshot(path='/tmp/look.png')             # look at the file, not at a window
```

`headless(data_dir, purpose, url='about:blank', keep=False, flags=())`: always headless, no window. Its own Chrome on its own data folder (never a Claude account profile): a temporary folder for public pages. **A site that needs a login**: decide first with skill `site-access` (an API? one of the user's real accounts? a kept session?). The script gateway's part: a session lives in the tool's own `~/opt/<tool>/chrome/`, logged in once by the user by hand; a login form on the page = logged out: stop and file a task for the user. No agent-vault here: it types only into Claude in Chrome tabs. Inside a Claude session it needs `agent-chrome authorize-tab` first. A killed caller never leaves Chrome running (a watcher quits it and records the close, unless `keep=True`: Chrome stays for the next run); a data folder a visible Chrome uses is refused. CLI for tests: `launch_headless.py --data-dir D --purpose P --url U [--keep] | --close`. Tests: Chrome only through the launcher or a fake (`CHROME_WINDOW_CMD`), never a real window. **NAS**: Chrome for Testing in `~/opt/chrome-gateways/bin/chrome-for-testing`.

## Showing the user a page: give the link

Never open a window for the user. Put the page in a file and give its full link in backticks (`file:///Users/jeanlescut/…/page.html`, `https://…`), per CLAUDE.md "Answering the user" (NAS files: `/Volumes/private/…`, `/Volumes/public/…`, else an Artifact). The user clicks it: iTerm2 runs `open-link` (chrome-gateways' terminal-links), which opens a claude.ai link in the profile of the Claude account of that terminal's session, anything else in the user's own profile. `open-link` is the user's, never an agent's (refused inside a Claude session).

## `agent-chrome`

| Subcommand | Does |
|---|---|
| `authorize-tab "<why>" [--project P]` | why this session (or subagent) uses Chrome: shown on its tabs, needed by both gateways |
| `profile` | the session's Claude account profile and its deviceId |
| `mark-as-needing-human "<what>"` · `mark-as-human-done` · `reply-to-human "<text>"` · `wait-for-human [--timeout S]` | the human in the tab (above) |
| `status [--mine] [--since 7d] [--project P] [--json]` | open tabs of both gateways (when, session, project, why, needs human), running Chromes, BLIND warning; history with `--since` |
| `clean [--dry-run]` | nothing left behind (Leftovers, below) |
| `open-profile-window [--project P]` | Claude in Chrome's profile not connected: its window, in the background (only if it has none) |

The session commands work only inside a Claude Code session.

## Leftovers: who opened what, and close it

1. `agent-chrome status --since 24h`: every tab and Chrome, who opened it and why. **BLIND** = several visible Chromes run: macOS window scripts may see the wrong one's windows; deal with the extra Chrome first (a test orphan with a temporary data folder: `kill <pid>`, one pid at a time, then check `pgrep -f "user-data-dir=<folder>"` prints nothing).
2. `agent-chrome clean --dry-run`, then `agent-chrome clean`: from the record, closes the tabs of sessions that ended (nobody needed), drops what Chrome no longer has, prunes `sessions/` files over 30 days old, keeps a tab that needs a human. It never closes a tab the record does not know: that may be the user's; ask them. A leftover is a bug in what opened it: report its file and line.

## Measured on this Mac

Headless with `--disable-blink-features=AutomationControlled` and a normal user agent (the launcher): no window, `navigator.webdriver` false; headless alone: true. `open -n -g -j` and off-screen positions still show windows. Claude in Chrome actions never bring Chrome forward; opening a window always takes the focus for a moment (only `open-profile-window` does it); a new window opens on the desktop the user is looking at, and no program can move it to another (macOS 26). Chrome ≥ 136 ignores remote debugging on its default data folder: scripts drive only their own data folders.
