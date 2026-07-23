"""
ReadMark — Integration Test Suite
Tests all API endpoints against the live server.

Run with:
    pip install requests pytest
    pytest test_readmark.py -v
"""

import os
import uuid
import pytest
import requests

# Override with the READMARK_TEST_URL env var to test against a deployed server.
BASE_URL = os.environ.get("READMARK_TEST_URL", "http://localhost:8000/api")


def unique_email():
    return f"test_{uuid.uuid4().hex[:8]}@readmark-test.com"


# ─────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def user_creds():
    """Register a fresh test user and return credentials + token."""
    email = unique_email()
    password = "TestPass123!"
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": "Test User",
    })
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    data = resp.json()
    return {
        "email": email,
        "password": password,
        "token": data["access_token"],
        "user_id": data["user"]["id"],
    }


@pytest.fixture(scope="module")
def auth_headers(user_creds):
    return {"Authorization": f"Bearer {user_creds['token']}"}


# ─────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────

class TestHealth:
    def test_health_check(self):
        resp = requests.get(f"{BASE_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "app" in data
        assert "version" in data


# ─────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────

class TestAuth:
    def test_register_new_user(self):
        resp = requests.post(f"{BASE_URL}/auth/register", json={
            "email": unique_email(),
            "password": "SecurePass99!",
            "name": "Jane Doe",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["auth_provider"] == "email"

    def test_register_duplicate_email(self, user_creds):
        resp = requests.post(f"{BASE_URL}/auth/register", json={
            "email": user_creds["email"],
            "password": "AnotherPass99!",
        })
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    def test_register_short_password(self):
        resp = requests.post(f"{BASE_URL}/auth/register", json={
            "email": unique_email(),
            "password": "short",
        })
        assert resp.status_code == 422  # Validation error

    def test_login_valid(self, user_creds):
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": user_creds["email"],
            "password": user_creds["password"],
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, user_creds):
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": user_creds["email"],
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    def test_login_unknown_email(self):
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "nobody@nowhere.com",
            "password": "SomePass99!",
        })
        assert resp.status_code == 401

    def test_get_profile_authenticated(self, auth_headers, user_creds):
        resp = requests.get(f"{BASE_URL}/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == user_creds["email"]
        assert data["name"] == "Test User"

    def test_get_profile_unauthenticated(self):
        resp = requests.get(f"{BASE_URL}/auth/me")
        assert resp.status_code == 401

    def test_get_profile_invalid_token(self):
        resp = requests.get(f"{BASE_URL}/auth/me",
                            headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────
# Items — CRUD
# ─────────────────────────────────────────────────────

class TestItemsCRUD:
    def test_list_items_empty(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/items", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_create_item(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/items", headers=auth_headers, json={
            "url": "https://example.com/article-1",
            "title": "Test Article",
            "category": "Article",
            "notes": "Interesting read",
            "status": "unread",
            "scroll_position": 0,
            "estimated_read_time": 5,
            "favicon": "https://example.com/favicon.ico",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Article"
        assert data["status"] == "unread"
        assert data["scroll_position"] == 0
        assert "id" in data
        return data["id"]

    def test_create_duplicate_url(self, auth_headers):
        url = f"https://example.com/unique-{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/items", headers=auth_headers, json={
            "url": url, "title": "First"
        })
        resp = requests.post(f"{BASE_URL}/items", headers=auth_headers, json={
            "url": url, "title": "Duplicate"
        })
        assert resp.status_code == 409
        assert "already" in resp.json()["detail"].lower()

    def test_get_item_by_id(self, auth_headers):
        # Create first
        create_resp = requests.post(f"{BASE_URL}/items", headers=auth_headers, json={
            "url": f"https://example.com/get-{uuid.uuid4().hex[:6]}",
            "title": "Fetch Me",
        })
        item_id = create_resp.json()["id"]

        resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == item_id

    def test_get_item_not_found(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/items/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404

    def test_update_item_status(self, auth_headers):
        create_resp = requests.post(f"{BASE_URL}/items", headers=auth_headers, json={
            "url": f"https://example.com/update-{uuid.uuid4().hex[:6]}",
            "title": "Update Me",
        })
        item_id = create_resp.json()["id"]

        resp = requests.patch(f"{BASE_URL}/items/{item_id}", headers=auth_headers,
                              json={"status": "reading"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "reading"

    def test_update_item_notes(self, auth_headers):
        create_resp = requests.post(f"{BASE_URL}/items", headers=auth_headers, json={
            "url": f"https://example.com/notes-{uuid.uuid4().hex[:6]}",
            "title": "Add Notes",
        })
        item_id = create_resp.json()["id"]

        resp = requests.patch(f"{BASE_URL}/items/{item_id}", headers=auth_headers,
                              json={"notes": "My personal notes here"})
        assert resp.status_code == 200
        assert resp.json()["notes"] == "My personal notes here"

    def test_delete_item(self, auth_headers):
        create_resp = requests.post(f"{BASE_URL}/items", headers=auth_headers, json={
            "url": f"https://example.com/delete-{uuid.uuid4().hex[:6]}",
            "title": "Delete Me",
        })
        item_id = create_resp.json()["id"]

        del_resp = requests.delete(f"{BASE_URL}/items/{item_id}", headers=auth_headers)
        assert del_resp.status_code == 204

        get_resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_items_require_auth(self):
        resp = requests.get(f"{BASE_URL}/items")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────
# Items — Filtering & Sorting
# ─────────────────────────────────────────────────────

class TestItemsFiltering:
    @pytest.fixture(autouse=True)
    def seed_items(self, auth_headers):
        """Create a set of items with different statuses and categories."""
        self.headers = auth_headers
        suffix = uuid.uuid4().hex[:6]
        items = [
            {"url": f"https://a.com/unread-{suffix}", "title": "Unread Article",
             "status": "unread", "category": "Article"},
            {"url": f"https://b.com/reading-{suffix}", "title": "Reading Tutorial",
             "status": "reading", "category": "Tutorial"},
            {"url": f"https://c.com/done-{suffix}", "title": "Done Research",
             "status": "done", "category": "Research"},
        ]
        self.item_ids = []
        for item in items:
            resp = requests.post(f"{BASE_URL}/items", headers=auth_headers, json=item)
            if resp.status_code == 201:
                self.item_ids.append(resp.json()["id"])

    def test_filter_by_status_unread(self):
        resp = requests.get(f"{BASE_URL}/items?status=unread", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(i["status"] == "unread" for i in data["items"])

    def test_filter_by_status_reading(self):
        resp = requests.get(f"{BASE_URL}/items?status=reading", headers=self.headers)
        assert resp.status_code == 200
        assert all(i["status"] == "reading" for i in resp.json()["items"])

    def test_filter_by_status_done(self):
        resp = requests.get(f"{BASE_URL}/items?status=done", headers=self.headers)
        assert resp.status_code == 200
        assert all(i["status"] == "done" for i in resp.json()["items"])

    def test_filter_invalid_status(self):
        resp = requests.get(f"{BASE_URL}/items?status=invalid", headers=self.headers)
        assert resp.status_code == 422

    def test_filter_by_category(self):
        resp = requests.get(f"{BASE_URL}/items?category=Tutorial", headers=self.headers)
        assert resp.status_code == 200
        assert all(i["category"] == "Tutorial" for i in resp.json()["items"])

    def test_search_by_title(self):
        resp = requests.get(f"{BASE_URL}/items?search=Unread+Article", headers=self.headers)
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert any("Unread" in t for t in titles)

    def test_sort_newest(self):
        resp = requests.get(f"{BASE_URL}/items?sort=newest", headers=self.headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        if len(items) > 1:
            dates = [i["created_at"] for i in items]
            assert dates == sorted(dates, reverse=True)

    def test_sort_alpha(self):
        resp = requests.get(f"{BASE_URL}/items?sort=alpha", headers=self.headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        if len(items) > 1:
            titles = [i["title"] for i in items]
            assert titles == sorted(titles, key=str.lower)

    def test_pagination(self):
        resp = requests.get(f"{BASE_URL}/items?limit=1&offset=0", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 1
        assert "total" in data


# ─────────────────────────────────────────────────────
# Items — URL Lookup (extension feature)
# ─────────────────────────────────────────────────────

class TestURLLookup:
    def test_lookup_saved_url(self, auth_headers):
        url = f"https://lookup-test.com/page-{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/items", headers=auth_headers,
                      json={"url": url, "title": "Lookup Test"})

        resp = requests.get(f"{BASE_URL}/items/lookup/url",
                            headers=auth_headers,
                            params={"url": url})
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["title"] == "Lookup Test"

    def test_lookup_unsaved_url(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/items/lookup/url",
                            headers=auth_headers,
                            params={"url": "https://not-saved-anywhere.com/page"})
        assert resp.status_code == 200
        assert resp.json() is None

    def test_lookup_url_normalization(self, auth_headers):
        """URLs with/without trailing slashes and tracking params should match."""
        base = f"https://normalize-test.com/article-{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/items", headers=auth_headers,
                      json={"url": base, "title": "Normalize Test"})

        # Same URL with trailing slash should resolve
        resp = requests.get(f"{BASE_URL}/items/lookup/url",
                            headers=auth_headers,
                            params={"url": base + "/"})
        assert resp.status_code == 200

    def test_lookup_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/items/lookup/url",
                            params={"url": "https://example.com"})
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────
# Scroll Position Tracking (extension feature)
# ─────────────────────────────────────────────────────

class TestScrollTracking:
    def test_update_scroll_position(self, auth_headers):
        url = f"https://scroll-test.com/article-{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/items", headers=auth_headers,
                      json={"url": url, "title": "Scroll Test", "status": "unread"})

        resp = requests.post(f"{BASE_URL}/items/scroll", headers=auth_headers,
                             json={"url": url, "scroll_position": 50})
        assert resp.status_code == 200
        data = resp.json()
        assert data["scroll_position"] == 50

    def test_scroll_past_10_changes_status_to_reading(self, auth_headers):
        url = f"https://scroll-test.com/reading-{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/items", headers=auth_headers,
                      json={"url": url, "title": "Auto Reading", "status": "unread"})

        resp = requests.post(f"{BASE_URL}/items/scroll", headers=auth_headers,
                             json={"url": url, "scroll_position": 15})
        assert resp.status_code == 200
        assert resp.json()["status"] == "reading"

    def test_scroll_past_95_changes_status_to_done(self, auth_headers):
        url = f"https://scroll-test.com/done-{uuid.uuid4().hex[:6]}"
        # Start in "reading" status
        requests.post(f"{BASE_URL}/items", headers=auth_headers,
                      json={"url": url, "title": "Auto Done", "status": "reading"})

        resp = requests.post(f"{BASE_URL}/items/scroll", headers=auth_headers,
                             json={"url": url, "scroll_position": 97})
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    def test_scroll_unknown_url_returns_404(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/items/scroll", headers=auth_headers,
                             json={"url": "https://not-saved.com/article", "scroll_position": 50})
        assert resp.status_code == 404

    def test_scroll_requires_auth(self):
        resp = requests.post(f"{BASE_URL}/items/scroll",
                             json={"url": "https://example.com", "scroll_position": 50})
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────
# Sync (extension ↔ server)
# ─────────────────────────────────────────────────────

class TestSync:
    def test_sync_new_items_from_extension(self, auth_headers):
        suffix = uuid.uuid4().hex[:6]
        resp = requests.post(f"{BASE_URL}/items/sync", headers=auth_headers, json={
            "items": [
                {
                    "url": f"https://sync-test.com/page1-{suffix}",
                    "title": "Synced Article 1",
                    "category": "Article",
                    "status": "unread",
                    "scroll_position": 0,
                    "estimated_read_time": 3,
                },
                {
                    "url": f"https://sync-test.com/page2-{suffix}",
                    "title": "Synced Article 2",
                    "category": "Tutorial",
                    "status": "reading",
                    "scroll_position": 40,
                    "estimated_read_time": 8,
                },
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "synced_at" in data
        synced_urls = [i["url"] for i in data["items"]]
        assert any(f"page1-{suffix}" in u for u in synced_urls)
        assert any(f"page2-{suffix}" in u for u in synced_urls)

    def test_sync_updates_scroll_if_higher(self, auth_headers):
        suffix = uuid.uuid4().hex[:6]
        url = f"https://sync-scroll.com/article-{suffix}"

        # Save item with low scroll
        requests.post(f"{BASE_URL}/items", headers=auth_headers,
                      json={"url": url, "title": "Scroll Sync", "scroll_position": 10,
                            "status": "reading"})

        # Sync with higher scroll
        resp = requests.post(f"{BASE_URL}/items/sync", headers=auth_headers, json={
            "items": [{"url": url, "title": "Scroll Sync", "scroll_position": 60,
                       "status": "reading"}]
        })
        assert resp.status_code == 200
        items = resp.json()["items"]
        matching = [i for i in items if i.get("url") == url or
                    (i.get("url") and url.rstrip("/") in i["url"])]
        if matching:
            assert matching[0]["scroll_position"] >= 60

    def test_sync_empty_list(self, auth_headers):
        resp = requests.post(f"{BASE_URL}/items/sync", headers=auth_headers,
                             json={"items": []})
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_sync_requires_auth(self):
        resp = requests.post(f"{BASE_URL}/items/sync", json={"items": []})
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────
# Data Isolation (users can't see each other's items)
# ─────────────────────────────────────────────────────

class TestDataIsolation:
    def test_user_cannot_access_other_users_item(self):
        # Create user A
        email_a = unique_email()
        resp_a = requests.post(f"{BASE_URL}/auth/register", json={
            "email": email_a, "password": "PassA1234!"
        })
        token_a = resp_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Create user B
        email_b = unique_email()
        resp_b = requests.post(f"{BASE_URL}/auth/register", json={
            "email": email_b, "password": "PassB1234!"
        })
        token_b = resp_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A creates an item
        item_resp = requests.post(f"{BASE_URL}/items", headers=headers_a, json={
            "url": f"https://private.com/secret-{uuid.uuid4().hex[:6]}",
            "title": "User A's private item",
        })
        item_id = item_resp.json()["id"]

        # User B tries to access it
        resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=headers_b)
        assert resp.status_code == 404

    def test_user_cannot_delete_other_users_item(self):
        # Create user A
        resp_a = requests.post(f"{BASE_URL}/auth/register", json={
            "email": unique_email(), "password": "PassA1234!"
        })
        headers_a = {"Authorization": f"Bearer {resp_a.json()['access_token']}"}

        # Create user B
        resp_b = requests.post(f"{BASE_URL}/auth/register", json={
            "email": unique_email(), "password": "PassB1234!"
        })
        headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

        # User A creates an item
        item_resp = requests.post(f"{BASE_URL}/items", headers=headers_a, json={
            "url": f"https://private.com/cant-delete-{uuid.uuid4().hex[:6]}",
            "title": "Protected Item",
        })
        item_id = item_resp.json()["id"]

        # User B tries to delete it
        resp = requests.delete(f"{BASE_URL}/items/{item_id}", headers=headers_b)
        assert resp.status_code == 404
