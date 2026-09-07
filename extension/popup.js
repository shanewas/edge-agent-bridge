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
    if (badge) {
      if (isOnline) {
        badge.className = "badge connected";
        badge.innerText = "Connected";
      } else {
        badge.className = "badge disconnected";
        badge.innerText = "Offline";
      }
    }

    const logBox = document.getElementById("logBox");
    if (logBox) {
      if (data.lastLog) {
        logBox.innerText = data.lastLog;
      } else if (directConnected) {
        logBox.innerText = "Bridge online on 127.0.0.1:18999";
      }
    }
  });

  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    const tabInfo = document.getElementById("tabInfo");
    if (tabInfo) {
      if (tab) {
        tabInfo.innerText = `${tab.title || "Tab"}\n(${tab.url || ""})`;
      } else {
        tabInfo.innerText = "No active tab";
      }
    }
  } catch (e) {
    const tabInfo = document.getElementById("tabInfo");
    if (tabInfo) {
      tabInfo.innerText = "Tab info unavailable";
    }
  }
}

updateUI();
setInterval(updateUI, 1000);

