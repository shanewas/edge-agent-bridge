// Update popup UI
async function updateUI() {
  // Wake up service worker
  try {
    chrome.runtime.sendMessage({ action: "wake_up" }, () => {
      if (chrome.runtime.lastError) {}
    });
  } catch (e) {}

  // Direct bridge probe. The badge tracks the extension link, not just the
  // daemon: bridge_running is a constant, extension_connected is the real signal.
  let directConnected = false;
  try {
    const res = await fetch("http://127.0.0.1:18999/status", { cache: "no-store" });
    if (res.ok) {
      const st = await res.json();
      directConnected = Boolean(st.extension_connected);
    }
  } catch (e) {}

  chrome.storage.local.get(["lastLog"], (data) => {
    const badge = document.getElementById("statusBadge");
    const isOnline = directConnected;
    if (isOnline) {
      badge.className = "badge connected";
      badge.innerText = "Connected";
    } else {
      badge.className = "badge disconnected";
      badge.innerText = "Offline";
    }

    if (data.lastLog) {
      document.getElementById("logBox").innerText = data.lastLog;
    } else if (directConnected) {
      document.getElementById("logBox").innerText = "Bridge online on 127.0.0.1:18999";
    }
  });

  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab) {
      document.getElementById("tabInfo").innerText = `${tab.title || "Tab"}\n(${tab.url || ""})`;
    } else {
      document.getElementById("tabInfo").innerText = "No active tab";
    }
  } catch (e) {
    document.getElementById("tabInfo").innerText = "Tab info unavailable";
  }
}

updateUI();
setInterval(updateUI, 1000);

