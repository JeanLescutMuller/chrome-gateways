// window.html: the first tab (pinned) of a window `agent-chrome open-profile-window` opened for an agent profile with none.
// Tells the background which profile this extension runs in; its title names the profile in Mission Control.
const q = new URLSearchParams(location.search);
const profile = q.get("profile") || "";
document.title = `${profile || "?"} · agent window`;
document.getElementById("title").textContent = `${profile || "?"} · agent window`;
document.getElementById("profile").textContent = "Agents of this Claude account put their tabs here, on this desktop.";
chrome.runtime.sendMessage({ type: "marker", profile }).then(() => {}, () => {});
