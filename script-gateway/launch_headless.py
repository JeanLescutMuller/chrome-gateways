#!/usr/bin/env python3
"""The script gateway of chrome-gateways: the one way for code (scripts, tests, scheduled jobs; anything on the NAS) to
start a Chrome (skill chrome). Always headless: no window, ever. It records every tab like the hook does, and reuses what the previous run left open.

- Reuse: a Chrome already running on the same data folder (its DevToolsActivePort answers) is attached, not started
  again; its tab recorded open for the same job (else the same project) is reused, not opened again.
- Recorded (open.json, history/): open, navigate, close; profile = "headless:<data folder>", tab_id = the CDP target
  id, device_id null. Who: $CLAUDE_CODE_SESSION_ID, $JR_JOB, the project of the current folder.
- keep=True leaves the Chrome and its tab for the next run (no human ever acts in a headless tab: no window); otherwise both are closed
  and the close checked (no process left on the data folder).
- A killed caller never leaves Chrome running (keep=False): a watcher process in its own session (it outlives a
  job-runner timeout KILL, which Chrome, in its own session too, also escapes) quits Chrome, checks it is gone and
  records the close as soon as the caller's pid is gone. Model: the retired pwlayer.py `_watch`.
- flags: extra Chrome flags (e.g. ['--disk-cache-size=1']).
- Inside a Claude Code session ($CLAUDE_CODE_SESSION_ID set), the session must have run `agent-chrome authorize-tab
  "<why>"` first (PermissionError otherwise); outside one (scheduled jobs, by hand), `purpose` says why.
- A data folder a visible Chrome (not this launcher's) already uses is refused: a second Chrome on it would hand
  its work to that one, in a window.
Only the standard library (CDP's HTTP endpoints); a caller attaches Playwright to `http://127.0.0.1:<port>` itself.

macOS: Google Chrome; Linux: Chrome for Testing (~/opt/chrome-gateways/bin/chrome-for-testing, or $CHROME_BIN).
Python:  with headless(Path.home() / 'opt/<repo>/chrome', purpose='…', url='https://…', flags=()) as h: ...  # h['port'], h['target_id']
CLI (tests): launch_headless.py --data-dir D --purpose P --url U [--keep] | --close
Reads/writes: the data folder, ~/opt/chrome-gateways/state/ (chrome_kit).
"""
from __future__ import annotations  # macOS /usr/bin/python3 is 3.9: allows "str | None" hints
import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ next to the deployed copy
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'shared')]   # this gateway's modules, then chrome_kit (shared/)
import chrome_kit as kit  # noqa: E402

# Linux (the NAS, 2026-11-22): Chrome for Testing, installed by agent-chrome's install.sh (pinned version and SHA-256 there); resolved, so the command line
# shows .../chrome-linux64/chrome (chrome_kit.RE_CHROME_MAIN)
CHROME = ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' if sys.platform == 'darwin' else
          os.environ.get('CHROME_BIN') or str((Path.home() / 'opt/chrome-gateways/bin/chrome-for-testing').resolve()))
# The user agent a normal Chrome of this system sends (headless says "HeadlessChrome"); Linux: no keyring daemon on a
# server, so the basic password store, the same on every run (a kept data folder's cookies stay readable)
UA_OS, OS_FLAGS = (('Macintosh; Intel Mac OS X 10_15_7', []) if sys.platform == 'darwin' else
                   ('X11; Linux x86_64', ['--password-store=basic']))


def cdp(port: int, path: str, method: str = 'GET'):
    with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}', method=method), timeout=5) as r:
        body = r.read().decode()
    return json.loads(body) if body.strip().startswith(('{', '[')) else body


def pids(data_dir: Path) -> list[int]:
    r = subprocess.run(['pgrep', '-f', f'user-data-dir={data_dir}( |$)'], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split()]


def running_port(data_dir: Path) -> int | None:
    """The port of a Chrome already running on this data folder, if it still answers."""
    f = data_dir / 'DevToolsActivePort'
    if not (pids(data_dir) and f.exists() and f.read_text().strip()):
        return None
    port = int(f.read_text().split()[0])
    with contextlib.suppress(OSError):
        cdp(port, '/json/version')
        return port
    return None


def busy(data_dir: Path, visible_only: bool = False):
    """Refuse a data folder that another Chrome holds but this launcher must not or cannot attach to: a visible one
    (a login window, a script's), or (visible_only=False) one whose DevTools port does not answer. Starting a second
    Chrome on it would only hand the work to that one."""
    l_p = [p for p in kit.chrome_processes() if p['data_dir'] and Path(p['data_dir']).resolve() == data_dir
           and (p['kind'] == 'visible' or not visible_only)]
    if l_p:
        p = l_p[0]
        raise RuntimeError(f'Chrome data folder {data_dir} is already used by a {p["kind"]} Chrome (pid {p["pid"]}) that '
                           'the launcher did not start or cannot attach to: quit it first (cmd+Q in its window, or '
                           f'`kill {p["pid"]}`), then run again. A second Chrome on the same folder would hand its work to it.')


def mock_keychain(data_dir: Path) -> list[str]:
    """['--use-mock-keychain'] for a throwaway data folder (under a temporary folder) only: it never asks the macOS
    keychain for "Chrome Safe Storage" (from an agent's sandboxed shell it cannot reach it, and macOS showed "Keychain
    Not Found ... Chrome", the user, 2026-11-07). Never for a kept folder (~/opt/<repo>/chrome): its logins were saved
    by a visible Chrome with the real keychain, and a mock key cannot read them, so every cookie was lost (the
    engine of marketplace-seller "logged out of Facebook" from 2026-11-07 to 2026-11-09)."""
    d = data_dir.resolve()
    roots = {Path(tempfile.gettempdir()).resolve(), Path('/private/tmp'), Path('/private/var/folders')}
    return ['--use-mock-keychain'] if any(r in d.parents for r in roots) else []


def start(data_dir: Path, flags=()) -> int:
    busy(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / 'DevToolsActivePort').unlink(missing_ok=True)
    major = re.search(r'(\d+)\.', subprocess.run([CHROME, '--version'], capture_output=True, text=True).stdout).group(1)
    ua = f'Mozilla/5.0 ({UA_OS}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36'
    subprocess.Popen([CHROME, '--headless', f'--user-data-dir={data_dir}', '--remote-debugging-port=0', '--no-first-run',
                      '--no-default-browser-check', *mock_keychain(data_dir), *OS_FLAGS, f'--user-agent={ua}', '--window-size=1440,900',
                      '--disable-blink-features=AutomationControlled', *flags, 'about:blank'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)  # outlives us if keep
    for _ in range(120):
        if (port := running_port(data_dir)):
            return port
        time.sleep(0.25)
    raise RuntimeError(f'headless Chrome did not start on {data_dir}')


def stop(data_dir: Path, port: int | None):
    """Quit Chrome on this data folder and check no process is left (skill chrome)."""
    with contextlib.suppress(OSError):
        if port:
            for t in cdp(port, '/json/list'):
                cdp(port, f'/json/close/{t["id"]}')  # closing the last page quits a headless Chrome
    for _ in range(40):
        if not pids(data_dir):
            return
        time.sleep(0.25)
    for pid in pids(data_dir):  # still there: SIGTERM = a normal quit, cookies and logins stay
        subprocess.run(['kill', str(pid)], capture_output=True)  # helpers exit with the main process: may be gone
    time.sleep(2)
    if pids(data_dir):
        raise RuntimeError(f'Chrome still running on {data_dir}: {pids(data_dir)}')


KEYCHAIN_LOG = kit.STATE / 'keychain-dialogs.jsonl'


def keychain_dialog(data_dir: Path, w: dict, phase: str, s_seen: set) -> None:
    """Record (once per phase) a keychain dialog shown while this throwaway Chrome runs, or just after it quit:
    macOS showed "Keychain Not Found ... Chrome" on 2026-11-07 14:28 and 2026-11-11 10:45, each time just after an
    agent's headless Chrome, and it went away by itself; 4 tries to reproduce it failed (the user, 2026-11-11).
    SecurityAgent is the macOS process that shows keychain dialogs. Writes: KEYCHAIN_LOG."""
    if phase in s_seen or not subprocess.run(['pgrep', '-x', 'SecurityAgent'], capture_output=True).stdout:
        return
    s_seen.add(phase)
    l_ps = [subprocess.run(['ps', '-o', 'pid=,command=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
            for pid in pids(data_dir)]
    ts = int(time.time())
    with contextlib.suppress(OSError), open(KEYCHAIN_LOG, 'a') as f:
        f.write(json.dumps({'ts': ts, 'dt': kit.utc(ts), 'phase': phase, 'data_dir': str(data_dir),
                            'chrome': [x[:600] for x in l_ps if x], **w['ctx']}) + '\n')


def watch():
    """`launch_headless.py _watch` (env CHROME_WATCH: caller pid, data folder, port, context): while Chrome runs on
    the folder, check every second that the caller is alive; once it is gone (killed, crashed), quit Chrome, check
    it is gone, and record the close of the tabs still recorded open on it. Also records a keychain dialog seen
    while Chrome runs or within 5 s after it quit (keychain_dialog)."""
    w = json.loads(os.environ['CHROME_WATCH'])
    data_dir = Path(w['data_dir'])
    s_seen = set()
    while pids(data_dir):
        keychain_dialog(data_dir, w, 'while Chrome runs', s_seen)
        if os.getppid() != w['caller']:  # reparented: the caller is gone (a reused pid cannot fool this)
            with contextlib.suppress(Exception):
                stop(data_dir, w['port'])
            l_close = [{'event': 'close', 'tab_id': e['tab_id'], 'url': e.get('url'), 'needs_human': None}
                       for e in kit.read_open().values() if e.get('profile') == w['ctx']['profile']]
            if l_close:
                kit.record(l_close, w['ctx'])
            return
        time.sleep(1)
    for _ in range(5):
        keychain_dialog(data_dir, w, 'after Chrome quit', s_seen)
        time.sleep(1)


@contextlib.contextmanager
def headless(data_dir: Path, purpose: str, url: str = 'about:blank', keep: bool = False, flags=()):
    sid = os.environ.get('CLAUDE_CODE_SESSION_ID')
    d_sess = kit.session(sid)
    if sid and not d_sess.get('purpose'):  # inside a Claude session: it must have said why (shown in `agent-chrome status`)
        raise PermissionError(
            f'launch_headless: this Claude session ({sid[:8]}) has not said why it uses Chrome. Run first: agent-chrome '
            'authorize-tab "<why>" [--project P] (skill chrome). Scheduled jobs and scripts run by hand (no '
            '$CLAUDE_CODE_SESSION_ID) need nothing.')
    data_dir = Path(data_dir).resolve()
    profile = f'headless:{data_dir}'
    ctx = dict(session_id=sid, cwd=os.getcwd(), job=os.environ.get('JR_JOB'), project=d_sess.get('project'),
               profile=profile, purpose=purpose)
    project = d_sess.get('project') or kit.project_of(ctx['cwd'])
    busy(data_dir, visible_only=True)  # never attach to a visible Chrome (it may answer CDP: pwlayer's does)
    port = running_port(data_dir)
    reused = port is not None
    port = port or start(data_dir, flags)
    if not keep:  # the watcher: a killed caller's Chrome is quit and recorded closed
        subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()), '_watch'], start_new_session=True,
                         env={**os.environ, 'CHROME_WATCH': json.dumps({'caller': os.getpid(), 'data_dir': str(data_dir),
                                                                        'port': port, 'ctx': ctx})},
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # the previous run's tab: recorded open on this data folder for this job (else this project), still a page here
    s_live = {t['id'] for t in cdp(port, '/json/list') if t.get('type') == 'page'}
    l_mine = [e for e in kit.read_open().values() if e.get('profile') == profile and e.get('tab_id') in s_live
              and (e.get('job') == ctx['job'] if ctx['job'] else e.get('project') == project)]
    if l_mine:
        tid = l_mine[-1]['tab_id']
        kit.record([{'event': 'navigate', 'tab_id': tid, 'url': url}], ctx)
    else:
        tid = cdp(port, f'/json/new?{url}', 'PUT')['id']
        kit.record([{'event': 'open', 'tab_id': tid, 'url': url}], ctx)
    try:  # a reused tab keeps its page: the caller's Playwright sends it to `url` (CDP's HTTP API cannot navigate)
        yield {'port': port, 'target_id': tid, 'reused': reused, 'reused_tab': bool(l_mine)}
    finally:
        if not keep:
            kit.record([{'event': 'close', 'tab_id': tid, 'url': url, 'needs_human': None}], ctx)
            stop(data_dir, port)


def main():
    if sys.argv[1:2] == ['_watch']:
        watch()
        return
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True, type=Path)
    ap.add_argument('--purpose', default='test')
    ap.add_argument('--url', default='about:blank')
    ap.add_argument('--keep', action='store_true', help='leave Chrome and the tab for the next run')
    ap.add_argument('--close', action='store_true', help='close what a --keep run left, and record it')
    ap.add_argument('--flag', action='append', default=[], help='an extra Chrome flag (repeatable)')
    ap.add_argument('--hold', type=float, default=0, help='tests: stay inside headless() this many seconds')
    a = ap.parse_args()
    if a.close:
        port = running_port(a.data_dir.resolve())
        l_close = [{'event': 'close', **{k: e.get(k) for k in ('profile', 'tab_id', 'url', 'purpose', 'job', 'session_id')}}
                   for e in kit.read_open().values() if e.get('profile') == f'headless:{a.data_dir.resolve()}']
        if l_close:
            kit.record(l_close, {'cwd': os.getcwd()})
        stop(a.data_dir.resolve(), port)
        print(json.dumps({'closed': True, 'pids_left': pids(a.data_dir.resolve())}))
        return
    with headless(a.data_dir, a.purpose, a.url, keep=a.keep, flags=a.flag) as h:
        print(json.dumps(h), flush=True)
        time.sleep(a.hold)


if __name__ == '__main__':
    main()
