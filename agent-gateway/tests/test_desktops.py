#!/usr/bin/env python3
"""Tests of the desktop layer (agent-gateway/desktops.py, for one agent window per account and desktop): the pure choices
with made-up windows, and a read-only look at this Mac's desktops (macOS only). No window is ever opened.
Reads/writes only a temporary $CHROME_STATE and a fake Chrome "Local State". Run: /usr/bin/python3 -I agent-gateway/tests/test_desktops.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent   # agent-gateway/
tmp = Path(tempfile.mkdtemp(prefix='chrome-desktops-test-'))
local_state = tmp / 'Local State'
local_state.write_text(json.dumps({'profile': {'info_cache': {
    'Default': {'name': 'Jean (jean@example.com)'}, 'Profile 1': {'name': 'Claude - Account A'},
    'Profile 2': {'name': 'Claude - LinkedIn'}}}}))
# Chrome is never asked to open a window: `show` would start it with this command, which only leaves a mark (a case
# that is not refused fails below instead of opening a real window: 21-23 Nov 2026, 5 windows in a real profile)
fake_chrome = tmp / 'fake-chrome'
fake_chrome.write_text(f'#!/bin/sh\necho "$@" >> {tmp / "chrome-called"}\n')
fake_chrome.chmod(0o755)
ENV = {**os.environ, 'CHROME_STATE': str(tmp / 'state'), 'CHROME_LOCAL_STATE': str(local_state), 'CHROME_WINDOW_CMD': str(fake_chrome)}
os.environ.update(ENV)   # before the import: chrome_kit reads them once
sys.path[:0] = [str(KIT), str(KIT.parent / 'shared')]
import desktops as dk  # noqa: E402

n_fail = n_pass = 0


def check(name, ok, detail=''):
    global n_fail, n_pass
    n_fail, n_pass = n_fail + (not ok), n_pass + bool(ok)
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  -- {detail}'))



# ---- the windows of Chrome: a frame finds its macOS window and desktop (what the native host does)
l_chrome = [w for w in dk.windows() if w.get('owner') == 'Google Chrome' and dk.spaces_of(w['id'])]
print(f'      (info) Chrome windows on a desktop: {len(l_chrome)}, with a frame another one shares: '
      f'{len(l_chrome) - len({w["rect"] for w in l_chrome})} (those get no desktop: their tabs stay put)')

# ---- this Mac, read-only
lay = dk.layout()
check('desktops read', bool(lay) and sum(v['shown'] for v in lay.values()) >= 1, lay)
sp, rect, _ = dk.session_desktop()
check('this session\'s desktop found (or no iTerm2 window: on the phone)', sp is None or sp in lay, (sp, list(lay)))

check('Chrome was never asked to open a window', not (tmp / 'chrome-called').exists(), (tmp / 'chrome-called').read_text() if (tmp / 'chrome-called').exists() else '')
print(f'{n_pass} passed, {n_fail} failed')
sys.exit(bool(n_fail))
