# Design

What we build so that every requirement of [`REQUIREMENTS.md`](REQUIREMENTS.md) is met, and why this way. Words as in the vocabulary table of [`AGENTS.md`](AGENTS.md). Rewritten 2026-11-24 for the three gateways (the user: "1 entrypoint for agents"; the links are "a UX problem"); the refactor of 2026-11-23 (one profile per account, `clean`, the clicks by terminal) is built and kept. For humans, the same with pictures: [`README.html`](README.html).

## The parts

```
 who                        gateway (folder)                    Chrome
 an agent browsing  ──────► agent-gateway/   hook.py ─────────► Claude in Chrome, the session's Claude account profile,
   (Mac)                    agent_chrome.py, extension/,         visible, never in front
                            native_host.py, desktops.py
 code: scripts, tests, ───► script-gateway/  launch_headless.py ► its own headless Chrome, its own data folder
   jobs (Mac and NAS)
 the user clicking  ──────► terminal-links/  open_link.py ─────► claude.ai link in a Claude pane: that account's profile;
   (Mac, iTerm2)                                                 anything else: the user's own profile, or `open`
                                       │
                                       ▼
                 shared/  chrome_kit.py: the record ~/opt/chrome-gateways/state/ (open.json, history/, sessions/,
                          comments.jsonl, windows/, clicks.log), the account profiles; clean_job.sh: the daily check
```

| Part | Serves |
|---|---|
| agent gateway | R1–R6, R9–R12 |
| script gateway | R13, R19 |
| both, through the record (`shared/`) | R7, R8, R14, R18 |
| terminal links | R15, R16 |

## §1 Two gateways, one per kind of caller (serves R1, R13)

**Choice.** An agent that looks at a page itself uses Claude in Chrome (the agent gateway); code uses the launcher (the script gateway). Nobody chooses between headless and visible: an agent browsing is visible, never in front (R2); code is headless (R13). The rule agents read (skill chrome) is one line: "you look at a page yourself → Claude in Chrome; code you write or run → the launcher; on the NAS, only the launcher".

**Reason.** The two callers control Chrome in ways that cannot stand in for each other: Claude in Chrome takes orders only from an AI in a Claude session (a script cannot call it), and it needs a window (the NAS has none); a script drives Chrome through its remote-control port, on its own data folder (Chrome ≥ 136 refuses it on the default one, where the Claude account profiles live). Measured: 1,088 tabs opened on the Mac in November 2026, about 925 of them headless, mostly from code.

**Rejected.** (a) Only Claude in Chrome: scripts could not use it, and every run of code would pop a window. (b) Only a program-controlled Chrome per account, for agents too, with a headless/visible switch: a rebuild of what Claude in Chrome gives (clicking, reading pages for the model), every site logged in again in new data folders, agent-vault's typing ported, and a headless login to LinkedIn risks the account. (c) The agent choosing headless or visible (2026-11-23 design): one more decision with no benefit to the user, since an agent browsing may need them.

## §2 Asking to open a tab: the reason only (serves R7, R8)

`agent-chrome authorize-tab "<why>"`: one argument, the reason shown on the tab (R7); `--project P` only outside a repo folder. Needed by both gateways inside a Claude session (the launcher raises `PermissionError` without it); a job without Bash sets `CHROME_PURPOSE`. Kept: one tab per agent, and no Chrome started from the shell (a window no record knows, against R8). The old `--visibility`, `--visibility-reason` and `--mode` are accepted and ignored.

## §3 The profile is the Claude account's (serves R4, R5, R18)

A session's profile = the one of `$CLAUDE_ACCOUNT` (a → "Claude - Account A", b → "Claude - Account B"). The hook refuses any other `deviceId` and names the right one; the ids live in one table (`D_DEVICE` in `shared/chrome_kit.py`); `agent-chrome profile` prints them. The script gateway uses no Claude profile: its own data folder.

## §4 One window per Claude account and desktop (serves R3)

**Built (2026-11-24, extension 1.10.0).** `authorize-tab` records the desktop of the session's iTerm2 window (`desktops.py` `session_desktop()`) in `sessions/<key>.json`, and every tab of that key carries it (`desktop` in the record). The extension reports its windows' frames (at once, on any window change, every 30 s: a window dragged to another desktop moves no frame); the native host matches each frame to macOS's window of Google Chrome and answers each window's desktops. `agent-gateway/extension/place.js` moves an agent tab's group, in the background, into this profile's window on its session's desktop; each copy of the extension runs in one profile, so every window it sees is that account's. It never moves a group holding a user's tab, places each tab once, and closes the window a group left only when that group's arrival created it. Replaced: one window per project (its project map and marker windows).

**Limits, measured.** No program can move a window to another desktop on macOS 26, and a new window always opens on the desktop the user is looking at (1 Nov 2026); tabs move freely between windows. So when a session's desktop has no window of its profile, the tab stays where Claude in Chrome put it (the bar still names the session); no window is ever created for it. Two Chrome windows with one frame (both maximized on one screen, on two desktops) get no desktop: never a guess, their tabs stay. A session without an iTerm2 window (the phone, a job) has no desktop: its tabs stay.

**Prototype (2026-11-24).** Measured: (1) Chrome's AppleScript window ids are the extension's window ids (`249430992` in both); (2) the 3 browser windows each matched one macOS window by frame and one desktop (`SLSCopySpacesForWindows`); the 20 other macOS windows of Chrome are thin strips with no desktop, and the only shared frames are among them. So the extension sends each window's frame (`chrome.windows`, also on `onBoundsChanged`) and the native host writes each window's desktop into `windows/<profile>.json` (`desktops`: matches, space, label): no AppleScript in the host, so no macOS permission prompt. Still to measure once the extension is reloaded: that `chrome.windows` frames equal macOS's (the host's `matches` = 1), and two windows of one profile on two desktops.

## §5 The tab and the user (serves R9–R12)

The bar (opened at, session, project, why, job), the badge, NEEDS HUMAN with its expiry, the side panel and its comment box, subagents with one tab each and `agent-chrome wait-for-human`. The side panel says where to answer from who owns the tab (main agent: the terminal; a subagent: the panel). The quiet sites stay the extension's own list (`QUIET_HOSTS` in `extension/background.js`).

## §6 Nothing left behind: `agent-chrome clean` (serves R14)

```text
agent-chrome clean [--dry-run [--no-chrome]]
  for each tab in open.json:
      its session has ended (the Claude process recorded at authorization is gone) and nobody is needed → close it
      a headless Chrome whose caller is gone                                                         → quit it
      needs a human                                                        → keep, list
  open.json entries Chrome no longer has                                   → drop them
  sessions/ files of sessions ended over 30 days ago                       → delete them
  Chrome windows and processes the record does not know                    → list only, never close (they may be the user's)
```

The daily job `chrome-gateways` (`shared/clean_job.sh`, LaunchAgent `com.jeanlescut.chrome-gateways`) runs `--dry-run --no-chrome` and files one task when something needs the user. `--no-chrome`: the job decides from the record alone, because AppleScript from a LaunchAgent made macOS ask the user for a permission (2026-11-24). Closing on its own once the dry runs look right: the user's call. A killed script's Chrome is quit by the launcher's watcher.

## §7 Terminal links (serves R15, R16)

**Links an agent gives** are a rule in `CLAUDE.md` (my-setup, "Answering the user"), because every session must load it: full links in backticks; NAS files under `/Volumes/private/…` or `/Volumes/public/…`, else an Artifact or a copy there. Agents never open a window to show the user something (`agent-chrome show` was removed on 2026-11-24).

**The click** (iTerm2 → `open-link`, `terminal-links/open_link.py`):

```text
a claude.ai link, and the clicked tmux pane has @claude_account and a claude process still runs there → that account's profile
any other web link, an HTML or Markdown file                                                        → the user's own profile
any other file or folder                                                                            → open (macOS's choice)
```

Chrome gets the link as an argument of its binary with `--profile-directory`: a new tab in that profile's last window, no placement on a desktop (the user: for links, "it does not matter"). The pane's account is written by the agent gateway's hook at SessionStart and removed at SessionEnd (`tmux set -p @claude_account`); a crash leaves it, hence the claude-process check. iTerm2's two settings (Semantic History, a Smart Selection rule for `https://` and `file://`) are written by `install.sh` through iTerm2's Python API (`set_iterm2_clicks.py`), live. `open-link` refuses to run inside a Claude session: it may open the user's own profile.

## §8 Logins: agent-vault (serves R6)

A contract: agent-vault's `vault-type` reads `open.json` to check that the tab it types into belongs to the asking session (`session_id`, `agent_id`, `tab_id`). Those three fields keep their meaning; agent-firewall's sandbox (part `chrome`) runs after every change to the record. Agent gateway only: `vault-type` types through Apple Events into a visible Claude in Chrome tab.

## §9 Later: a message reaches an idle session (serves R20)

Not built. Path: the native host, on a comment for a session that made no tool call for a while, types a short line into its tmux pane (agent-resume knows how to find and resume a session's pane). Needs the user's OK first.

## §10 The rename from agent-chrome (2026-11-24)

| What | Before | After |
|---|---|---|
| repo | `~/dev/agents/agent-chrome`, GitHub `agent-chrome` | `~/dev/agents/chrome-gateways`, GitHub `chrome-gateways` (GitHub redirects the old name) |
| deployed | `~/opt/agent-chrome/kit/…`, `skills/`, `state/` | `~/opt/chrome-gateways/{agent-gateway,script-gateway,terminal-links,shared}/`, `skills/`, `state/` |
| the launcher | `~/opt/agent-chrome/kit/launch_headless.py` | `~/opt/chrome-gateways/script-gateway/launch_headless.py` |
| the daily job | `com.jeanlescut.agent-chrome`, job `agent-chrome` | `com.jeanlescut.chrome-gateways`, job `chrome-gateways` (the old one decommissioned) |
| the clicks | `agent-chrome show --clicked` | `open-link` |
| kept | the command `agent-chrome`, skill `chrome`, the native host `com.jeanlescut.agent_tab_notes`, the extension's id, the `AC_` and `CHROME_*` variables | |

`install.sh` moved the record once and kept transition links in `~/opt/agent-chrome/` until agent-vault's root-owned copy (reinstalled with sudo by the user) and the extension (loaded again from `~/opt/chrome-gateways/agent-gateway/extension` in both profiles) used the new paths; both done the same day, the links and that one-time code are gone (2026-11-24).

## §12 Logins through the script gateway (serves R13)

**Choice**, in this order, the first that works for the site (the tool's AGENTS.md says which): (1) the site's API with a token in `~/.config/<tool>/secrets.env`, no Chrome; (2) a session in the tool's own data folder `~/opt/<tool>/chrome/`, logged in once by the user in a visible window, reused headless; logged out → the script stops and files a task; (3) the code types a password from `~/.config/<tool>/secrets.env`, for a site whose session ends daily. Never an agent typing or reading a password, never a password saved in the data folder's Chrome, never the user's real accounts (they go through the agent gateway: a headless second login risks a ban).

**Reason.** (1) leaves nothing to expire on a page and nothing for a bot check to catch; (2) stores a session, not a password, and keeps the user the only one typing it; (3) puts a password on disk, so it comes last. agent-vault is not an option: it types through Apple Events into a visible Claude in Chrome tab, and no agent is in the loop to protect.

**Proposed, not built.** `launch_headless.py --login --data-dir D --url U`: a visible window on D for the user's one-time login (2), recorded, refused inside a Claude session. Today no tool keeps a logged-in data folder (no `~/opt/*/chrome/` on either machine, 2026-11-24).

## §11 Order of work

| Step | What | Status |
|---|---|---|
| 1–5 | clean-up; profile = account; `authorize-tab "<why>"`; clicks by terminal; `clean` and its job (2026-11-23/24, `c978a7d` … `7ce9c48`) | done |
| 6 | three gateways, rename to chrome-gateways, `show` removed, `open-link`, the launcher's `needs_human` removed (§1, §7, §10) | done 2026-11-24 |
| 7 | one window per account and desktop (§4): prototype (window ids and frames measured), then built (`place.js`, extension 1.10.0) | done 2026-11-24 |
| 8 | the transition links go (after agent-vault's sudo install and the extension's reload) | done 2026-11-24 |

Each step: its tests, then agent-firewall's sandbox part `chrome`, then commit, push, `bash install.sh`.

## Acceptance

| # | Check | Requirement |
|---|---|---|
| A1 | An agent opens a page through Claude in Chrome in its account's profile; it never comes to the front | R1, R2, R5 |
| A2 | A select_browser of the other account's profile is refused, with the right id in the message | R5 |
| A3 | Two sessions on account a, on one desktop: their tabs end in one window | R3 |
| A4 | A claude.ai link clicked in a session on account b opens in "Claude - Account B"; any other link in the user's own profile | R16 |
| A5 | A NAS session asked for a page in `~/data/private` gives `file:///Volumes/private/…`; for one in its home, an Artifact | R15 |
| A6 | A script killed mid-run leaves no Chrome; its run is in `agent-chrome status --since 1h` | R13, R14 |
| A7 | agent-firewall `sandbox/run_all.sh chrome` passes after every step | R6 |

## Superseded decisions

| Was | Now | Why |
|---|---|---|
| One agent window per project (1 Nov 2026) | per Claude account and desktop | one profile per account (2026-11-21); the user, 2026-11-23 |
| Three visibility levels chosen by the agent (1 Nov), then "the agent decides" (2026-11-23) | agents visible, code headless | the user, 2026-11-24: one way in for agents |
| `agent-chrome show`: an agent opens a page on its desktop | the agent gives a link, the user clicks | the user, 2026-11-24: links are a UX matter |
| A click opens the session's profile for every link (2026-11-23) | only claude.ai links; the rest the user's own profile | the user, 2026-11-24 |
| A list of allowed sites (jobs, and "later" here) | none | the user, 2026-11-23 (jobs `2834ea5`) |
