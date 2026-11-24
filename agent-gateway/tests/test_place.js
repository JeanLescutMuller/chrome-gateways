// Unit tests of extension/place.js's pure decisions (one agent window per Claude account and desktop).
// Run: node agent-gateway/tests/test_place.js
const { decide, leftEmpty } = require("../extension/place.js");
let fail = 0;
const check = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  fail += !ok;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : `  got ${JSON.stringify(got)} want ${JSON.stringify(want)}`}`);
};
// tabs 11 and 12: one session on desktop 100; 21: another session on desktop 200
const notes = { 11: { desktop: 100 }, 12: { desktop: 100 }, 21: { desktop: 200 } };
const desk = { 1: [100], 2: [200], 3: [] };   // window 1 on desktop 100, 2 on 200, 3: unknown (a shared frame)
const tab = (id, windowId, groupId = 7) => ({ id, windowId, groupId });
const d = (o) => decide({ notes, desk, groupTabIds: [11], desktop: 100, ...o });
const a = (o) => d(o).action;

check("the session's desktop unknown (no iTerm2 window): skip", a({ tab: tab(11, 2), desktop: null }), "skip");
check("the windows' desktops not known yet: wait", a({ tab: tab(11, 2), desk: {} }), "wait");
check("already in the account's window on its desktop: stay", a({ tab: tab(11, 1) }), "stay");
check("on another desktop: move the group to the window on its desktop",
      d({ tab: tab(11, 2), groupTabIds: [11, 12] }), { action: "move", windowId: 1, groupId: 7, tabIds: [11, 12] });
check("an ungrouped agent tab: move the tab", d({ tab: tab(11, 2, -1) }), { action: "move", windowId: 1, groupId: -1, tabIds: [11] });
check("in a window whose desktop is unknown: move to the known one", d({ tab: tab(11, 3) }).windowId, 1);
check("no window of the account on its desktop: skip (the tab stays; tried again later)",
      d({ tab: tab(21, 1), desktop: 300 }), { action: "skip", why: "no window of this profile on desktop 300" });
check("a window shown on all desktops counts for each", a({ tab: tab(11, 4), desk: { 4: [100, 200] } }), "stay");
check("the group holds a tab not in open.json (the user's): wait, never move", a({ tab: tab(11, 2), groupTabIds: [11, 99] }), "wait");
check("the group mixes desktops: skip for good", d({ tab: tab(11, 2), groupTabIds: [11, 21] }).final, true);

const now = 100000;
check("left window: created by the arrival, only a new tab -> close", leftEmpty({ created: now - 2000, now, remaining: [{ url: "chrome://newtab/" }] }), true);
check("left window: not created by an arrival -> keep", leftEmpty({ created: undefined, now, remaining: [{ url: "chrome://newtab/" }] }), false);
check("left window: created long ago -> keep", leftEmpty({ created: now - 60000, now, remaining: [] }), false);
check("left window: holds a real page -> keep", leftEmpty({ created: now - 2000, now, remaining: [{ url: "https://example.com/" }] }), false);
console.log(fail ? `${fail} FAILED` : "all passed");
process.exit(fail ? 1 : 0);
