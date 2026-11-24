#!/bin/bash
# Removes what chrome-gateways/install.sh made, except the record ~/opt/chrome-gateways/state/ (kept: it is the history).
#   bash ~/dev/agents/chrome-gateways/uninstall.sh
# The hook groups go (only ours). The extension stays loaded in the agent profiles until the user removes it there
# (chrome://extensions); iTerm2's clicks still run open-link until the user changes them back (said at the end).
set -uo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
P="$HOME/opt/chrome-gateways"
for f in "$HOME/.claude/settings.json" "$HOME"/.claude/account-*/settings.json; do
    [ -f "$f" ] && [ ! -L "$f" ] && echo "  ${f/#$HOME/~} hooks: $(CLAUDE_SETTINGS="$f" python3 -I "$SRC/agent-gateway/merge_claude_settings.py" unset)"
done
NMH="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.jeanlescut.agent_tab_notes.json"
grep -q "$P/agent-gateway/native_host.py" "$NMH" 2>/dev/null && rm "$NMH" && echo "  removed $NMH"
[ "$(readlink "$HOME/.local/bin/agent-chrome")" = "$P/agent-gateway/agent_chrome.py" ] && rm "$HOME/.local/bin/agent-chrome" && echo "  removed ~/.local/bin/agent-chrome"
[ "$(readlink "$HOME/.local/bin/open-link")" = "$P/terminal-links/open_link.py" ] && rm "$HOME/.local/bin/open-link" && echo "  removed ~/.local/bin/open-link"
for home in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
    [ "$(readlink "$home/chrome")" = "$P/skills/chrome" ] && rm "$home/chrome" && echo "  removed $home/chrome"
done
[ -d "$P/skills" ] && chmod -R u+w "$P/skills" && rm -r "$P/skills" && echo "  removed $P/skills"
for d in agent-gateway script-gateway terminal-links shared bin; do [ -d "$P/$d" ] && rm -r "$P/$d" && echo "  removed $P/$d"; done
for d in "$P"/chrome-*/; do [ -d "$d" ] && rm -r "${d%/}" && echo "  removed ${d%/}"; done
NAME=com.jeanlescut.chrome-gateways
if [ -e "$HOME/Library/LaunchAgents/$NAME.plist" ] || [ -L "$HOME/Library/LaunchAgents/$NAME.plist" ]; then
    [ "${AC_NO_LAUNCHCTL:-}" = 1 ] || launchctl bootout "gui/$(id -u)/$NAME" 2> /dev/null || true
    rm "$HOME/Library/LaunchAgents/$NAME.plist" && echo "  removed the LaunchAgent $NAME"
fi
[ -f "$P/$NAME.plist" ] && rm "$P/$NAME.plist"
[ -f "$P/entrypoint.sh" ] && rm "$P/entrypoint.sh"
echo "  kept $P/state (the record)"
[ "$(uname -s)" = Darwin ] && echo "  NOTE: iTerm2's clicks still run open-link (Settings → Profiles → Default → Advanced: Semantic History, Smart Selection): set them back by hand"
exit 0
