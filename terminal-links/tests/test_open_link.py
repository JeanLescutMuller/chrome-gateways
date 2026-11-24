#!/usr/bin/env python3
"""Tests of open-link (terminal-links/open_link.py): which Chrome profile a click opens, or `open`. Never the real Chrome,
iTerm2, tmux or `open`: $CHROME_WINDOW_CMD and $OPEN_CMD are fakes that only write what they were asked; the clicked pane
is $OPEN_LINK_PANE; the record is a temporary $CHROME_STATE; Chrome's profiles a fake "Local State".
Run: python3 -I terminal-links/tests/test_open_link.py"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'open_link.py'
tmp = Path(tempfile.mkdtemp(prefix='open-link-test-'))
local_state = tmp / 'Local State'
local_state.write_text(json.dumps({'profile': {'info_cache': {
    'Default': {'name': 'Jean'}, 'Profile 3': {'name': 'Claude - Account A'}, 'Profile 9': {'name': 'Claude - Account B'}}}}))
asked = tmp / 'asked'
fake = tmp / 'fake'
fake.write_text(f'#!/bin/sh\necho "$(basename "$0") $*" >> {asked}\n')
fake.chmod(0o755)
(tmp / 'chrome').symlink_to(fake)
(tmp / 'open').symlink_to(fake)
ENV = {k: v for k, v in os.environ.items() if k != 'CLAUDE_CODE_SESSION_ID'}   # the user's click: no Claude session
ENV.update(CHROME_STATE=str(tmp / 'state'), CHROME_LOCAL_STATE=str(local_state), CHROME_WINDOW_CMD=str(tmp / 'chrome'),
           OPEN_CMD=str(tmp / 'open'), OPEN_LINK_PANE='')
page = tmp / 'p.html'
page.write_text('<title>t</title>')
n_fail = n_pass = 0


def check(name, ok, detail=''):
    global n_fail, n_pass
    n_fail, n_pass = n_fail + (not ok), n_pass + bool(ok)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  -- {detail}'))


def click(target, pane='', **env):
    asked.unlink(missing_ok=True)
    r = subprocess.run([sys.executable, '-IB', str(SCRIPT), target], capture_output=True, text=True,
                       env={**ENV, 'OPEN_LINK_PANE': pane, **env})
    for _ in range(30):   # Chrome is started detached: wait for its fake to write (up to 3 s)
        if asked.exists() and asked.read_text().endswith('\n'):
            break
        time.sleep(0.1)
    return r, asked.read_text().strip() if asked.exists() else ''


ART = 'https://claude.ai/artifact/abc'
me = os.getpid()   # this test runs under a pane-like process tree with no claude in it
r, a = click(ART, f'{me}\ta')
check('a claude.ai link, no claude process in the pane: your own profile', a == f'chrome --profile-directory=Default {ART}', a)
fake_claude = tmp / 'claude'
fake_claude.symlink_to('/bin/sleep')   # a process whose command is .../claude: the pane's Claude session (a copy of a system binary is killed)
cl = subprocess.Popen([str(fake_claude), '5'])
try:
    r, a = click(ART, f'{cl.pid}\tb')
    check('a claude.ai link in a Claude pane of account b: profile "Claude - Account B"', a == f'chrome --profile-directory=Profile 9 {ART}', a)
    r, a = click('https://example.com/x', f'{cl.pid}\tb')
    check('any other web link, even in a Claude pane: your own profile', a == 'chrome --profile-directory=Default https://example.com/x', a)
finally:
    cl.kill()
r, a = click(str(page))
check('an HTML file: Chrome, your own profile', a == f'chrome --profile-directory=Default {page.resolve().as_uri()}', a)
r, a = click(str(tmp / 'notes.txt'))
check('any other file: open', a == f'open {(tmp / "notes.txt").resolve()}', a)
r, a = click('file:///tmp/archive.zip')
check('a file:// link to a file that is not a page: open', a == 'open file:///tmp/archive.zip', a)
r, a = click(ART, CLAUDE_CODE_SESSION_ID='sess-1')
check('run by an agent (a Claude session): refused, nothing opened', r.returncode != 0 and a == '', r.stderr + a)
log = (tmp / 'state/clicks.log').read_text()
check('every click logged, with why', log.count('\n') == 6 and 'claude.ai link in a Claude pane of account b' in log, log)
print(f'{n_pass} passed, {n_fail} failed')
sys.exit(bool(n_fail))
