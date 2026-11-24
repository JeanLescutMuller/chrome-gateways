#!/bin/bash
# Tests install.sh and uninstall.sh in a scratch HOME (no real ~/opt, settings, Chrome or native host; no network, no browser).
# Run: bash shared/tests/test_install.sh
set -uo pipefail
R="$(cd "$(dirname "$0")/../.." && pwd)"
T=$(mktemp -d "${TMPDIR:-/tmp}/chrome-gateways-install-test.XXXXXX")
export HOME="$T/home" AC_NO_LAUNCHCTL=1; mkdir -p "$HOME/.claude"   # never launchctl: it would load the scratch job in the real session
n=0; bad=0
check() { n=$((n+1)); if eval "$2"; then echo "PASS $1"; else echo "FAIL $1"; bad=$((bad+1)); fi; }
echo '{"model":"x"}' > "$HOME/.claude/settings.json"
NMH="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.jeanlescut.agent_tab_notes.json"
if [ "$(uname)" = Darwin ]; then
    bash "$R/install.sh" > "$T/full.log" 2>&1; rc=$?
    P=$HOME/opt/chrome-gateways
    check "install: exit 0" "[ $rc = 0 ]"
    check "install: code deployed in the four folders" "[ -f $P/agent-gateway/hook.py ] && [ -f $P/agent-gateway/extension/manifest.json ] && [ -f $P/script-gateway/launch_headless.py ] && [ -f $P/terminal-links/open_link.py ] && [ -f $P/shared/chrome_kit.py ] && [ -f $P/skills/chrome/SKILL.md ] && [ ! -d $P/agent-gateway/tests ]"
    check "install: links, native host path, hooks" "[ \"\$(readlink $HOME/.local/bin/agent-chrome)\" = $P/agent-gateway/agent_chrome.py ] && [ \"\$(readlink $HOME/.local/bin/open-link)\" = $P/terminal-links/open_link.py ] && [ \"\$(readlink $HOME/.claude/skills/chrome)\" = $P/skills/chrome ] && grep -q 'opt/chrome-gateways/agent-gateway/native_host.py' '$NMH' && grep -q 'opt/chrome-gateways/agent-gateway/hook.py' $HOME/.claude/settings.json && grep -q '\"model\": \"x\"' $HOME/.claude/settings.json"
    check "install: the job's entrypoint and its LaunchAgent (written, not loaded)" "[ -f $P/entrypoint.sh ] && [ \"\$(readlink $HOME/Library/LaunchAgents/com.jeanlescut.chrome-gateways.plist)\" = $P/com.jeanlescut.chrome-gateways.plist ] && grep -q '$P/entrypoint.sh' $P/com.jeanlescut.chrome-gateways.plist"
    check "install: iTerm2 never reached from a scratch HOME (no iTerm2 Python there)" "grep -q 'iTerm2 clicks not set' $T/full.log"
    bash "$R/install.sh" > "$T/again.log" 2>&1
    cp -R "$R" "$T/repo" && echo '// changed' >> "$T/repo/agent-gateway/extension/note.js"
    bash "$T/repo/install.sh" > "$T/nover.log" 2>&1
    check "install: changed extension code without a new version is refused, not deployed" "grep -q 'its version is still' $T/nover.log && ! grep -q '// changed' $P/agent-gateway/extension/note.js"
    check "second run: nothing installed" "! grep -q '^  installed' $T/again.log"
    echo '{}' > "$P/state/open.json"
    bash "$R/uninstall.sh" > "$T/un.log" 2>&1
    check "uninstall: code, links and the job gone, record kept" "[ ! -d $P/agent-gateway ] && [ ! -d $P/script-gateway ] && [ ! -e $HOME/.local/bin/agent-chrome ] && [ ! -e $HOME/.local/bin/open-link ] && [ ! -e '$NMH' ] && [ ! -e $HOME/Library/LaunchAgents/com.jeanlescut.chrome-gateways.plist ] && [ ! -e $P/entrypoint.sh ] && [ -f $P/state/open.json ]"
fi
check "install.sh: unknown option refused" "! bash $R/install.sh --nope >/dev/null 2>&1"
check "install.sh and uninstall.sh: syntax" "bash -n $R/install.sh && bash -n $R/uninstall.sh"
check "no older deploy path in install.sh" "! grep -q 'layer-chrome' $R/install.sh"
echo "$n checks, $bad failed (scratch: $T)"
[ $bad = 0 ]
