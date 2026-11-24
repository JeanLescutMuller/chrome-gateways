#!/usr/bin/env python3
"""Adds or removes the Chrome kit's hook groups in a Claude settings.json, touching nothing else.

`hooks` is shared (skill config-ownership): ours are the groups whose command contains MARK (~/opt/chrome-gateways). `set`
replaces them (a re-run never adds a second one); `unset` removes them. (The former deploys' groups, ~/opt/layer-chrome and
~/opt/my-setup/chrome, were replaced on 2026-11-23: none is left on the Mac or the NAS.)
The command checks the file first: a missing script would make python exit 2, which Claude Code reads as "block this
tool call"; `|| true` keeps the hook failing open.

The groups are added only when ~/opt/chrome-gateways/agent-gateway/hook.py exists (else nothing changes).
The deny rules on the user's own Chrome profile (Default) are no longer written here: agent-firewall's deny/ owns them
(since the 2026-11 restructure; those already in settings.json are left as they are).

Usage: merge_claude_settings.py set|unset. Env: CLAUDE_SETTINGS (default ~/.claude/settings.json); HOME (where ~/opt/chrome-gateways is
looked for). Prints changed, unchanged, absent or skipped (new hook not installed).
"""
import json
import os
import sys
from pathlib import Path

MARK = 'opt/chrome-gateways/agent-gateway/hook.py'
COMMAND = '[ ! -f "$HOME/opt/chrome-gateways/agent-gateway/hook.py" ] || python3 -I "$HOME/opt/chrome-gateways/agent-gateway/hook.py" || true'
GROUPS = {  # event -> matchers
    'PreToolUse': ['mcp__claude-in-chrome__.*', 'Bash'],
    'PostToolUse': ['mcp__claude-in-chrome__.*'],
    'UserPromptSubmit': [''],
    'Stop': [''],
    'SubagentStop': [''],
    'SessionStart': [''],   # the pane's Claude account, for the user's clicks (DESIGN.md §7)
    'SessionEnd': [''],
}


def is_ours(g, marks) -> bool:
    return isinstance(g, dict) and any(m in str(h.get('command', '')) for m in marks
                                       for h in g.get('hooks') or [] if isinstance(h, dict))


def merge(d: dict, mode: str, new_hook_installed: bool) -> dict:
    """The settings dict after `set` or `unset`; the input is not modified."""
    hooks = d.get('hooks') or {}
    if mode == 'set' and not new_hook_installed:
        return d
    new = {ev: [g for g in l_g if not is_ours(g, [MARK])] for ev, l_g in hooks.items()}
    if mode == 'set':
        hook = {'type': 'command', 'command': COMMAND, 'timeout': 10}
        for ev, l_m in GROUPS.items():
            new.setdefault(ev, []).extend({'matcher': m, 'hooks': [hook]} for m in l_m)
    new = {ev: l_g for ev, l_g in new.items() if l_g}
    out = dict(d)
    if new:
        out['hooks'] = new
    else:
        out.pop('hooks', None)
    return out


def main(argv: list) -> int:
    mode = argv[1] if len(argv) > 1 else ''
    if mode not in ('set', 'unset'):
        print(__doc__)
        return 2
    f = Path(os.environ.get('CLAUDE_SETTINGS') or Path.home() / '.claude' / 'settings.json').resolve()  # a link: write its target
    if not f.exists():
        if mode == 'unset':
            print('absent')
            return 0
        d = {}
    else:
        d = json.loads(f.read_text())
    installed = (Path.home() / MARK).is_file()
    if mode == 'set' and not installed:
        print('skipped (no ~/opt/chrome-gateways/agent-gateway/hook.py)')
        return 0
    out = merge(d, mode, installed)
    if out == d:
        print('unchanged')
        return 0
    tmp = f.with_name(f.name + '.tmp')
    tmp.write_text(json.dumps(out, indent=2) + '\n')
    os.replace(tmp, f)
    print('changed')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
