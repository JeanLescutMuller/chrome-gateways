# chrome-gateways

Every way into Chrome, one gateway per kind of caller (vocabulary below), and the **record** they share. Named agent-chrome until 2026-11-24 (history: `git log --follow`). Development home: Mac; the NAS gets the script gateway (`dev-install chrome-gateways`). What the user gets: [`REQUIREMENTS.md`](REQUIREMENTS.md); how it is built: [`DESIGN.md`](DESIGN.md) (§11, the steps); for humans: [`README.html`](README.html) (open it in a browser); the rules agents follow: skill `chrome` ([`agent-gateway/skills/chrome/SKILL.md`](agent-gateway/skills/chrome/SKILL.md)).

agent-firewall's sandbox finds this repo at `AC_REPO` (default `~/dev/agents/chrome-gateways`), the deployed copy at `~/opt/chrome-gateways`.

```
chrome-gateways/                     deployed to ~/opt/chrome-gateways/ (same folders, no tests) by install.sh
├── AGENTS.md · README.html · REQUIREMENTS.md · DESIGN.md
├── install.sh · uninstall.sh        no sudo; what they make: install.sh's header
├── agent-gateway/                   an agent browsing (Mac)
│   ├── hook.py                      every Claude in Chrome call; Bash; marks the tmux pane's Claude account
│   ├── agent_chrome.py              the command agent-chrome
│   ├── native_host.py · extension/  "Agent tab notes": bar, badge, side panel, place.js
│   ├── desktops.py                  macOS desktops and windows (DESIGN.md §4)
│   ├── merge_claude_settings.py     the hook groups in a Claude settings.json, nothing else (skill config-ownership)
│   ├── skills/chrome/               skill chrome
│   ├── doc/extension-shots/
│   └── tests/
├── script-gateway/                  code opening pages (Mac and NAS): launch_headless.py; tests/test_launcher.py
├── terminal-links/                  the user's clicks (Mac): open_link.py (open-link), set_iterm2_clicks.py; tests/test_open_link.py
└── shared/                          chrome_kit.py (the record, the profiles: D_DEVICE), clean_job.sh (the daily job); tests/test_install.sh
```

## Who uses it

| Who | What |
|---|---|
| agent-firewall's hook, agent-vault (`vault-type`) | `open.json`: which session owns a tab (`session_id`, `agent_id`, `tab_id`: DESIGN.md §8) |
| agent-firewall's sandbox | runs the hook and tests from `AC_REPO`, the deployed code from `~/opt/chrome-gateways` |
| other projects' scripts (jobs, cutaway, robotics-radar…) | `~/opt/chrome-gateways/script-gateway/launch_headless.py` |
| my-setup | the agent Chrome profiles per Claude account (`claude-setup/05-chrome.md`); `CLAUDE.md`'s rule on links |

## Rules

- Edit only here; `main` is what gets installed: commit, push, then `bash install.sh`.
- A module imports only from its own folder and `shared/` (each puts both on `sys.path`); the folders are deployed as they are.
- A test never touches the real record, Chrome, iTerm2 or the user's tmux: `CHROME_STATE`, a scratch `HOME`, fakes in `CHROME_WINDOW_CMD`, `OPEN_CMD`, `OPEN_LINK_PANE` (2026-11-23: a test that reached the real Chrome opened windows on the user's screen). The live test (`agent-gateway/tests/live/test_live.sh`) costs about $0.02 of haiku: run it only after a change to the hook's decisions.
- After a change to the record, run agent-firewall's sandbox part `chrome` (`bash sandbox/run_all.sh chrome` in `/Users/jeanlescut/dev/agents/agent-firewall`): agent-vault depends on it.
- The hook fails open (never blocks on its own error): keep the `|| true` in its command.
- A change to `agent-gateway/extension/` raises `version` in its `manifest.json` (`install.sh` refuses it otherwise); give the user the new version to check after the reload (2026-11-24).
- The deny rules on the user's own Chrome profile (Default) are agent-firewall's (its `deny/`), not merged here. The hook still refuses that profile; only `open-link` (the user's click) opens it.
- Names: `~/opt/chrome-gateways`, env var prefix `AC_` for new variables (`AC_REPO`); the older `CHROME_*` variables, the command `agent-chrome`, skill `chrome` and the native host `com.jeanlescut.agent_tab_notes` (the extension id depends on it) keep their names.
- Project of a tab = the repo folder name, in `~/dev/<category>/<repo>`, the old `~/dev/<repo>`, or `~/opt/<repo>`.

## Test

| What | Command |
|---|---|
| the fast tests | `python3 -I agent-gateway/tests/test_agent_gateway.py` · `python3 -I agent-gateway/tests/test_desktops.py` · `python3 -I agent-gateway/tests/test_merge.py` · `node agent-gateway/tests/test_place.js` · `python3 -I script-gateway/tests/test_launcher.py` · `python3 -I terminal-links/tests/test_open_link.py` · `bash shared/tests/test_install.sh` |
| the extension, headless | `<python with playwright> agent-gateway/tests/test_extension.py <Chrome for Testing binary> <scratch dir> [<screenshots dir>]` |
| live, with a Claude session | `bash agent-gateway/tests/live/test_live.sh <scratch folder>` |

## Vocabulary

| Word | Means |
|---|---|
| **agent gateway** | the way an agent browses a page itself: Claude in Chrome, the hook, `agent-chrome`, the extension (`agent-gateway/`) |
| **script gateway** | the way code opens pages: `launch_headless.py`, always headless (`script-gateway/`) |
| **terminal links** | how agents print links and what the user's click opens (`terminal-links/`, `open-link`) |
| **record** | `~/opt/chrome-gateways/state/`: `open.json` (open now), `history/YYYY-MM.jsonl` (every event), `comments.jsonl`, `sessions/`, `windows/`, `clicks.log` |
| **authorization** | `agent-chrome authorize-tab`: a session's permission to open its one tab, with the reason shown on it |
| **agent window** | an agent profile's window on one desktop: the one window where that Claude account's agents put their tabs on that desktop (DESIGN.md §4; the user, 2026-11-23) |
