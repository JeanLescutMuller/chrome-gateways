// Agent tab notes: one agent window per Claude account and desktop (DESIGN.md §4). This extension runs in one agent profile
// (one Claude account), so every window it sees is that account's. An agent tab whose session's terminal is on desktop D
// (note.desktop, recorded at authorize-tab) and that Claude in Chrome put in a window on another desktop (it uses the
// profile's last-focused window) is moved, with its tab group, into this profile's window on D, in the background.
// No such window: the tab stays (no program can put a window on a desktop; a new one opens where the user looks).
// Each window's desktops come from the native host (it matches the frames this extension reports to macOS's windows).
// Only agent tabs (in the kit's open.json, sent by the host as notes) are ever moved, never the user's; each tab is
// placed once (the user may move it after, we never do). The window a group left is closed only when that group's
// arrival created it (unfocused, under 30 s before) and nothing else is in it.
// Kept: chrome.storage.local {profile} (learned from a note; names the host's report); chrome.storage.session {placed:
// {tabId: 1}, created: {windowId: ms}, desk: {windowId: [desktop ids]}, placeLog: [last 30 decisions]}.
// decide() and leftEmpty() are pure: tests/test_place.js runs them in Node.

const BLANK = ["", "about:blank", "chrome://newtab/", "chrome://new-tab-page/"];
const NEW_WINDOW_MS = 30000;

// Where should this agent tab go?  -> {action: skip|wait|stay|move, ...}; skip and wait leave it unplaced (tried again)
function decide({ tab, desktop, desk, groupTabIds, notes }) {
  if (desktop == null) return { action: "skip", why: "its session's desktop is unknown (no iTerm2 window, or not a Mac session)" };
  if (!desk || desk[tab.windowId] == null) return { action: "wait", why: "the desktops of this profile's windows are not known yet" };
  if (desk[tab.windowId].includes(desktop)) return { action: "stay" };
  const target = Object.keys(desk).map(Number).find(w => w !== tab.windowId && desk[w].includes(desktop));
  if (target == null) return { action: "skip", why: `no window of this profile on desktop ${desktop}` };
  const ids = tab.groupId === -1 || tab.groupId == null ? [tab.id] : groupTabIds;
  const unknown = ids.filter(i => !notes[String(i)]);
  if (unknown.length) return { action: "wait", why: `tab(s) ${unknown.join(",")} of the group are not an agent's (yet)` };
  if (ids.some(i => notes[String(i)].desktop !== desktop)) return { action: "skip", why: "the group mixes desktops", final: true };
  return { action: "move", windowId: target, groupId: tab.groupId == null ? -1 : tab.groupId, tabIds: ids };
}

// After a move: close the window the group left?
function leftEmpty({ created, now, remaining }) {
  return created != null && now - created <= NEW_WINDOW_MS && remaining.every(t => BLANK.includes(t.url || t.pendingUrl || ""));
}

if (typeof module !== "undefined") module.exports = { decide, leftEmpty, BLANK, NEW_WINDOW_MS };

if (typeof chrome !== "undefined" && chrome.windows) {
  var Place = (() => {
    let queue = Promise.resolve();
    const run = fn => (queue = queue.then(fn).catch(e => log({ error: String(e) })));
    const local = async () => ({ profile: null, ...(await chrome.storage.local.get(["profile"])) });
    const sess = async () => ({ placed: {}, created: {}, desk: {}, placeLog: [],
                                ...(await chrome.storage.session.get(["placed", "created", "desk", "placeLog"])) });
    let notesNow = {};
    const lastWhy = {};   // a tab's last logged decision: a retry that decides the same is not logged again

    async function log(entry) {
      const s = await sess();
      s.placeLog.push({ t: Date.now(), ...entry });
      await chrome.storage.session.set({ placeLog: s.placeLog.slice(-30) });
    }

    async function placeOne(id, notes) {
      const note = notes[id];
      const tab = await chrome.tabs.get(Number(id)).catch(() => null);
      if (!tab) return;                                   // not in this profile, or gone
      let { profile } = await local();
      if (!profile && note.profile) { profile = note.profile; await chrome.storage.local.set({ profile }); }
      const s = await sess();
      if (s.placed[id]) return;
      const groupTabIds = tab.groupId > -1 ? (await chrome.tabs.query({ groupId: tab.groupId })).map(t => t.id) : [tab.id];
      const d = decide({ tab, desktop: note.desktop, desk: s.desk, groupTabIds, notes });
      if (d.action === "move") {
        const src = tab.windowId;
        if (d.groupId > -1) await chrome.tabGroups.move(d.groupId, { windowId: d.windowId, index: -1 });
        else await chrome.tabs.move(tab.id, { windowId: d.windowId, index: -1 });
        const remaining = await chrome.tabs.query({ windowId: src }).catch(() => []);
        if (remaining.length && leftEmpty({ created: s.created[src], now: Date.now(), remaining })) {
          await chrome.windows.remove(src).catch(() => {});
          d.closed = src;
        }
      }
      if (d.action === "stay" || d.action === "move" || d.final) {
        const s2 = await sess();
        for (const t of d.tabIds || groupTabIds) s2.placed[String(t)] = 1;
        await chrome.storage.session.set({ placed: s2.placed });
      }
      if (d.action !== "stay" && d.action !== "wait" && lastWhy[id] !== d.action + (d.why || "")) {
        lastWhy[id] = d.action + (d.why || "");
        await log({ tab: tab.id, desktop: note.desktop, from: tab.windowId, ...d });
      }
    }

    const place = notes => run(async () => { notesNow = notes; for (const id of Object.keys(notes)) await placeOne(id, notes); });
    return {
      local, place,
      // the host's answer to a report: {windowId: [desktop ids]}; then the tabs not placed yet are tried again
      setDesktops: desk => run(() => chrome.storage.session.set({ desk })).then(() => place(notesNow)),
      // window.html, the first tab of a window `agent-chrome open-profile-window` opened: it names the profile
      marker: (profile, tab) => run(async () => {
        if (profile) await chrome.storage.local.set({ profile });
        if (!tab.pinned) await chrome.tabs.update(tab.id, { pinned: true }).catch(() => {});
        return { profile };
      }),
      created: w => run(async () => {
        if (!w.focused) { const s = await sess(); s.created[w.id] = Date.now(); await chrome.storage.session.set({ created: s.created }); }
      }),
    };
  })();
}
