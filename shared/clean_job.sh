#!/bin/bash
# ~/opt/chrome-gateways/entrypoint.sh: job chrome-gateways (DESIGN.md §6, REQUIREMENTS.md R14), run by the LaunchAgent
# com.jeanlescut.chrome-gateways (install.sh; a tick every hour).
# Requirements:
#   - once per UTC day, on the Mac (Chrome and its record are there)
#   - a dry run only: `agent-chrome clean --dry-run` closes nothing (the user, 2026-11-23: closing by itself later,
#     once the dry runs look right)
#   - something to close or drop: one task for Jean, always the same one (same title and path: never a second);
#     nothing left: that task completed (a program closes its own task when the problem goes away)
#   - timeout 5 min
#   - never asks Chrome (--no-chrome: from the record alone): AppleScript from a LaunchAgent makes macOS ask the user
#     for a permission (2026-11-24); a tab Chrome no longer has shows as "closed", and `agent-chrome clean` run by the
#     user sorts it out
# Reads ~/opt/chrome-gateways/state/; writes only the task.
. ~/opt/job-runner/lib.sh
jr_skip_if SUCCESS day "done today"
jr_execute 5 /usr/bin/python3 -I "$HOME/opt/chrome-gateways/agent-gateway/agent_chrome.py" clean --dry-run --no-chrome
[ "$JR_RC" = 0 ] || exit 0                                     # the FAILURE is written: the log says why
n=$(grep -cE '  (closed|dropped): ' "$JR_LOG")
TASK="$HOME/.local/bin/task"
PATH_ARGS=(--project Personal --section 'Projects - IT' --subsection chrome-gateways)
TITLE='chrome-gateways: Review what clean would close, then run it'
if [ "$n" = 0 ]; then
    "$TASK" complete "${PATH_ARGS[@]}" "$TITLE" > /dev/null 2>&1   # no such open task: nothing to do
    jr_summary "nothing to close"
    exit 0
fi
"$TASK" add "${PATH_ARGS[@]}" --repo chrome-gateways --owner jean --type one-off --need_level optional --deadline none \
    --done_when 'agent-chrome clean --dry-run lists nothing to close or drop' \
    --created_by "job chrome-gateways · $JR_MACHINE_NAME" \
    --description "chrome-gateways records every tab agents and scripts open, so that nothing is left behind. Its daily job found $n tab(s) in the record that \`agent-chrome clean\` would close (their Claude session ended and nobody is needed) or drop (Chrome no longer has them). It closes nothing by itself yet: you decided on 2026-11-23 to look at the dry runs first.

**Next step:** in a terminal, \`agent-chrome clean --dry-run\`; if the list looks right, \`agent-chrome clean\`. If the dry runs keep looking right, tell an agent to let the job close them by itself (chrome-gateways DESIGN.md §6)." \
    "$TITLE" > /dev/null 2>&1 || jr_summary "$n to close; the task could not be written"
jr_summary "$n tab(s) to close or drop: task for Jean"
