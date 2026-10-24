"""Security state changes and fail-closed behavior using the actual gateway."""
from werkzeug.security import generate_password_hash


def test_permission_query_failure_never_grants_access(bookcase):
    bookcase.sql("audiobook", "DROP TABLE user_category_permissions")
    for endpoint in ("/opds", "/opds/books/1", "/opds/books/1/cover",
                     "/opds/books/1/stream", "/opds/books/1/download", "/opds/books/5/tracks",
                     "/opds/books/5/tracks/5/stream", "/opds/books/5/tracks/5/download"):
        response = bookcase.client.get(endpoint, headers=bookcase.auth())
        assert response.status_code == 503
        assert b"user_category_permissions" not in response.data
        assert str(bookcase.tmp_path).encode() not in response.data


def test_deleted_identity_is_rejected_on_the_next_request(bookcase):
    assert bookcase.client.get("/opds", headers=bookcase.auth()).status_code == 200
    bookcase.sql("general", "DELETE FROM users WHERE username='reader'")
    assert bookcase.client.get("/opds/books/1/stream", headers=bookcase.auth()).status_code == 401


def test_changed_password_invalidates_old_credentials_immediately(bookcase):
    bookcase.sql("general", "UPDATE users SET password_hash=? WHERE username='reader'",
                (generate_password_hash("changed-test-password"),))
    assert bookcase.client.get("/opds", headers=bookcase.auth()).status_code == 401
    assert bookcase.client.get("/opds", headers=bookcase.auth(password="changed-test-password")).status_code == 200


def test_failed_login_throttle_is_bounded_and_authenticated_resources_are_private(bookcase):
    successful = bookcase.client.get("/opds", headers=bookcase.auth())
    assert successful.headers["Cache-Control"] == "private, no-store"
    assert successful.headers["Vary"] == "Authorization"
    for _ in range(25):
        assert bookcase.client.get("/opds").status_code == 401
    assert bookcase.client.get("/opds", headers=bookcase.auth()).status_code == 200
    invalid = bookcase.auth(username="nonexistent-reader")
    for _ in range(20):
        assert bookcase.client.get("/opds", headers=invalid).status_code == 401
    response = bookcase.client.get("/opds", headers=invalid)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
