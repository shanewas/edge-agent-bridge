// Edge Agent Bridge popup: shows daemon/extension state and the pairing field when the daemon asks for it.

async function fetchStatus() {
  try {
    const res = await fetch("http://127.0.0.1:18999/status", { cache: "no-store" });
    if (res.ok) return await res.json();
  } catch (e) {}
  return null;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function show(id, visible) {
  const el = document.getElementById(id);
  if (el) el.style.display = visible ? "block" : "none";
}

async function updateUI() {
  try {
    chrome.runtime.sendMessage({ type: "KEEPALIVE" }).catch(() => {});
  } catch (e) {}

  const st = await fetchStatus();
  const online = Boolean(st && st.extension_connected);
  const badge = document.getElementById("statusBadge");
  if (badge) {
    badge.className = online ? "badge connected" : "badge disconnected";
    badge.textContent = online ? "Connected" : (st ? "Extension offline" : "Daemon offline");
  }

  const extVersion = chrome.runtime.getManifest().version;
  setText("versions", st ? `daemon ${st.daemon_version || "?"} · extension ${extVersion}` : "daemon not running");
  show("outdated", Boolean(st && st.extension_outdated));
  show("pairing", Boolean(st && st.pairing_required));

  chrome.storage.local.get(["lastLog"], (data) => {
    setText("logBox", data.lastLog || (online ? "Bridge online on 127.0.0.1:18999" : ""));
  });

  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    setText("tabInfo", tab ? `${tab.title || "Tab"}\n(${tab.url || ""})` : "No active tab");
  } catch (e) {
    setText("tabInfo", "Tab info unavailable");
  }
}

document.getElementById("pairSave").addEventListener("click", async () => {
  const value = document.getElementById("pairToken").value.trim();
  await chrome.storage.local.set({ pairToken: value });
  try {
    chrome.runtime.sendMessage({ type: "RECONNECT" }).catch(() => {});
  } catch (e) {}
  setText("pairMsg", "Saved. Reconnecting…");
});

updateUI();
setInterval(updateUI, 1000);
