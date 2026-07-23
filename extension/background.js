/**
 * ReadMark Background Service Worker
 * Handles badge updates and periodic sync.
 */

importScripts("api.js");

// ── Badge Update ───────────────────────────────────────

async function updateBadge() {
  const loggedIn = await ReadMarkAPI.isLoggedIn();

  if (loggedIn) {
    try {
      const data = await ReadMarkAPI.listItems({ limit: 200 });
      const items = data.items || [];
      const readingCount = items.filter(i => i.status === "reading").length;
      const unreadCount = items.filter(i => i.status === "unread").length;
      const total = readingCount + unreadCount;

      chrome.action.setBadgeText({ text: total > 0 ? String(total) : "" });
      chrome.action.setBadgeBackgroundColor({ color: readingCount > 0 ? "#f59e0b" : "#7c3aed" });
      return;
    } catch (e) {
      console.warn("Badge update from server failed:", e.message);
      // Fall through to local
    }
  }

  // Fallback: local storage
  chrome.storage.local.get(["readmark_items"], (result) => {
    const items = result.readmark_items || [];
    const readingCount = items.filter(i => i.status === "reading").length;
    const unreadCount = items.filter(i => i.status === "unread").length;
    const total = readingCount + unreadCount;

    chrome.action.setBadgeText({ text: total > 0 ? String(total) : "" });
    chrome.action.setBadgeBackgroundColor({ color: readingCount > 0 ? "#f59e0b" : "#7c3aed" });
  });
}

// ── Storage change listener (for local mode) ──────────

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.readmark_items) {
    updateBadge();
  }
});

// ── Lifecycle events ───────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  updateBadge();
  // Set up periodic badge refresh (every 5 minutes)
  chrome.alarms.create("badge-refresh", { periodInMinutes: 5 });
});

chrome.runtime.onStartup.addListener(updateBadge);

// ── Alarm handler ──────────────────────────────────────

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "badge-refresh") {
    updateBadge();
  }
});

// ── Message handler ────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "UPDATE_BADGE") {
    updateBadge();
  }

  // Proxy API requests from content scripts to bypass mixed content restrictions
  if (msg.type === "API_REQUEST") {
    ReadMarkAPI.request(msg.path, msg.options)
      .then(data => sendResponse({ data }))
      .catch(e => {
        if (e.message.includes("Session expired")) {
          sendResponse({ error: "SESSION_EXPIRED" });
        } else {
          sendResponse({ error: e.message });
        }
      });
    return true;
  }

  return true;
});
