"""Sends the user's clicks in iTerm2 to open-link (terminal-links/open_link.py, DESIGN.md §7), in iTerm2's Default profile, live:
  - Semantic History (a clicked file path): "Run command…" open-link \\1
  - one Smart Selection rule (a clicked https:// or file:// link, which Semantic History never sees): "Run Command…"
    open-link \\0, precision Very High; any older rule of ours (its notes name agent-chrome or open-link) is replaced
Through iTerm2's own Python API (Settings → General → Magic → Enable Python API), with the Python iTerm2 ships
(~/Library/Application Support/iTerm2/iterm2env/), so that a running iTerm2 takes it at once and never writes its
old copy back over it (as it would over a `defaults write`). Idempotent. Run by install.sh:
  <iTerm2's python3> -I set_iterm2_clicks.py <path of open-link>
Prints one line; exit 0 written or already so, 1 failed."""
import sys

import iterm2

NOTES = 'Link → open-link (chrome-gateways install.sh)'
REGEX = r'''(https?|file)://[^\s<>"'`]*[^\s<>"'`.,;:!?)\]]'''


async def main(conn):
    cmd = sys.argv[1]
    p = await iterm2.PartialProfile.async_get_default(conn, properties=['Name', 'Guid', 'Semantic History', 'Smart Selection Rules'])
    full = await p.async_get_full_profile()
    l_done = []
    d_sem = dict(p.semantic_history or {})
    d_new = {**d_sem, 'action': 'command', 'text': f'{cmd} \\1'}
    if d_new != d_sem:
        await full.async_set_semantic_history(d_new)
        l_done.append('Semantic History')
    l_rules = list(p.smart_selection_rules or [])
    rule = {'notes': NOTES, 'precision': 'very_high', 'regex': REGEX,
            'actions': [{'title': 'open-link', 'action': 2, 'parameter': f'{cmd} \\0'}]}   # 2: Run Command…
    l_keep = [r for r in l_rules if not any(m in (r.get('notes') or '') for m in ('agent-chrome', 'open-link'))]
    if l_keep + [rule] != l_rules:
        await full.async_set_smart_selection_rules(l_keep + [rule])
        l_done.append('the Smart Selection rule')
    print(f'iTerm2 profile "{p.name}": ' + (' and '.join(l_done) + ' written' if l_done else 'clicks already go to open-link'))


try:
    iterm2.run_until_complete(main, retry=False)
except Exception as e:   # iTerm2 not running, or its Python API off
    print(f'iTerm2 not reached ({type(e).__name__}: {e}): is iTerm2 running, with Settings → General → Magic → Enable Python API?')
    sys.exit(1)
