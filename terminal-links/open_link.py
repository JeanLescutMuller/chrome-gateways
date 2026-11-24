#!/usr/bin/env python3
"""open-link: what a click on a link or a path in iTerm2 opens (terminal-links, REQUIREMENTS.md R16). Run by iTerm2
(Semantic History for a file path, a Smart Selection rule for an https:// or file:// link: set_iterm2_clicks.py),
never by an agent:
  - a claude.ai link (an Artifact…), clicked in a tmux pane where a Claude session runs → Chrome, in the profile of
    that session's Claude account ("Claude - Account A" or B): claude.ai shows it only to that account
  - any other web link, and an HTML or Markdown file → Chrome, in the user's own profile
  - any other file or folder → as macOS opens it (`open`)
Chrome gets the link as an argument of its binary with --profile-directory: a new tab in that profile's last window
(a new window when it has none). The pane's account: the tmux option @claude_account, set by the agent gateway's hook
at the session's start, trusted only while a claude process still runs in that pane (a crash leaves the option).
Never fails silently: each click is a line in ~/opt/chrome-gateways/state/clicks.log; on any error, `open`.
Usage: open-link <path or URL>. Tests: $CHROME_WINDOW_CMD replaces Chrome; $OPEN_LINK_PANE ("<pid>\t<account>")
replaces iTerm2 and tmux; $OPEN_CMD replaces open."""
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / 'shared')]
import chrome_kit as kit  # noqa: E402

CHROME_BIN = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
OWN_FOLDER = 'Default'   # the user's own profile: opened here only by the user's own click
PAGES = ('.html', '.htm', '.md', '.markdown')
LOG = kit.STATE / 'clicks.log'
TMUX = shutil.which('tmux') or next((p for p in ('/opt/homebrew/bin/tmux', '/usr/local/bin/tmux') if os.path.exists(p)), 'tmux')


def pane() -> tuple:
    """(pid of the clicked pane's shell, its @claude_account) of the tmux pane shown in iTerm2's current session."""
    if 'OPEN_LINK_PANE' in os.environ:
        return tuple((os.environ['OPEN_LINK_PANE'].split('\t') + [''])[:2])
    tty = subprocess.run(['osascript', '-e', 'if application "iTerm2" is running then tell application "iTerm2" to '
                          'get tty of current session of current window'], capture_output=True, text=True).stdout.strip()
    if not tty:
        return '', ''
    r = subprocess.run([TMUX, 'display', '-p', '-c', tty, '#{pane_pid}\t#{@claude_account}'], capture_output=True, text=True)
    return tuple((r.stdout.rstrip('\n').split('\t') + [''])[:2]) if r.returncode == 0 else ('', '')


def claude_runs(pid: str) -> bool:
    """Does a Claude Code process run under this pid (the pane's shell)? Its command: claude, or .../claude/versions/<v>."""
    if not pid.isdigit():
        return False
    out = subprocess.run(['ps', '-A', '-o', 'pid=,ppid=,comm='], capture_output=True, text=True).stdout
    d_kids, d_comm = {}, {}
    for line in out.splitlines():
        p = line.split(None, 2)
        if len(p) == 3 and p[0].isdigit() and p[1].isdigit():
            d_kids.setdefault(p[1], []).append(p[0])
            d_comm[p[0]] = p[2]
    l_todo, seen = [pid], set()
    while l_todo:
        x = l_todo.pop()
        if x in seen:
            continue
        seen.add(x)
        c = d_comm.get(x, '')
        if '/claude/versions/' in c or c.rsplit('/', 1)[-1] == 'claude':
            return True
        l_todo += d_kids.get(x, [])
    return False


def decide(target: str) -> tuple:
    """(how, folder or None, url or path, why): how = 'chrome' (with a profile folder) or 'open'."""
    if re.match(r'https?://', target):
        url = target
    elif target.startswith('file://'):
        url = target
        if Path(re.sub(r'^file://', '', target).split('#')[0]).suffix.lower() not in PAGES:
            return 'open', None, target, 'a file that is not a page'
    else:
        path = Path(target).expanduser().resolve()
        if path.is_dir() or path.suffix.lower() not in PAGES:
            return 'open', None, str(path), 'not a page'
        url = path.as_uri()
    if re.match(r'https://([a-z0-9-]+\.)?claude\.ai(/|$)', url):
        pid, acct = pane()
        if acct and claude_runs(pid):
            folder = kit.profile_folders().get(kit.account_profile(acct))
            if folder and folder != OWN_FOLDER:
                return 'chrome', folder, url, f'claude.ai link in a Claude pane of account {acct}'
            return 'chrome', OWN_FOLDER, url, f'claude.ai link, account {acct} has no Chrome profile here'
    return 'chrome', OWN_FOLDER, url, 'your own profile'


def main(target: str) -> int:
    try:
        how, folder, what, why = decide(target)
        if how == 'chrome':
            subprocess.Popen([os.environ.get('CHROME_WINDOW_CMD') or CHROME_BIN, f'--profile-directory={folder}', what],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        else:
            subprocess.run([os.environ.get('OPEN_CMD') or 'open', what])
        line = f'{how} {folder or ""} ({why})'
    except Exception as e:   # noqa: BLE001: the click must still open something
        subprocess.run([os.environ.get('OPEN_CMD') or 'open', target])
        line = f'open (error: {e!r})'
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'a') as f:
        f.write(f'{kit.utc(int(time.time()))} {target}: {line}\n')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2 or os.environ.get('CLAUDE_CODE_SESSION_ID'):
        sys.exit('open-link <path or URL>: run by iTerm2 for the user\'s clicks, never by an agent')
    sys.exit(main(sys.argv[1]))
