/**
 * ReadMark Content Script
 * Runs on every page to:
 * 1. Track scroll position for saved pages (synced to server)
 * 2. Extract page metadata for quick-saving
 * 3. Show restore prompt when returning to a saved page
 *
 * Note: api.js is loaded before this file (defined in manifest content_scripts).
 */

(function () {
  "use strict";

  const SCROLL_SAVE_INTERVAL = 5000;  // Sync scroll every 5 seconds (gentler on server)
  const SCROLL_DEBOUNCE = 1000;
  let scrollTimer = null;
  let saveInterval = null;
  let currentUrl = window.location.href;
  let isTracked = false;
  let currentItemId = null;
  let lastSentScroll = -1;

  // ── Metadata Extraction ──────────────────────────────

  function extractMetadata() {
    const meta = {
      url: window.location.href,
      title: "",
      description: "",
      siteName: "",
      favicon: "",
      estimatedReadTime: 0,
      category: guessCategory(),
    };

    meta.title =
      getMetaContent("og:title") ||
      getMetaContent("twitter:title") ||
      document.title || "";

    meta.description =
      getMetaContent("og:description") ||
      getMetaContent("twitter:description") ||
      getMetaContent("description") || "";

    meta.siteName =
      getMetaContent("og:site_name") ||
      window.location.hostname.replace("www.", "");

    const iconLink =
      document.querySelector('link[rel="icon"]') ||
      document.querySelector('link[rel="shortcut icon"]');
    meta.favicon = iconLink ? iconLink.href : `${window.location.origin}/favicon.ico`;

    const bodyText = document.body?.innerText || "";
    const wordCount = bodyText.trim().split(/\s+/).length;
    meta.estimatedReadTime = Math.max(1, Math.round(wordCount / 200));

    return meta;
  }

  function getMetaContent(name) {
    const el =
      document.querySelector(`meta[property="${name}"]`) ||
      document.querySelector(`meta[name="${name}"]`);
    return el ? el.getAttribute("content") : "";
  }

  function guessCategory() {
    const hostname = window.location.hostname.toLowerCase();
    const url = window.location.href.toLowerCase();
    if (hostname.includes("youtube") || hostname.includes("vimeo") || hostname.includes("twitch")) return "Video";
    if (hostname.includes("podcast") || hostname.includes("spotify") || hostname.includes("anchor.fm")) return "Podcast";
    if (hostname.includes("arxiv") || hostname.includes("scholar") || hostname.includes("researchgate") || hostname.includes("ieee")) return "Research";
    if (hostname.includes("dev.to") || hostname.includes("stackoverflow") || hostname.includes("freecodecamp") || url.includes("tutorial") || url.includes("how-to") || url.includes("guide")) return "Tutorial";
    if (hostname.includes("medium") || hostname.includes("substack") || url.includes("/essay") || url.includes("/opinion")) return "Essay";
    return "Article";
  }

  // ── Scroll Position Tracking ─────────────────────────

  function getScrollPercentage() {
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
    if (scrollHeight <= 0) return 0;
    return Math.min(100, Math.round((scrollTop / scrollHeight) * 100));
  }

  async function saveScrollPosition() {
    if (!isTracked) return;
    const percentage = getScrollPercentage();
    if (percentage === lastSentScroll) return;  // Don't send if unchanged
    lastSentScroll = percentage;

    const loggedIn = await ReadMarkAPI.isLoggedIn();
    if (loggedIn) {
      // Sync to server
      try {
        await ReadMarkAPI.updateScroll(currentUrl, percentage);
      } catch (e) {
        // Offline fallback: save locally
        saveScrollLocally(percentage);
      }
    } else {
      // Local-only mode
      saveScrollLocally(percentage);
    }
  }

  function saveScrollLocally(percentage) {
    chrome.storage.local.get(["readmark_items"], (result) => {
      const items = result.readmark_items || [];
      const normalized = normalizeUrlSimple(currentUrl);
      const index = items.findIndex((item) => normalizeUrlSimple(item.url) === normalized);
      if (index !== -1) {
        items[index].scrollPosition = percentage;
        items[index].updatedAt = new Date().toISOString();
        if (percentage > 10 && items[index].status === "unread") items[index].status = "reading";
        if (percentage >= 95 && items[index].status === "reading") items[index].scrolledToEnd = true;
        chrome.storage.local.set({ readmark_items: items });
      }
    });
  }

  function normalizeUrlSimple(url) {
    try {
      const u = new URL(url);
      let hostname = u.hostname.replace("www.", "");
      let path = u.pathname.replace(/\/$/, "") || "/";
      return u.protocol + "//" + hostname + path;
    } catch { return url; }
  }

  // ── Restore Scroll Position ──────────────────────────

  async function checkAndRestore() {
    if (!currentUrl || currentUrl.startsWith("chrome://")) return;

    const loggedIn = await ReadMarkAPI.isLoggedIn();
    if (loggedIn) {
      try {
        const item = await ReadMarkAPI.lookupByUrl(currentUrl);
        if (item) {
          isTracked = true;
          currentItemId = item.id;
          if (item.scroll_position > 5 && (item.status === "reading" || item.status === "unread")) {
            showRestorePrompt(item.scroll_position, item.title);
          }
        }
      } catch {
        // Offline — fall back to local
        checkLocalRestore();
      }
    } else {
      checkLocalRestore();
    }
  }

  function checkLocalRestore() {
    chrome.storage.local.get(["readmark_items"], (result) => {
      const items = result.readmark_items || [];
      const normalized = normalizeUrlSimple(currentUrl);
      const item = items.find((i) => normalizeUrlSimple(i.url) === normalized);
      if (item) {
        isTracked = true;
        if (item.scrollPosition > 5 && item.status === "reading") {
          showRestorePrompt(item.scrollPosition, item.title);
        }
      }
    });
  }

  function showRestorePrompt(percentage, title) {
    const bar = document.createElement("div");
    bar.id = "readmark-restore-bar";
    bar.innerHTML = `
      <div style="
        position: fixed; bottom: 20px; right: 20px; z-index: 2147483647;
        background: #1a1a2e; color: #e4e5ea; border-radius: 12px;
        padding: 14px 18px; box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 13px; max-width: 320px;
        border: 1px solid rgba(192,132,252,0.3);
        animation: readmarkSlideIn 0.3s ease;
      ">
        <style>
          @keyframes readmarkSlideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        </style>
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
          <span style="font-size: 16px;">📖</span>
          <strong style="color: #c084fc;">ReadMark</strong>
        </div>
        <div style="margin-bottom: 10px; line-height: 1.4;">
          You were <strong>${percentage}%</strong> through this page. Pick up where you left off?
        </div>
        <div style="display: flex; gap: 8px;">
          <button id="readmark-restore-yes" style="
            background: #7c3aed; color: white; border: none; border-radius: 6px;
            padding: 6px 14px; font-size: 12px; font-weight: 600; cursor: pointer;
          ">Resume Reading</button>
          <button id="readmark-restore-no" style="
            background: transparent; color: #8b8d9a; border: 1px solid #2a2d3a; border-radius: 6px;
            padding: 6px 14px; font-size: 12px; cursor: pointer;
          ">Start Over</button>
        </div>
      </div>
    `;
    document.body.appendChild(bar);

    document.getElementById("readmark-restore-yes").addEventListener("click", () => {
      const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      window.scrollTo({ top: (percentage / 100) * scrollHeight, behavior: "smooth" });
      bar.remove();
    });

    document.getElementById("readmark-restore-no").addEventListener("click", () => bar.remove());

    // Auto-dismiss after 60 seconds
    setTimeout(() => {
      if (bar.parentNode) {
        bar.style.transition = "opacity 0.3s";
        bar.style.opacity = "0";
        setTimeout(() => bar.remove(), 300);
      }
    }, 60000);
  }

  // ── Scroll Event Listener ────────────────────────────

  window.addEventListener("scroll", () => {
    if (!isTracked) return;
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(saveScrollPosition, SCROLL_DEBOUNCE);
  }, { passive: true });

  saveInterval = setInterval(() => {
    if (isTracked) saveScrollPosition();
  }, SCROLL_SAVE_INTERVAL);

  window.addEventListener("beforeunload", () => {
    if (isTracked) saveScrollPosition();
  });

  // ── Message Handling ─────────────────────────────────

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "GET_PAGE_META") {
      sendResponse(extractMetadata());
    }
    if (msg.type === "GET_SCROLL_POSITION") {
      sendResponse({ scrollPercentage: getScrollPercentage() });
    }
    if (msg.type === "ITEM_SAVED") {
      isTracked = true;
      if (msg.item) currentItemId = msg.item.id;
    }
    return true;
  });

  // ── Initialize ───────────────────────────────────────

  setTimeout(checkAndRestore, 800);
})();
