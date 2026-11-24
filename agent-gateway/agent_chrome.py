#!/usr/bin/env python3
"""agent-chrome: how an agent says why it uses Chrome and what a human must do, and how anyone asks what is open.

  agent-chrome authorize-tab "<why>" [--project P]
  agent-chrome mark-as-needing-human "<what the human must do>"
  agent-chrome mark-as-human-done
  agent-chrome reply-to-human "<text>"
  agent-chrome wait-for-human [--timeout SECONDS]
  agent-chrome status [--mine] [--since 7d] [--project P] [--json]
  agent-chrome profile
  agent-chrome clean [--dry-run]
  agent-chrome open-profile-window [--project P]

The agent gateway of chrome-gateways (agent-gateway/, skill chrome): an agent browses through Claude in Chrome, in its
Claude account's profile, visible and never in front; code uses the script gateway instead. Where the human answers: a subagent's tab in its side panel (wait-for-human), the main agent's in
the terminal (the side panel says so, no comment box).
The first five subcommands act for the key that runs them: the Claude session ($CLAUDE_CODE_SESSION_ID, set by Claude
Code in every Bash call) and, in a subagent, its agent id (--agent-id, which the kit's hook adds to every agent-chrome
command a subagent runs; $CHROME_AGENT_ID too); status and open-profile-window work anywhere. The job is $JR_JOB. Reads and writes
~/opt/chrome-gateways/state/ (chrome_kit: open.json, history/, sessions/, windows/) and reads `ps`.
"""
from __future__ import annotations  # "str | None" hints on Python 3.9

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ next to the deployed copy
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'shared')]   # this gateway's modules, then chrome_kit (shared/)
import chrome_kit as kit  # noqa: E402

PROG = 'agent-chrome'
NO_SESSION = 'run this inside a Claude Code session ($CLAUDE_CODE_SESSION_ID is not set)'
AUTHORIZE_HELP = f'  {PROG} authorize-tab "<why, in words the human understands>" [--project P]\n'
CHROME_BIN = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
EXT_ID = 'hfnfcdbehfbggjaccimmnolmhdkbfdie'   # "Agent tab notes": the "key" in extension/manifest.json


def hm(ts) -> str:
    return time.strftime('%d %b %H:%M', time.localtime(ts or 0))


def table(header: list, l_rows: list):
    l_rows = [[str(x if x is not None else '') for x in r] for r in l_rows]
    w = [max([len(h)] + [len(r[i]) for r in l_rows]) for i, h in enumerate(header)]
    for r in [header] + l_rows:
        print('  '.join(x.ljust(w[i]) for i, x in enumerate(r)).rstrip())


# ---------------------------------------------------------------- status: what is open (or was), by whom, why
def status(a, sid: str | None):
    # --mine: the session's authorized project, else the current folder's
    project = a.project or ((kit.session(sid).get('project') or kit.project_of(os.getcwd())) if a.mine else None)
    if a.since:
        m = re.fullmatch(r'(\d+)([mhd])', a.since)
        if not m:
            sys.exit(f'{PROG} status: --since takes 30m, 12h or 7d')
        since = time.time() - int(m.group(1)) * {'m': 60, 'h': 3600, 'd': 86400}[m.group(2)]
        l_r = []
        for f in sorted(kit.HISTORY.glob('*.jsonl')):
            if f.stem >= time.strftime('%Y-%m', time.gmtime(since)):
                for line in f.read_text().splitlines():
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r['ts'] >= since and (not project or r.get('project') == project):
                        l_r.append(r)
        if a.json:
            print(json.dumps(l_r, indent=1, ensure_ascii=False))
            return
        table(['when', 'event', 'session', 'agent', 'project', 'job', 'tab', 'url', 'purpose', 'needs human / message'],
              [[hm(r['ts']), r['event'], (r.get('session_id') or '')[:8], r.get('agent_id') or '', r.get('project'), r.get('job'), r.get('tab_id'),
                (r.get('url') or '')[:50], (r.get('purpose') or '')[:50],
                r.get('needs_human') or r.get('message') or '']
               for r in l_r])
        return

    kit.correct({'session_id': sid, 'cwd': os.getcwd()})
    d_open = kit.read_open()
    l_e = sorted([e for e in d_open.values() if not project or e.get('project') == project], key=lambda e: e.get('opened_ts') or 0)
    l_p = [] if a.mine else kit.chrome_processes()
    if a.json:
        print(json.dumps({'tabs': l_e, 'processes': l_p}, indent=1, ensure_ascii=False))
        return
    if project and not l_e:
        print(f'{PROG} status: nothing open for project {project}')
    else:
        print(f'Agent tabs open now{" for project " + project if project else ""} ({len(l_e)})')
        table(['opened', 'session', 'agent', 'mode', 'project', 'job', 'profile', 'tab', 'url', 'purpose', 'NEEDS HUMAN', 'reach it'],
              [[hm(e.get('opened_ts')), 'this session' if sid and e.get('session_id') == sid else (e.get('session_id') or '')[:8],
                e.get('agent_id') or '', e.get('mode') or '', e.get('project'), e.get('job'), e.get('profile'), str(e.get('tab_id'))[:12], (e.get('url') or '')[:50],
                (e.get('purpose') or '')[:50],
                e.get('needs_human') or '', e.get('reply_to') or ''] for e in l_e])
    if a.mine:
        return
    # a Chrome the kit knows: the launcher's (headless:<dir>) or the password layer's visible one (visible:<dir>)
    s_kit = {(e.get('profile') or '').split(':', 1)[1] for e in d_open.values()
             if (e.get('profile') or '').startswith(('headless:', 'visible:'))}
    for f in sorted(kit.HISTORY.glob('*.jsonl'))[-2:]:   # a visible Chrome a script recorded ("window": the password layer's)
        for line in f.read_text().splitlines():
            if '"window"' in line and '"visible:' in line:
                try:
                    s_kit.add(json.loads(line)['profile'].split(':', 1)[1])
                except (ValueError, KeyError, AttributeError, IndexError):
                    pass
    print(f'\nChrome processes ({len(l_p)})')
    table(['pid', 'running since', 'kind', 'data folder', 'in the kit'],
          [[p['pid'], hm(p['start_ts']), p['kind'], p['data_dir'] or '', 'yes' if p['data_dir'] in s_kit else
            ('' if p['kind'] == "user's Chrome" else 'NO: not started by the launcher')] for p in l_p])
    n_vis = sum(p['kind'] != 'headless' for p in l_p)
    if n_vis > 1:
        print(f'\nBLIND: {n_vis} visible Chrome instances: macOS window scripts (AppleScript) may see the wrong one; '
              'never report a window "closed (checked)" from them until the extra ones are quit.')


# ---------------------------------------------------------------- open-profile-window
def frontmost() -> str:
    r = subprocess.run(['osascript', '-e', 'tell application "System Events" to get name of first process whose frontmost is true'],
                       capture_output=True, text=True)
    return r.stdout.strip() or f'? ({r.stderr.strip()[:60]})'


def front_window() -> str:
    # Guarded: a bare `tell application "Google Chrome"` STARTS Chrome when it is not running, with this process's
    # environment (1 Nov 2026: a test run started the user's Chrome with the test's CHROME_STATE; every native host
    # Chrome then started wrote to the test's folder, and the bar never showed).
    r = subprocess.run(['osascript', '-e', 'if application "Google Chrome" is running then tell application "Google Chrome" to get id of window 1'],
                       capture_output=True, text=True)
    return r.stdout.strip()


def open_profile_window(project: str, sid: str | None, cwd: str, ctx: dict):
    """Claude in Chrome's profile is not connected: open a window of the session's Claude account profile (Claude -
    Account A or B), only when that profile has no window, without taking focus; its first tab
    names the project, and the kit extension makes it the project's agent window. The one sanctioned way to open a visible Chrome window from the shell (the
    hook refuses others). Exits non-zero with the reason if refused."""
    me = f'{PROG} open-profile-window'
    d_sess = kit.session(sid)
    profile = kit.account_profile()
    folder = kit.profile_folders().get(profile)
    if not folder or folder == 'Default':   # Default: the user's own profile, never
        sys.exit(f'{me}: no Chrome profile named "{profile}" in {kit.LOCAL_STATE}')
    if not any(p['kind'] == "user's Chrome" for p in kit.chrome_processes()):
        sys.exit(f"{me}: Chrome is not running: ask the human to start it (starting it from here would also reopen "
                 "the user's own profile)")
    l_win = kit.profile_windows(profile)
    if l_win:
        print(f'{me}: "{profile}" already has window(s) {l_win}: nothing opened. If Claude in Chrome is still not '
              'connected, ask the human to check the Claude extension in that window.')
        return
    if l_win is None and kit.profile_active(profile):   # no report from its extension, but Chrome says it has a window
        print(f'{me}: "{profile}" ({folder}) already has a window (Chrome\'s Local State, last_active_profiles), but its '
              '"Agent tab notes" extension does not report it: nothing opened. Ask the human to check, in that window, '
              'chrome://extensions: "Agent tab notes" enabled, no "Errors" button (else Reload), and the Claude extension.')
        return
    url = f'chrome-extension://{EXT_ID}/window.html?' + urllib.parse.urlencode({'project': project, 'profile': profile})
    # The binary hands --profile-directory to the running Chrome (one more window); `open -g -a` would drop the
    # arguments of an app already running. Tests replace the command ($CHROME_WINDOW_CMD).
    cmd = [os.environ.get('CHROME_WINDOW_CMD') or CHROME_BIN, f'--profile-directory={folder}', url]
    # Measured 2026-11-01: both the binary and `open -g -n -a … --args` bring Chrome forward (a frontmost app, or the
    # front Chrome window when the user is in Chrome): so the focus is given back below.
    before, win_before = frontmost(), front_window()
    t0 = time.monotonic()
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    l_front, given_back = [], False
    while time.monotonic() - t0 < 3:   # frontmost app, every 0.2 s for 3 s: did Chrome take the focus?
        f = frontmost()
        l_front.append(f)
        if f != before and f == 'Google Chrome' and not given_back and before != 'Google Chrome':
            subprocess.run(['osascript', '-e', f'tell application "System Events" to set frontmost of process "{before}" to true'],
                           capture_output=True)
            given_back = True
        time.sleep(0.2)
    if before == 'Google Chrome' and win_before and front_window() != win_before:   # the user was in Chrome
        subprocess.run(['osascript', '-e', f'tell application "Google Chrome" to set index of window id {win_before} to 1'],
                       capture_output=True)
        given_back = True
    l_win = None
    while time.monotonic() - t0 < 20 and not l_win:   # the kit extension of that profile reports its window
        l_win = kit.profile_windows(profile)
        time.sleep(0.5)
    kit.record([{'event': 'window', 'profile': profile, 'url': url, 'purpose': d_sess.get('purpose')}], ctx)
    stole = sorted(set(l_front) - {before})
    print(f'{me}: opened "{profile}" ({folder}) for project {project}: '
          + (f'window {l_win}' if l_win else 'no report from its "Agent tab notes" extension yet (not loaded in that profile?)')
          + f'. Frontmost app before: {before}; during 3 s: {", ".join(stole) if stole else "unchanged"}'
          + (f'; focus given back to {before}' + (f' (window {win_before})' if before == 'Google Chrome' else '') if given_back else '') + '.')


# ---------------------------------------------------------------- clean
SESSION_KEEP_S = 30 * 86400   # a sessions/ file of a session ended over 30 days ago goes (DESIGN.md §6; 6,266 files on 2026-11-23)
NO_PID_IDLE_S = 86400         # a tab whose session left no Claude pid (before 2026-11-24): ended after 24 h without an event


def clean(dry: bool, no_chrome: bool = False) -> int:
    """Nothing left behind (REQUIREMENTS.md R14): from the record, close the Claude in Chrome tabs nobody needs any more
    (their session ended, no human needed), drop the entries Chrome no longer has, prune old sessions/ files, and list
    the rest. Never a tab the record does not know (it may be the user's). A dry run decides even when Chrome is not
    asked (--no-chrome) or does not answer: from the record alone. Returns the exit code (0)."""
    me = f'{PROG} clean'
    kit.correct()
    d_open, s_ids, now = kit.read_open(), None if no_chrome else kit.chrome_tab_ids(), time.time()
    l_rows, l_close = [], []
    for k, e in sorted(d_open.items(), key=lambda x: x[1].get('opened_ts') or 0):
        if not e.get('device_id'):
            act = 'kept: a headless Chrome, its caller runs'
        elif s_ids is None and not dry:
            act = 'kept: Chrome not reachable (not running, or BLIND)'
        elif s_ids is not None and int(k) not in s_ids:
            act = 'dropped: no longer in Chrome'
        elif e.get('needs_human'):
            act = f'kept: needs a human ({e["needs_human"][:40]})'
        else:
            pid = kit.session(e.get('session_id'), e.get('agent_id') or '').get('claude_pid') or kit.session(e.get('session_id')).get('claude_pid')
            live = kit.claude_alive(pid) if pid else now - (e.get('ts') or 0) < NO_PID_IDLE_S
            act = 'kept: its session runs' if live else 'closed: its session ended, nobody needed'
        l_rows.append([hm(e.get('opened_ts')), (e.get('session_id') or '')[:8], e.get('project'), k, (e.get('url') or '')[:45], act])
        if act.startswith(('dropped', 'closed')) and not dry:
            if act.startswith('closed') and not kit.close_chrome_tab(int(k)):
                l_rows[-1][-1] = 'kept: closing failed'
                continue
            l_close.append({f: e.get(f) for f in kit.FIELDS if f not in ('ts', 'dt', 'reply_to')}
                           | {'event': 'close', 'ts': None, 'message': f'{me}: {act}', 'reply_to': e.get('reply_to')})
    if l_close:
        kit.record(l_close)
    n_old = 0
    s_live = {e.get('session_id') for e in kit.read_open().values()}
    for f in sorted(kit.SESSIONS.glob('*')) if kit.SESSIONS.exists() else []:
        if f.is_file() and now - f.stat().st_mtime > SESSION_KEEP_S and f.name.split('.')[0] not in s_live:
            n_old += 1
            if not dry:
                f.unlink()
    print(f'{me}{" (dry run: nothing changed)" if dry else ""}: {len(l_rows)} tab(s) in the record')
    if l_rows:
        table(['opened', 'session', 'project', 'tab', 'url', 'what clean does'], l_rows)
    print(f'sessions/ files of sessions ended over 30 days ago: {n_old} {"to delete" if dry else "deleted"}')
    l_other = [p for p in kit.chrome_processes() if p['kind'] == 'visible']
    for p in l_other:   # never closed here: they may be the user's
        print(f'not the kit\'s: a visible Chrome, pid {p["pid"]}, data folder {p["data_dir"]} (BLIND: see skill chrome, Leftovers)')
    return 0


# ---------------------------------------------------------------- wait-for-human
WAIT_MAX = 300


def wait_for_human(a, sid: str, aid: str, me: str):
    """Block until a comment for this key's tab arrives (exit 0, printed, marked delivered) or the timeout (exit 2)."""
    t = a.timeout
    if not 1 <= t <= WAIT_MAX:
        sys.exit(f'{me}: --timeout takes 1 to {WAIT_MAX} seconds')
    end = time.monotonic() + t
    while True:
        l_c = kit.take_comments(sid, aid)
        if l_c:
            for c in l_c:
                print(f'{(c.get("dt") or "")[11:16]} UTC, tab {c.get("tab_id")} ({(c.get("url") or "")[:60]}): {c.get("text")}')
            print(f'(from the user, typed in the side panel of your tab; answer on the tab with {PROG} reply-to-human "<text>")')
            sys.exit(0)
        if time.monotonic() >= end:
            print(f'{me}: no comment in {t} s')
            sys.exit(2)
        time.sleep(1)


# ---------------------------------------------------------------- the CLI
def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=PROG, description=__doc__.split('\n')[0],
                                 epilog='Skill chrome. Record: ~/opt/chrome-gateways/state/.')
    ap.add_argument('--agent-id', metavar='ID', help="a subagent's id: the kit's hook adds it to every agent-chrome command "
                                                     'a subagent runs (never type it yourself); else $CHROME_AGENT_ID')
    sub = ap.add_subparsers(dest='cmd', metavar='<subcommand>')
    p = sub.add_parser('authorize-tab', help='say why this session uses Chrome (before opening a tab): shown on the tab',
                       description='Say why this Claude session uses Chrome, and for which project: shown on its tabs. '
                                   'A human who must act is marked after opening the tab: mark-as-needing-human.')
    p.add_argument('why', metavar='WHY', help='why this session uses Chrome, in words the human understands')
    for old in ('--visibility', '--visibility-reason', '--mode'):   # accepted and ignored: callers of before 2026-11-23 (DESIGN.md §1, §2)
        p.add_argument(old, help=argparse.SUPPRESS)
    p.add_argument('--project', metavar='P', help='the project the tab is for: required outside ~/dev/<category>/<repo> and '
                                                  '~/opt/<repo>; inside, <repo> (another value is refused)')
    p = sub.add_parser('mark-as-needing-human', help="a human must act in this session's tab now",
                       description="A human must act in this session's tab now: shown on the tab as NEEDS HUMAN. If nobody acts within 2 h, "
                                   'the kit closes the tab ("expired") and tells the session at its next tool call.')
    p.add_argument('what', metavar='WHAT', help='what the human must do')
    sub.add_parser('mark-as-human-done', help="the human's part is over", description="The human's part is over: NEEDS HUMAN cleared.")
    p = sub.add_parser('reply-to-human', help="answer the human's comment, shown on the tab",
                       description="Answer the human's comment (typed on the tab): shown on this session's tabs.")
    p.add_argument('text', metavar='TEXT', help='your answer')
    p = sub.add_parser('wait-for-human', help="wait for the human's comment on your tab (mode subagents)",
                       description="Block until the human writes in your tab's side panel (mode subagents): prints the "
                                   'comment(s) and marks them delivered. Exit 0: a comment; 2: the timeout. Loop on it '
                                   'while you check your page between calls.')
    p.add_argument('--timeout', type=int, default=30, metavar='SECONDS', help=f'default 30, at most {WAIT_MAX}')
    p = sub.add_parser('status', help='what is open now (agent tabs, Chrome processes), or the history',
                       description='What agents have open now (tabs and Chrome processes), or the history with --since.')
    p.add_argument('--mine', action='store_true', help="only this session's authorized project, else the current folder's "
                                                       '(ask this before opening a tab)')
    p.add_argument('--since', metavar='PERIOD', help='the history over this period: 30m, 12h, 7d')
    p.add_argument('--project', metavar='P', help='only this project')
    p.add_argument('--json', action='store_true', help='JSON')
    p = sub.add_parser('clean', help='close what nobody needs any more, from the record; list the rest',
                       description=clean.__doc__)
    p.add_argument('--dry-run', action='store_true', help='only say what it would do')
    p.add_argument('--no-chrome', action='store_true', help='with --dry-run: from the record alone, without asking Chrome '
                   'for its tabs (the daily job: AppleScript from a LaunchAgent makes macOS ask the user, 2026-11-24)')
    sub.add_parser('profile', help="this session's Chrome profile: its name and deviceId (select_browser)",
                   description="The agent Chrome profile of this session's Claude account ($CLAUDE_ACCOUNT): name and deviceId.")
    p = sub.add_parser('open-profile-window', help="Claude in Chrome's profile not connected: open its window, in the background",
                       description=open_profile_window.__doc__.split('Exits')[0].strip())
    p.add_argument('--project', metavar='P', help="this project instead of the session's authorized one, else the current folder's")
    return ap


def session_desktop() -> int | None:
    """The desktop (macOS space id) of the iTerm2 window that shows this session: its agent tabs go to its Claude
    account's window there (extension/place.js). None off macOS, without an iTerm2 window (the phone), or on error.
    Tests: $CHROME_TEST_DESKTOP (a space id, or empty for none)."""
    if 'CHROME_TEST_DESKTOP' in os.environ:
        v = os.environ['CHROME_TEST_DESKTOP']
        return int(v) if v.isdigit() else None
    if sys.platform != 'darwin':
        return None
    try:
        import desktops as dk
        return dk.session_desktop()[0]
    except Exception:   # noqa: BLE001: no desktop is not a reason to refuse the authorization
        return None


def authorized_project(given: str | None, cwd: str) -> str:
    """--project of authorize-tab: inside ~/dev/<category>/<repo> or ~/opt/<repo> it is <repo> (given or not); elsewhere required."""
    repo = kit.repo_of(cwd)
    if repo and given and given != repo:
        sys.exit(f'{PROG} authorize-tab: refused: --project {given}, but this folder is project {repo} ({cwd}): '
                 f'run it from the folder of {given}, or leave --project out')
    if not (repo or given):
        sys.exit(f'{PROG} authorize-tab: --project is required outside ~/dev/<category>/<repo> and ~/opt/<repo> (here: {cwd}): '
                 'say which project this tab is for')
    return repo or given


def main(argv: list | None = None):
    ap = parser()
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return
    me = f'{PROG} {a.cmd}'
    sid = os.environ.get('CLAUDE_CODE_SESSION_ID')
    try:
        aid = kit.agent_id(a.agent_id or os.environ.get('CHROME_AGENT_ID'))
    except ValueError as e:
        sys.exit(f'{me}: {e}')
    d_sess = kit.session(sid, aid)
    me_key = f'{(sid or "")[:8]}' + (f' (subagent {aid})' if aid else '')
    pwd = os.environ.get('PWD') or ''   # the folder as the shell names it (~/dev/personal/about-me is a link), if it is this one
    cwd = pwd if pwd and Path(pwd).resolve() == Path(os.getcwd()).resolve() else os.getcwd()
    ctx = dict(session_id=sid, agent_id=aid or None, cwd=os.getcwd(), job=os.environ.get('JR_JOB'), project=d_sess.get('project'),
               mode=d_sess.get('mode'))
    if a.cmd == 'status':
        status(a, sid)
        return
    if a.cmd == 'clean':
        if a.no_chrome and not a.dry_run:
            sys.exit(f'{PROG} clean: --no-chrome needs --dry-run (closing a tab needs Chrome)')
        sys.exit(clean(a.dry_run, a.no_chrome))
    if a.cmd == 'profile':   # the one place the agent profiles are written: chrome_kit.D_DEVICE (R18)
        print(f'Claude account {kit.account()}: "{kit.account_profile()}", deviceId {kit.account_device()}')
        return
    if a.cmd == 'open-profile-window':
        open_profile_window(a.project or d_sess.get('project') or kit.project_of(os.getcwd()), sid, os.getcwd(), ctx)
        return
    if not sid:
        sys.exit(f'{me}: {NO_SESSION}')
    if a.cmd == 'authorize-tab':
        project, mode, desk = authorized_project(a.project, cwd), kit.mode_of(aid), session_desktop()
        kit.update_session(sid, aid, purpose=a.why, project=project, mode=mode, desktop=desk, authorized_ts=int(time.time()),
                           claude_pid=kit.claude_ancestor(),
                           visibility=None, visibility_reason=None, visible_because=None)   # (fields of before 2026-11-23)
        ctx.update(project=project, mode=mode, desktop=desk)
        d = dict(purpose=a.why, mode=mode, desktop=desk)
        kit.record([{'event': 'claim', **d, 'needs_human': d_sess.get('needs_human')}], ctx, fanout=d)
        print(f'{me}: recorded for {me_key}, project {project}: {a.why!r}. A human must act in the tab: {PROG} '
              'mark-as-needing-human "<what>" after opening it'
              + (f'. The human answers in the tab\'s side panel: loop on {PROG} wait-for-human while you check the page'
                 if aid else '. The human answers in the terminal (the side panel says so)'))
    elif a.cmd == 'mark-as-needing-human':
        if not d_sess.get('purpose'):
            sys.exit(f'{me}: refused: this session has not said why it uses Chrome: {PROG} authorize-tab "<why>"')
        kit.update_session(sid, aid, needs_human=a.what)
        kit.record([{'event': 'needs_human', 'purpose': d_sess['purpose'], 'needs_human': a.what}], ctx,
                   fanout={'purpose': d_sess['purpose'], 'needs_human': a.what})
        print(f'{me}: recorded for {me_key}: NEEDS HUMAN: {a.what}'
              + f'. If nobody acts, the kit closes it at {hm(time.time() + kit.NEEDS_HUMAN_TTL)} '
                f'({kit.ttl_text()}) and tells this session ("expired").'
              + (f' The human may answer in the side panel: {PROG} wait-for-human' if aid else ''))
    elif a.cmd == 'mark-as-human-done':
        kit.update_session(sid, aid, needs_human=None)
        kit.record([{'event': 'done', 'purpose': d_sess.get('purpose'), 'needs_human': None}], ctx, fanout={'needs_human': None})
        print(f'{me}: recorded for {me_key}: nothing waits for a human any more')
    elif a.cmd == 'reply-to-human':
        kit.record([{'event': 'message', 'purpose': d_sess.get('purpose'), 'needs_human': d_sess.get('needs_human'),
                     'message': a.text}], ctx, fanout={'message': a.text})
        print(f'{me}: recorded for {me_key}: shown on its tab(s)')
    elif a.cmd == 'wait-for-human':
        wait_for_human(a, sid, aid, me)


if __name__ == '__main__':
    main()
