#!/usr/bin/env python3
"""Tests of merge_claude_settings.py (the hook groups in a Claude settings.json) in a scratch HOME: no real settings, no install.
Run: python3 -I agent-gateway/tests/test_merge.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'merge_claude_settings.py'
home = Path(tempfile.mkdtemp(prefix='chrome-gateways-merge-test-'))
settings = home / 'settings.json'
n_fail = 0


def check(name, ok):
    global n_fail
    print(('PASS ' if ok else 'FAIL ') + name)
    n_fail += not ok


def run(mode):
    r = subprocess.run([sys.executable, '-I', str(SCRIPT), mode], capture_output=True, text=True,
                       env={**os.environ, 'HOME': str(home), 'CLAUDE_SETTINGS': str(settings)})
    return r.stdout.strip()


def cmds(d):
    return [h['command'] for l_g in (d.get('hooks') or {}).values() for g in l_g for h in g['hooks']]


FW = {'matcher': '.*', 'hooks': [{'type': 'command', 'command': '[ ! -f "$HOME/opt/agent-firewall/hooks/hook.py" ] || x || true'}]}
OTHER = {'matcher': '', 'hooks': [{'type': 'command', 'command': 'python3 $HOME/opt/agent-tracker/stop.py'}]}
DENY = ['Read(~/Library/Application Support/Google/Chrome/Default/**)', 'Bash(*Chrome/Default*)', 'Bash(rm *)']
start = {'model': 'x', 'permissions': {'deny': DENY}, 'hooks': {'PreToolUse': [FW], 'Stop': [OTHER]}}
settings.write_text(json.dumps(start))

check('new hook not installed: set skips and changes nothing', run('set').startswith('skipped') and json.loads(settings.read_text()) == start)
(home / 'opt/chrome-gateways/agent-gateway').mkdir(parents=True)
(home / 'opt/chrome-gateways/agent-gateway/hook.py').write_text('')
check('new hook installed: set changes', run('set') == 'changed')
d = json.loads(settings.read_text())
c = cmds(d)
check('8 new groups (Mac: Pre 2, Post 1, Prompt 1, Stop 1, SubagentStop 1, SessionStart 1, SessionEnd 1)', sum('opt/chrome-gateways/agent-gateway/hook.py' in x for x in c) == 8)
check("another project's Stop group is kept", OTHER in d['hooks']['Stop'])
check('the firewall group and the other keys are kept', FW in d['hooks']['PreToolUse'] and d['model'] == 'x')
check('deny rules are neither added nor removed here', d['permissions']['deny'] == DENY)
before = settings.read_text()
check('a second set is unchanged (no duplicate)', run('set') == 'unchanged' and settings.read_text() == before)
check('unset removes ours only', run('unset') == 'changed' and sorted(cmds(json.loads(settings.read_text()))) == sorted([FW['hooks'][0]['command'], OTHER['hooks'][0]['command']]))
check('unset again: unchanged', run('unset') == 'unchanged')
settings.unlink()
check('unset on a missing file: absent', run('unset') == 'absent')
print(f'{n_fail} failed')
sys.exit(1 if n_fail else 0)
