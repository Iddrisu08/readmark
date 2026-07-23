/**
 * ReadMark API Client
 * Shared module for communicating with the ReadMark server.
 * 
 * ┌─────────────────────────────────────────────────────────┐
 * │  CONFIGURATION: Change API_BASE_URL to your server URL  │
 * └─────────────────────────────────────────────────────────┘
 */

// Set this to your ReadMark server's URL. For local development the backend
// runs on http://localhost:8000 (see backend/README.md).
const API_BASE_URL = "http://localhost:8000/api";

const ReadMarkAPI = {
  // ── Auth state (cached in chrome.storage) ────────────────

  async getToken() {
    const result = await chrome.storage.local.get(["readmark_token"]);
    return result.readmark_token || null;
  },

  async setToken(token) {
    await chrome.storage.local.set({ readmark_token: token });
  },

  async clearToken() {
    await chrome.storage.local.remove(["readmark_token", "readmark_user"]);
  },

  async getUser() {
    const result = await chrome.storage.local.get(["readmark_user"]);
    return result.readmark_user || null;
  },

  async setUser(user) {
    await chrome.storage.local.set({ readmark_user: user });
  },

  async isLoggedIn() {
    const token = await this.getToken();
    return !!token;
  },

  // ── HTTP helpers ─────────────────────────────────────────

  async request(path, options = {}) {
    // Content scripts can't make HTTP requests from HTTPS pages (mixed content).
    // Detect content script context by checking for chrome.tabs (unavailable in content scripts).
    const isContentScript = typeof chrome.tabs === "undefined";
    if (isContentScript) {
      return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ type: "API_REQUEST", path, options }, (response) => {
          if (chrome.runtime.lastError) {
            reject(new Error("Cannot reach server — working offline"));
            return;
          }
          if (response.error) {
            if (response.error === "SESSION_EXPIRED") {
              this.clearToken();
              reject(new Error("Session expired — please log in again"));
            } else {
              reject(new Error(response.error));
            }
          } else {
            resolve(response.data);
          }
        });
      });
    }

    const token = await this.getToken();
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    try {
      const res = await fetch(API_BASE_URL + path, {
        ...options,
        headers: { ...headers, ...options.headers },
      });

      if (res.status === 401) {
        await this.clearToken();
        throw new Error("Session expired — please log in again");
      }
      if (res.status === 204) return null;
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(err.detail || `Request failed (${res.status})`);
      }
      return res.json();
    } catch (e) {
      if (e.message.includes("Failed to fetch") || e.message.includes("NetworkError")) {
        throw new Error("Cannot reach server — working offline");
      }
      throw e;
    }
  },

  // ── Auth endpoints ───────────────────────────────────────

  async register(email, password, name) {
    const data = await this.request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    });
    await this.setToken(data.access_token);
    await this.setUser(data.user);
    return data;
  },

  async login(email, password) {
    const data = await this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    await this.setToken(data.access_token);
    await this.setUser(data.user);
    return data;
  },

  async logout() {
    await this.clearToken();
  },

  async fetchProfile() {
    const data = await this.request("/auth/me");
    await this.setUser(data);
    return data;
  },

  // ── Items endpoints ──────────────────────────────────────

  async listItems(params = {}) {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.category) query.set("category", params.category);
    if (params.search) query.set("search", params.search);
    if (params.sort) query.set("sort", params.sort);
    query.set("limit", params.limit || "200");
    return this.request(`/items?${query.toString()}`);
  },

  async createItem(item) {
    return this.request("/items", {
      method: "POST",
      body: JSON.stringify(item),
    });
  },

  async updateItem(id, updates) {
    return this.request(`/items/${id}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    });
  },

  async deleteItem(id) {
    return this.request(`/items/${id}`, { method: "DELETE" });
  },

  async updateScroll(url, scrollPosition) {
    return this.request("/items/scroll", {
      method: "POST",
      body: JSON.stringify({ url, scroll_position: scrollPosition }),
    });
  },

  async lookupByUrl(url) {
    return this.request(`/items/lookup/url?url=${encodeURIComponent(url)}`);
  },

  async syncItems(items) {
    return this.request("/items/sync", {
      method: "POST",
      body: JSON.stringify({ items }),
    });
  },
};
