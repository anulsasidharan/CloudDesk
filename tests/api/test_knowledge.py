"""Phase 5: /knowledge routes, RBAC and error paths."""

API = "/api/v1/knowledge"


def test_routes_require_a_token(client):
    assert client.get(f"{API}/articles").status_code == 401
    assert client.post(f"{API}/search", json={"query": "mfa"}).status_code == 401
    assert client.post(f"{API}/reindex").status_code == 401


def test_list_has_15_articles_and_filters(client, viewer_headers):
    items = client.get(f"{API}/articles", headers=viewer_headers).json()
    assert len(items) == 15
    assert {"id", "slug", "title", "category", "tags", "summary", "updated_at"} <= set(items[0])
    billing = client.get(f"{API}/articles", params={"category": "billing"}, headers=viewer_headers)
    assert billing.json() and {a["category"] for a in billing.json()} == {"billing"}
    found = client.get(f"{API}/articles", params={"search": "MFA"}, headers=viewer_headers).json()
    assert any(a["slug"] == "mfa-recovery" for a in found)
    assert client.get(f"{API}/articles", params={"category": "nope"}, headers=viewer_headers).status_code == 422


def test_get_article_by_id_or_slug_and_404(client, viewer_headers):
    by_slug = client.get(f"{API}/articles/mfa-recovery", headers=viewer_headers)
    assert by_slug.status_code == 200 and "backup code" in by_slug.json()["content"]
    by_id = client.get(f"{API}/articles/{by_slug.json()['id']}", headers=viewer_headers)
    assert by_id.json()["slug"] == "mfa-recovery"
    assert client.get(f"{API}/articles/missing", headers=viewer_headers).status_code == 404


def test_search_returns_cited_evidence(client, viewer_headers):
    body = {"query": "locked out after wrong MFA codes", "top_k": 3}
    response = client.post(f"{API}/search", json=body, headers=viewer_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "hybrid" and data["took_ms"] >= 0
    assert data["results"][0]["source"].startswith("kb://mfa-recovery#")
    assert {"id", "title", "source", "snippet", "score", "url", "article_id"} == set(data["results"][0])
    assert len(data["results"]) <= 3


def test_search_modes_and_validation(client, viewer_headers):
    for mode in ("semantic", "keyword"):
        r = client.post(f"{API}/search", json={"query": "refund", "mode": mode}, headers=viewer_headers)
        assert r.status_code == 200 and r.json()["mode"] == mode
    for bad in ({"query": ""}, {"query": "x", "mode": "vibes"}, {"query": "x", "top_k": 0},
                {"query": "x", "top_k": 21}, {"query": "x", "category": "nope"}):
        assert client.post(f"{API}/search", json=bad, headers=viewer_headers).status_code == 422


def test_reindex_is_admin_only(client, viewer_headers, agent_headers, admin_headers):
    assert client.post(f"{API}/reindex", headers=viewer_headers).status_code == 403
    assert client.post(f"{API}/reindex", headers=agent_headers).status_code == 403
    response = client.post(f"{API}/reindex", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["articles"] == 15 and response.json()["indexed"] >= 15
    # still searchable after the collection was recreated
    again = client.post(f"{API}/search", json={"query": "mfa backup code"}, headers=admin_headers)
    assert again.json()["results"]
