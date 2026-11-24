#!/bin/bash
# Deploys chrome-gateways on this machine (idempotent: safe to re-run; no sudo).
#   bash ~/dev/agents/chrome-gateways/install.sh
# Makes, in P=~/opt/chrome-gateways (the repo's folders, without tests/):
#   agent-gateway/*.py, extension/  the hook, the agent-chrome command, the native host, desktops (macOS); the extension
#                                   "Agent tab notes", loaded once per agent profile by the user (Load unpacked)
#   agent-gateway/skills/chrome     -> P/skills/chrome, linked from ~/.claude/skills and ~/.agents/skills
#   script-gateway/*.py             the launcher (Mac and NAS)
#   terminal-links/*.py             open-link, the user's clicks in iTerm2 (macOS)
#   shared/*.py                     chrome_kit: the record, the profiles
#   P/state/                        the record: open.json, history/, comments.jsonl, sessions/, windows/ (kept across installs
#                                   and by uninstall.sh; readable by av-vault: agent-vault's vault-type reads open.json, so P is 755)
#   ~/.local/bin/agent-chrome -> P/agent-gateway/agent_chrome.py ; macOS: ~/.local/bin/open-link -> P/terminal-links/open_link.py
#   macOS: the hook groups in every Claude account's settings.json (agent-gateway/merge_claude_settings.py); the native host
#     manifest (Chrome's NativeMessagingHosts folder, read by every profile); iTerm2's clicks -> open-link, in its Default
#     profile, live (terminal-links/set_iterm2_clicks.py, iTerm2's Python API; a NOTE when iTerm2 is not reached);
#     the daily job chrome-gateways: shared/clean_job.sh -> P/entrypoint.sh, LaunchAgent com.jeanlescut.chrome-gateways
#     (P/com.jeanlescut.chrome-gateways.plist linked from ~/Library/LaunchAgents; a tick every hour). Tests: AC_NO_LAUNCHCTL=1
#   Linux (the NAS: the script gateway only): Chrome for Testing (pinned below, SHA-256 checked) -> P/chrome-<version>/,
#     P/bin/chrome-for-testing
set -uo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
OS=$(uname -s)
P="$HOME/opt/chrome-gateways"
for a in "$@"; do
    case "$a" in
        -h|--help) sed -n 2,3p "$0"; exit 0 ;;
        *) echo "unknown option: $a (see: bash $0 --help)" >&2; exit 2 ;;
    esac
done
ok() { printf '  ok         %s\n' "$1"; }
installed() { printf '  installed  %s\n' "$1"; }
fail() { printf '  FAILED     %s\n' "$1"; FAILED=1; }
FAILED=0
[ "$OS" = Darwin ] || [ "$OS" = Linux ] || { ok "not macOS or Linux: nothing to do"; exit 0; }
mkdir -p "$P" "$HOME/.local/bin" && chmod 755 "$P"

echo "record"
mkdir -p "$P/state" && ok "$P/state"

echo "code"
# copy to a temporary name, then rename: a hook running right now never reads half a file
deploy_dir() {  # deploy_dir <src folder> <dst folder> <glob>: the files of glob, one by one; a file gone from src is removed
    local s="$1" d="$2" g="$3" f changed=0
    mkdir -p "$d"
    for f in "$d"/$g; do [ -f "$f" ] && [ ! -f "$s/${f##*/}" ] && rm "$f" && changed=1; done
    for f in "$s"/$g; do
        [ -f "$f" ] || continue
        cmp -s "$f" "$d/${f##*/}" && continue
        cp "$f" "$d/.${f##*/}.tmp" && mv "$d/.${f##*/}.tmp" "$d/${f##*/}" && changed=1
    done
    if [ $changed = 1 ]; then installed "$d"; else ok "$d"; fi
}
deploy_dir "$SRC/shared" "$P/shared" '*.py'
deploy_dir "$SRC/script-gateway" "$P/script-gateway" '*.py'
deploy_dir "$SRC/agent-gateway" "$P/agent-gateway" '*.py'   # on Linux too: agent-chrome status and clean
chmod +x "$P/agent-gateway/agent_chrome.py" "$P/script-gateway/launch_headless.py"
ln -sfn "$P/agent-gateway/agent_chrome.py" "$HOME/.local/bin/agent-chrome" && ok "$HOME/.local/bin/agent-chrome"
if [ "$OS" = Darwin ]; then
    # changed extension code must carry a new version: the user checks it in chrome://extensions after the reload
    ext_ver() { sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$1/manifest.json" 2>/dev/null; }
    ver_old=$(ext_ver "$P/agent-gateway/extension") ver_new=$(ext_ver "$SRC/agent-gateway/extension")
    if diff -rq "$SRC/agent-gateway/extension" "$P/agent-gateway/extension" > /dev/null 2>&1; then ok "$P/agent-gateway/extension ($ver_new)"
    elif [ -n "$ver_old" ] && [ "$ver_old" = "$ver_new" ]; then
        fail "extension code changed but its version is still $ver_new: raise \"version\" in agent-gateway/extension/manifest.json (not deployed)"
    else
        deploy_dir "$SRC/agent-gateway/extension" "$P/agent-gateway/extension" '*'
        printf '  NOTE       extension %s -> %s: click its reload button in chrome://extensions of each agent profile, check it shows %s\n' "${ver_old:-none}" "$ver_new" "$ver_new"
    fi
    deploy_dir "$SRC/terminal-links" "$P/terminal-links" '*.py'
    chmod +x "$P/agent-gateway/hook.py" "$P/agent-gateway/native_host.py" "$P/terminal-links/open_link.py"
    ln -sfn "$P/terminal-links/open_link.py" "$HOME/.local/bin/open-link" && ok "$HOME/.local/bin/open-link"
fi

echo "skills"
for s in "$SRC"/agent-gateway/skills/*/; do
    s="${s%/}"; name=$(basename "$s"); dst="$P/skills/$name"
    mkdir -p "$P/skills"; [ ! -d "$dst" ] || { chmod -R u+w "$dst" && rm -r "$dst"; }
    cp -R "$s" "$dst" && find "$dst" -name __pycache__ -type d -prune -exec rm -r {} + ; chmod -R a-w "$dst"
    for home in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
        mkdir -p "$home"; ln -sfn "$dst" "$home/$name"
    done
    ok "skill $name"
done

if [ "$OS" = Linux ]; then
    echo "Chrome for Testing"
    # version|url|sha256 (Chrome for Testing publishes none: pinned here; 157.0.8103.78 = the NAS's since 2026-11-22)
    CFT_VER=157.0.8103.78
    CFT_URL="https://storage.googleapis.com/chrome-for-testing-public/$CFT_VER/linux64/chrome-linux64.zip"
    CFT_SHA=9223832977a13db3646201b1341c1f9cf08afa3ceae92540116d7b0c062364fb
    d="$P/chrome-$CFT_VER"
    if [ -x "$d/chrome-linux64/chrome" ] && [ "$(cat "$d/.sha256" 2>/dev/null)" = "$CFT_SHA" ]; then ok "chrome $CFT_VER"
    elif [ "$(uname -m)" != x86_64 ]; then fail "Chrome for Testing: x86_64 only"
    else
        tmp="$P/.download-chrome"; rm -rf "$tmp" && mkdir -p "$tmp/x"
        if ! curl -sfL --retry 3 -o "$tmp/archive" "$CFT_URL"; then fail "chrome $CFT_VER (download failed)"
        elif [ "$(sha256sum "$tmp/archive" | awk '{print $1}')" != "$CFT_SHA" ]; then fail "chrome $CFT_VER (SHA-256 differs from the pinned one: not installed)"
        else
            # no unzip on the NAS: Python's zipfile, keeping each file's mode (Chrome's helpers must stay executable)
            python3 -I -c 'import os, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
for i in z.infolist():
    p = z.extract(i, sys.argv[2])
    if i.external_attr >> 16 & 0o777:
        os.chmod(p, i.external_attr >> 16 & 0o777)' "$tmp/archive" "$tmp/x"
            if [ -x "$tmp/x/chrome-linux64/chrome" ]; then
                echo "$CFT_SHA" > "$tmp/x/.sha256"
                rm -rf "$d" && mv "$tmp/x" "$d" && installed "chrome $CFT_VER ($d)"
            else fail "chrome $CFT_VER (no chrome-linux64/chrome in the archive)"; fi
        fi
        rm -rf "$tmp"
    fi
    if [ -x "$d/chrome-linux64/chrome" ]; then
        mkdir -p "$P/bin" && ln -sfn "$d/chrome-linux64/chrome" "$P/bin/chrome-for-testing" && ok "$P/bin/chrome-for-testing"
        for old in "$P"/chrome-*/; do [ -d "$old" ] && [ "${old%/}" != "$d" ] && rm -rf "${old%/}" && installed "removed ${old%/}"; done
    fi
fi

if [ "$OS" = Darwin ]; then
    echo "hooks"
    for f in "$HOME/.claude/settings.json" "$HOME"/.claude/account-*/settings.json; do  # every Claude account
        [ -f "$f" ] || continue
        [ -L "$f" ] && continue  # a link to the first: written once
        r=$(CLAUDE_SETTINGS="$f" python3 -I "$SRC/agent-gateway/merge_claude_settings.py" set) && ok "${f/#$HOME/~} hooks: $r" || fail "hooks merge $f"
    done

    echo "native host"
    EXT_ID=hfnfcdbehfbggjaccimmnolmhdkbfdie   # from the "key" in agent-gateway/extension/manifest.json
    NMH="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.jeanlescut.agent_tab_notes.json"
    NMH_TEXT="$(printf '{\n  "name": "com.jeanlescut.agent_tab_notes",\n  "description": "Agent tab notes: the Chrome kit record on the tab",\n  "path": "%s",\n  "type": "stdio",\n  "allowed_origins": ["chrome-extension://%s/"]\n}' "$P/agent-gateway/native_host.py" "$EXT_ID")"
    if [ "$(cat "$NMH" 2>/dev/null)" = "$NMH_TEXT" ]; then ok "$NMH"
    else mkdir -p "${NMH%/*}" && printf '%s\n' "$NMH_TEXT" > "$NMH.tmp" && mv "$NMH.tmp" "$NMH" && installed "$NMH"; fi

    echo "job"
    NAME=com.jeanlescut.chrome-gateways
    cp "$SRC/shared/clean_job.sh" "$P/.entrypoint.sh.tmp" && mv "$P/.entrypoint.sh.tmp" "$P/entrypoint.sh"
    PLIST_TEXT="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\"><dict>
  <key>Label</key><string>$NAME</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$P/entrypoint.sh</string></array>
  <key>StartInterval</key><integer>3600</integer><key>RunAtLoad</key><true/><key>AbandonProcessGroup</key><true/>
</dict></plist>"
    if [ "$(cat "$P/$NAME.plist" 2>/dev/null)" = "$PLIST_TEXT" ] && [ -L "$HOME/Library/LaunchAgents/$NAME.plist" ]; then ok "LaunchAgent $NAME"
    else
        printf '%s\n' "$PLIST_TEXT" > "$P/$NAME.plist" && mkdir -p "$HOME/Library/LaunchAgents" && ln -sfn "$P/$NAME.plist" "$HOME/Library/LaunchAgents/$NAME.plist"
        if [ "${AC_NO_LAUNCHCTL:-}" != 1 ]; then
            launchctl bootout "gui/$(id -u)/$NAME" 2> /dev/null || true; launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/$NAME.plist" || fail "launchctl bootstrap $NAME"
        fi
        installed "LaunchAgent $NAME (every hour; the work once a day)"
    fi
    [ -f "$HOME/opt/job-runner/lib.sh" ] || printf '  NOTE       job-runner is not installed (~/opt/job-runner/lib.sh missing): the job fails until it is\n'

    echo "iTerm2 clicks"
    IT_PY=""
    for f in "$HOME/Library/Application Support/iTerm2/iterm2env/versions/"*/bin/python3; do   # the newest with iTerm2's module
        [ -x "$f" ] && "$f" -I -c 'import iterm2' 2> /dev/null && IT_PY="$f"
    done
    if [ -z "$IT_PY" ]; then printf '  NOTE       iTerm2 clicks not set: no iTerm2 Python (Settings → General → Magic → Enable Python API), then re-run\n'
    elif r=$("$IT_PY" -I "$SRC/terminal-links/set_iterm2_clicks.py" "$HOME/.local/bin/open-link"); then
        case "$r" in *written*) installed "$r" ;; *) ok "$r" ;; esac
    else printf '  NOTE       %s\n' "$r"; fi
fi

if python3 -I -c 'import sys; compile(open(sys.argv[1]).read(), sys.argv[1], "exec")' "$P/agent-gateway/hook.py"; then ok "hook compiles"; else fail "hook"; fi
exit $FAILED
