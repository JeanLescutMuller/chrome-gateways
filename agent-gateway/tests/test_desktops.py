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



# ---- pure choices
l_cg = [{'id': 1, 'rect': (0, 0, 800, 600)}, {'id': 2, 'rect': (10, 10, 800, 600)}, {'id': 3, 'rect': (20, 20, 800, 600)}]
G = 'Claude - Account A'
B = 'Claude - Account B'
d_win = {1: {'project': 'websites', 'profile': G}, 2: {'project': 'tasks', 'profile': G}, 3: {'project': 'websites', 'profile': B}}
d_sp = {1: [200], 2: [100], 3: [100]}
check("reuse: the profile's window on this desktop, whatever its project (one per profile and desktop)", (dk.pick(l_cg, d_win, G, 100, d_sp) or {}).get('id') == 2)
check("never another profile's window on the same desktop", dk.pick(l_cg, {3: d_win[3]}, G, 100, d_sp) is None)
check("never the profile's window on another desktop", dk.pick(l_cg, {1: d_win[1]}, G, 100, d_sp) is None)
check('never a window the kit did not open', dk.pick(l_cg, {}, G, 100, d_sp) is None)
check('AppleScript id by rect', dk.as_id_of((10, 10, 800, 600), [{'as_id': 7, 'rect': (10, 10, 800, 600)}]) == 7)
check('new window by rect, old ones excluded', (dk.cg_of((0, 0, 800, 600), l_cg + [{'id': 9, 'rect': (0, 0, 800, 600)}], {1}) or {}).get('id') == 9)

# ---- this Mac, read-only
lay = dk.layout()
check('desktops read', bool(lay) and sum(v['shown'] for v in lay.values()) >= 1, lay)
sp, rect, _ = dk.session_desktop()
check('this session\'s desktop found (or no iTerm2 window: on the phone)', sp is None or sp in lay, (sp, list(lay)))

check('Chrome was never asked to open a window', not (tmp / 'chrome-called').exists(), (tmp / 'chrome-called').read_text() if (tmp / 'chrome-called').exists() else '')
print(f'{n_pass} passed, {n_fail} failed')
sys.exit(bool(n_fail))
