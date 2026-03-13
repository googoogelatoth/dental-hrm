from tests.security_test_utils import client, db_session, create_user, set_authenticated_cookies


def test_request_id_is_generated_for_public_page(client):
    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"].strip()


def test_request_id_echoes_incoming_header_on_admin_guard_redirect(client):
    request_id = "req-admin-guard-001"

    response = client.get(
        "/admin/calculate-payroll",
        headers={"X-Request-ID": request_id},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
    assert response.headers.get("X-Request-ID") == request_id


def test_request_id_present_on_api_unauthorized_json_response(client):
    response = client.get("/api/manual-requests-count", follow_redirects=False)

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"].strip()


def test_request_id_preserved_on_csrf_redirect(client, db_session):
    session_id = "obs-admin-session"
    admin = create_user(db_session, "obs_admin_001", "Admin", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )

    request_id = "req-csrf-001"
    response = client.post(
        "/admin/process-payroll",
        data={"action": "save_draft", "start_date": "2026-03-01", "end_date": "2026-03-31"},
        headers={"X-Request-ID": request_id},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "invalid_csrf" in response.headers["location"]
    assert response.headers.get("X-Request-ID") == request_id
