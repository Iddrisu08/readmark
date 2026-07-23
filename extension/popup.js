/**
 * ReadMark Popup
 * Auth → Save current page → Recent items list
 */

const STATUS_CONFIG = {
  unread:  { label: "Unread",  icon: "○", color: "var(--unread)" },
  reading: { label: "Reading", icon: "◐", color: "var(--reading)" },
  done:    { label: "Done",    icon: "●", color: "var(--done)" },
};
const CATEGORIES = ["Article", "Essay", "Tutorial", "Research", "Video", "Podcast", "Other"];

let popupState = {
  authMode: "login",
  loading: true,
  saving: false,
  error: "",
  user: null,
  pageMeta: null,
  existingItem: null,  // If current page is already saved
  recentItems: [],
  theme: "dark",
};

// ── Init ───────────────────────────────────────────────

async function init() {
  // Load theme
  const stored = await chrome.storage.local.get(["readmark_theme"]);
  popupState.theme = stored.readmark_theme || "dark";
  if (popupState.theme === "light") document.body.classList.add("light");

  // Check auth
  const loggedIn = await ReadMarkAPI.isLoggedIn();
  if (loggedIn) {
    try {
      popupState.user = await ReadMarkAPI.getUser();
      // Get current tab metadata
      await loadPageMeta();
      // Check if page is already saved
      await checkExisting();
      // Load recent items
      await loadRecent();
    } catch (e) {
      console.warn("Init error:", e.message);
    }
  }
  popupState.loading = false;
  render();
}

async function loadPageMeta() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url || tab.url.startsWith("chrome://")) {
      popupState.pageMeta = { url: "", title: "Cannot save this page", category: "Other" };
      return;
    }
    // Try getting rich metadata from content script
    try {
      const meta = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_META" });
      if (meta) { popupState.pageMeta = meta; return; }
    } catch {}
    // Fallback to tab info
    popupState.pageMeta = {
      url: tab.url,
      title: tab.title || "",
      favicon: tab.favIconUrl || "",
      category: "Article",
      estimatedReadTime: 0,
    };
  } catch {
    popupState.pageMeta = { url: "", title: "Unknown page", category: "Other" };
  }
}

async function checkExisting() {
  if (!popupState.pageMeta?.url) return;
  try {
    const item = await ReadMarkAPI.lookupByUrl(popupState.pageMeta.url);
    popupState.existingItem = item;
  } catch { /* not found or offline */ }
}

async function loadRecent() {
  try {
    const data = await ReadMarkAPI.listItems({ sort: "newest", limit: 5 });
    popupState.recentItems = data.items || [];
  } catch {}
}

// ── Render ─────────────────────────────────────────────

function render() {
  const app = document.getElementById("app");
  if (popupState.loading) {
    app.innerHTML = `<div style="padding:40px;text-align:center;color:var(--muted);font-size:12px">Loading...</div>`;
    return;
  }
  if (!popupState.user) {
    app.innerHTML = renderAuth();
    bindAuth();
  } else {
    app.innerHTML = renderMain();
    bindMain();
  }
}

function esc(s) { if (!s) return ""; const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

function toast(msg) {
  document.querySelectorAll(".toast").forEach(t => t.remove());
  const t = document.createElement("div");
  t.className = "toast"; t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2200);
}

function timeAgo(d) {
  const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
  if (diff < 60) return "now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

// ── Auth View ──────────────────────────────────────────

function renderAuth() {
  const isLogin = popupState.authMode === "login";
  return `
    <div class="header">
      <div class="header-left">
        <div class="logo-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
          </svg>
        </div>
        <span class="logo-text">ReadMark</span>
      </div>
      <div class="header-right">
        <button class="icon-btn" id="theme-btn">${popupState.theme === 'dark' ? '☀' : '☾'}</button>
      </div>
    </div>
    <div class="auth-view">
      <div class="auth-tabs">
        <button class="auth-tab ${isLogin ? 'active' : ''}" data-mode="login">Sign In</button>
        <button class="auth-tab ${!isLogin ? 'active' : ''}" data-mode="register">Register</button>
      </div>
      <div class="error-msg ${popupState.error ? 'visible' : ''}" id="auth-error">${esc(popupState.error)}</div>
      ${!isLogin ? `
        <div class="field">
          <label>Name</label>
          <input id="auth-name" type="text" placeholder="Your name">
        </div>
      ` : ''}
      <div class="field">
        <label>Email</label>
        <input id="auth-email" type="email" placeholder="you@example.com">
      </div>
      <div class="field">
        <label>Password</label>
        <input id="auth-password" type="password" placeholder="${isLogin ? 'Enter password' : 'Min 8 characters'}">
      </div>
      <button class="btn-primary" id="auth-submit">${isLogin ? 'Sign In' : 'Create Account'}</button>
      <div class="server-url-hint">
        Connecting to: ${esc(API_BASE_URL.replace('/api', ''))}
      </div>
    </div>
  `;
}

function bindAuth() {
  document.getElementById("theme-btn")?.addEventListener("click", toggleTheme);

  document.querySelectorAll(".auth-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      popupState.authMode = btn.dataset.mode;
      popupState.error = "";
      render();
    });
  });

  document.getElementById("auth-submit")?.addEventListener("click", async () => {
    const email = document.getElementById("auth-email")?.value?.trim();
    const password = document.getElementById("auth-password")?.value;
    const name = document.getElementById("auth-name")?.value?.trim();

    if (!email || !password) { popupState.error = "Email and password required"; render(); return; }

    try {
      if (popupState.authMode === "login") {
        await ReadMarkAPI.login(email, password);
      } else {
        if (password.length < 8) { popupState.error = "Password must be 8+ characters"; render(); return; }
        await ReadMarkAPI.register(email, password, name);
      }
      popupState.user = await ReadMarkAPI.getUser();
      popupState.error = "";

      // Sync any existing local items to server
      await migrateLocalItems();

      await loadPageMeta();
      await checkExisting();
      await loadRecent();
      render();
      toast("Welcome!");

      // Tell background to update badge
      chrome.runtime.sendMessage({ type: "UPDATE_BADGE" });
    } catch (e) {
      popupState.error = e.message;
      render();
    }
  });

  // Enter key
  document.querySelectorAll("#auth-email, #auth-password, #auth-name").forEach(el => {
    el?.addEventListener("keydown", e => {
      if (e.key === "Enter") document.getElementById("auth-submit")?.click();
    });
  });
}

// ── Migrate local chrome.storage items to server ───────

async function migrateLocalItems() {
  try {
    const result = await chrome.storage.local.get(["readmark_items"]);
    const localItems = result.readmark_items || [];
    if (localItems.length === 0) return;

    const itemsToSync = localItems.map(item => ({
      url: item.url,
      title: item.title || "Untitled",
      category: item.category || "Article",
      notes: item.notes || "",
      status: item.status || "unread",
      scroll_position: item.scrollPosition || 0,
      estimated_read_time: item.estimatedReadTime || 0,
      favicon: item.favicon || "",
    }));

    await ReadMarkAPI.syncItems(itemsToSync);
    // Clear local items after successful sync
    await chrome.storage.local.remove(["readmark_items"]);
    console.log(`Migrated ${localItems.length} items to server`);
  } catch (e) {
    console.warn("Migration failed (will retry later):", e.message);
  }
}

// ── Main View (logged in) ──────────────────────────────

function renderMain() {
  const meta = popupState.pageMeta || {};
  const existing = popupState.existingItem;
  const canSave = meta.url && !meta.url.startsWith("chrome://");

  return `
    <div class="header">
      <div class="header-left">
        <div class="logo-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
          </svg>
        </div>
        <span class="logo-text">ReadMark</span>
      </div>
      <div class="header-right">
        <button class="icon-btn" id="theme-btn">${popupState.theme === 'dark' ? '☀' : '☾'}</button>
      </div>
    </div>

    <div class="save-view">
      ${canSave ? `
        <div class="page-info">
          ${meta.favicon ? `<img class="page-favicon" src="${esc(meta.favicon)}" onerror="this.style.display='none'">` : ''}
          <div class="page-title">${esc(meta.title || meta.url)}</div>
        </div>

        ${existing ? `
          <div class="already-saved yes">
            <span style="color:${STATUS_CONFIG[existing.status].color}">${STATUS_CONFIG[existing.status].icon}</span>
            Already saved · ${STATUS_CONFIG[existing.status].label}
            ${existing.scroll_position > 0 ? `· ${existing.scroll_position}% read` : ''}
          </div>
          <div class="form-row">
            <div class="field" style="flex:1">
              <select id="save-status" style="width:100%;padding:7px 10px;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;font-size:12px;color:var(--text)">
                <option value="unread" ${existing.status==='unread'?'selected':''}>○ Unread</option>
                <option value="reading" ${existing.status==='reading'?'selected':''}>◐ Reading</option>
                <option value="done" ${existing.status==='done'?'selected':''}>● Done</option>
              </select>
            </div>
            <button class="btn-primary" id="update-status-btn" style="width:auto;padding:7px 14px;margin-top:0">Update</button>
            <button class="btn-primary" id="delete-btn" style="width:auto;padding:7px 14px;margin-top:0;background:var(--danger)">Remove</button>
          </div>
        ` : `
          <div class="already-saved no">
            ✦ New — save this page to your library
          </div>
          <div class="field">
            <label>Title</label>
            <input id="save-title" value="${esc(meta.title)}">
          </div>
          <div class="form-row">
            <div class="field">
              <label>Category</label>
              <select id="save-category">
                ${CATEGORIES.map(c => `<option value="${c}" ${c === meta.category ? 'selected' : ''}>${c}</option>`).join('')}
              </select>
            </div>
          </div>
          <div class="field">
            <label>Notes (optional)</label>
            <textarea id="save-notes" rows="2" placeholder="Why is this interesting?"></textarea>
          </div>
          <button class="btn-primary" id="save-btn" ${popupState.saving ? 'disabled' : ''}>
            ${popupState.saving ? 'Saving...' : 'Save to Library'}
          </button>
        `}
      ` : `
        <div style="text-align:center;padding:16px;color:var(--muted);font-size:12px">
          Navigate to a web page to save it.
        </div>
      `}
    </div>

    ${popupState.recentItems.length > 0 ? `
      <div class="recent-section">
        <div class="section-label">Recent</div>
        ${popupState.recentItems.map(item => `
          <div class="recent-item" data-url="${esc(item.url || '')}">
            <span class="status-dot" style="color:${STATUS_CONFIG[item.status]?.color || 'var(--muted)'}">${STATUS_CONFIG[item.status]?.icon || '○'}</span>
            <span class="recent-title">${esc(item.title)}</span>
            <span class="recent-meta">${timeAgo(item.created_at)}</span>
          </div>
        `).join('')}
      </div>
    ` : ''}

    <div class="user-bar">
      <span>${esc(popupState.user?.email || '')}</span>
      <div style="display:flex;gap:8px">
        <button class="dashboard-link" id="dashboard-btn">Dashboard</button>
        <button class="logout-btn" id="logout-btn">Sign Out</button>
      </div>
    </div>
  `;
}

function bindMain() {
  document.getElementById("theme-btn")?.addEventListener("click", toggleTheme);

  // Save new item
  document.getElementById("save-btn")?.addEventListener("click", async () => {
    const meta = popupState.pageMeta;
    const title = document.getElementById("save-title")?.value?.trim() || meta.title;
    const category = document.getElementById("save-category")?.value || "Article";
    const notes = document.getElementById("save-notes")?.value?.trim() || "";

    popupState.saving = true;
    render();

    try {
      const item = await ReadMarkAPI.createItem({
        url: meta.url,
        title,
        category,
        notes,
        status: "unread",
        scroll_position: 0,
        estimated_read_time: meta.estimatedReadTime || 0,
        favicon: meta.favicon || "",
      });

      popupState.existingItem = item;
      popupState.saving = false;
      popupState.recentItems.unshift(item);
      if (popupState.recentItems.length > 5) popupState.recentItems.pop();

      // Tell content script this page is now tracked
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab) chrome.tabs.sendMessage(tab.id, { type: "ITEM_SAVED", item });
      } catch {}

      chrome.runtime.sendMessage({ type: "UPDATE_BADGE" });
      render();
      toast("Saved!");
    } catch (e) {
      popupState.saving = false;
      toast(e.message);
      render();
    }
  });

  // Update status of existing item
  document.getElementById("update-status-btn")?.addEventListener("click", async () => {
    const newStatus = document.getElementById("save-status")?.value;
    if (!newStatus || !popupState.existingItem) return;
    try {
      const updated = await ReadMarkAPI.updateItem(popupState.existingItem.id, { status: newStatus });
      popupState.existingItem = updated;
      chrome.runtime.sendMessage({ type: "UPDATE_BADGE" });
      render();
      toast("Updated!");
    } catch (e) { toast(e.message); }
  });

  // Delete
  document.getElementById("delete-btn")?.addEventListener("click", async () => {
    if (!popupState.existingItem) return;
    try {
      await ReadMarkAPI.deleteItem(popupState.existingItem.id);
      popupState.existingItem = null;
      popupState.recentItems = popupState.recentItems.filter(i => i.id !== popupState.existingItem?.id);
      chrome.runtime.sendMessage({ type: "UPDATE_BADGE" });
      await loadRecent();
      render();
      toast("Removed");
    } catch (e) { toast(e.message); }
  });

  // Recent item click → open in new tab
  document.querySelectorAll(".recent-item").forEach(el => {
    el.addEventListener("click", () => {
      const url = el.dataset.url;
      if (url) chrome.tabs.create({ url });
    });
  });

  // Dashboard link
  document.getElementById("dashboard-btn")?.addEventListener("click", () => {
    const dashUrl = API_BASE_URL.replace("/api", "");
    chrome.tabs.create({ url: dashUrl });
  });

  // Logout
  document.getElementById("logout-btn")?.addEventListener("click", async () => {
    await ReadMarkAPI.logout();
    popupState.user = null;
    popupState.existingItem = null;
    popupState.recentItems = [];
    chrome.runtime.sendMessage({ type: "UPDATE_BADGE" });
    render();
  });
}

// ── Theme toggle ───────────────────────────────────────

function toggleTheme() {
  popupState.theme = popupState.theme === "dark" ? "light" : "dark";
  document.body.classList.toggle("light", popupState.theme === "light");
  chrome.storage.local.set({ readmark_theme: popupState.theme });
  render();
}

// ── Go ─────────────────────────────────────────────────

init();
