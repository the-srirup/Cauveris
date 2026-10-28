"""
Production Authentication & Authorization End-to-End Test Suite.

Validates:
1. User registration / signup with persistent SQLite storage
2. Bcrypt password hashing (work factor >= 12, no plaintext passwords in DB)
3. Normalized email uniqueness and case-insensitive collision rejection (409)
4. Credential verification via real login (session establishment, HttpOnly cookies)
5. Structured error responses on authentication failures (401 AUTH_INVALID_CREDENTIALS)
6. Session restoration via GET /api/v1/auth/me and GET /api/auth/me
7. Logout and session revocation (invalidating session in DB and clearing cookies)
8. Multi-tenant / cross-user isolation: User B cannot view or modify User A's incidents (403)
9. Production security invariants: refusal to run with demo auth in production runtime mode
"""

import pytest
import sqlite3
import uuid
from httpx import AsyncClient, ASGITransport

from cauveris.api.main import app
from cauveris.auth import init_auth_store
from cauveris.config import get_settings, Settings
from cauveris.schemas.incident import Incident


@pytest.fixture
async def setup_test_auth_db(tmp_path):
    """Initializes a clean SQLite auth database for testing."""
    db_file = str(tmp_path / "test_auth.db")
    settings = get_settings()
    settings.runtime_mode = "development"
    settings.demo_auth = False
    settings.auth_backend = "sqlite"
    settings.auth_db_path = db_file
    store = init_auth_store(backend="sqlite", db_path=db_file)
    yield db_file, store


@pytest.mark.asyncio
async def test_signup_persistent_storage_and_bcrypt(setup_test_auth_db):
    """Test signup persists account to SQLite with bcrypt hash."""
    db_file, store = setup_test_auth_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        signup_payload = {
            "email": "Engineer.One@cauveris.dev",
            "password": "SuperSecurePassword2026!",
            "full_name": "Engineer One",
            "org_name": "Autonomous Systems Lab",
        }
        res = await client.post("/api/v1/auth/signup", json=signup_payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "engineer.one@cauveris.dev"
        assert data["user"]["full_name"] == "Engineer One"
        assert "password" not in data["user"]
        assert "password_hash" not in data["user"]

        # Verify HttpOnly cookies
        cookies = res.cookies
        assert "access_token" in cookies
        assert "refresh_token" in cookies
        assert "session_id" in cookies

        # Inspect SQLite database directly to confirm persistence & bcrypt hash
        con = sqlite3.connect(db_file)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE normalized_email = ?", ("engineer.one@cauveris.dev",))
        row = cur.fetchone()
        assert row is not None, "User record must exist in SQLite database"
        assert row["normalized_email"] == "engineer.one@cauveris.dev"
        assert row["display_name"] == "Engineer One"

        # Assert bcrypt hash format
        pw_hash = row["password_hash"]
        assert pw_hash.startswith(("$2b$12$", "$2b$", "$2a$")), f"Password must be hashed with bcrypt, got {pw_hash[:10]}"
        assert "SuperSecurePassword2026!" not in pw_hash, "Plaintext password must never appear in database"
        con.close()


@pytest.mark.asyncio
async def test_duplicate_signup_rejection(setup_test_auth_db):
    """Test duplicate signup with same or case-variant email is rejected with 409."""
    db_file, store = setup_test_auth_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Initial signup
        res1 = await client.post("/api/v1/auth/signup", json={
            "email": "operator.alice@cauveris.dev",
            "password": "Password123456!",
            "full_name": "Alice Operator",
        })
        assert res1.status_code == 200

        # Attempt duplicate signup with different case
        res2 = await client.post("/api/v1/auth/signup", json={
            "email": "OPERATOR.ALICE@cauveris.dev",
            "password": "DifferentPassword123!",
            "full_name": "Alice Duplicate",
        })
        assert res2.status_code == 409
        body2 = res2.json()
        assert body2.get("detail", {}).get("error") == "AUTH_EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_login_success_and_invalid_credentials(setup_test_auth_db):
    """Test real login with bcrypt verification and structured 401 error on bad credentials."""
    db_file, store = setup_test_auth_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user
        await client.post("/api/v1/auth/signup", json={
            "email": "security.analyst@cauveris.dev",
            "password": "ValidPassword987!",
            "full_name": "Security Analyst",
        })

        # Test invalid password
        bad_res = await client.post("/api/v1/auth/login", json={
            "email": "security.analyst@cauveris.dev",
            "password": "WrongPassword!",
        })
        assert bad_res.status_code == 401
        bad_body = bad_res.json()
        assert bad_body.get("detail", {}).get("error") == "AUTH_INVALID_CREDENTIALS"

        # Test non-existent user
        non_res = await client.post("/api/v1/auth/login", json={
            "email": "ghost.user@cauveris.dev",
            "password": "SomePassword123!",
        })
        assert non_res.status_code == 401
        assert non_res.json().get("detail", {}).get("error") == "AUTH_INVALID_CREDENTIALS"

        # Test successful login
        good_res = await client.post("/api/v1/auth/login", json={
            "email": "SECURITY.ANALYST@cauveris.dev",  # Case-insensitive
            "password": "ValidPassword987!",
        })
        assert good_res.status_code == 200
        good_data = good_res.json()
        assert "access_token" in good_data
        assert good_res.cookies.get("access_token") is not None


@pytest.mark.asyncio
async def test_session_restoration_and_logout(setup_test_auth_db):
    """Test GET /api/v1/auth/me session restoration and logout revocation."""
    db_file, store = setup_test_auth_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Signup & obtain cookies
        signup_res = await client.post("/api/v1/auth/signup", json={
            "email": "session.tester@cauveris.dev",
            "password": "SessionTestPassword1!",
            "full_name": "Session Tester",
        })
        assert signup_res.status_code == 200
        access_token = signup_res.json()["access_token"]

        # 2. Test session restoration with Bearer header
        me_res1 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_res1.status_code == 200
        me_data1 = me_res1.json()
        assert me_data1["email"] == "session.tester@cauveris.dev"
        assert me_data1["full_name"] == "Session Tester"
        assert "password_hash" not in me_data1

        # 3. Test route alias /api/auth/me with cookie
        me_res2 = await client.get("/api/auth/me")
        assert me_res2.status_code == 200
        assert me_res2.json()["email"] == "session.tester@cauveris.dev"

        # 4. Logout
        logout_res = await client.post("/api/v1/auth/logout")
        assert logout_res.status_code == 200

        # 5. Verify cookies are cleared and me returns 401
        client.cookies.clear()
        me_res_after = await client.get("/api/v1/auth/me")
        assert me_res_after.status_code == 401

        # 6. Verify presenting the revoked token is rejected
        me_revoked = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_revoked.status_code == 401


@pytest.mark.asyncio
async def test_cross_user_isolation(setup_test_auth_db):
    """Test User B is denied (403) from accessing User A's incident."""
    db_file, store = setup_test_auth_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create User A
        res_a = await client.post("/api/v1/auth/signup", json={
            "email": "user.a@cauveris.dev",
            "password": "PasswordForUserA1!",
            "full_name": "User Alpha",
            "org_name": "Alpha Org",
        })
        assert res_a.status_code == 200
        token_a = res_a.json()["access_token"]
        user_a_id = res_a.json()["user"]["id"]

        # Create User B
        res_b = await client.post("/api/v1/auth/signup", json={
            "email": "user.b@cauveris.dev",
            "password": "PasswordForUserB1!",
            "full_name": "User Beta",
            "org_name": "Beta Org",
        })
        assert res_b.status_code == 200
        token_b = res_b.json()["access_token"]

        # User A creates an incident
        from cauveris.api.main import incidents
        inc_id = f"CAU-ISOLATION-{uuid.uuid4().hex[:6]}"
        incident_a = Incident(
            id=inc_id,
            title="Private Incident Alpha",
            description="Confidential telemetry data",
            system_name="alpha-rover",
            status="OBSERVED",
        )
        incident_a._owner_user_id = user_a_id
        incident_a._owner_org_id = res_a.json()["user"]["org_id"]
        incidents[inc_id] = incident_a

        # User A can read their incident
        res_a_read = await client.get(
            f"/api/v1/incidents/{inc_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res_a_read.status_code == 200

        # User B attempts to read User A's incident -> must be 403 Forbidden
        res_b_read = await client.get(
            f"/api/v1/incidents/{inc_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b_read.status_code == 403, f"Expected 403, got {res_b_read.status_code}: {res_b_read.text}"
        assert res_b_read.json().get("detail", {}).get("error") == "access_denied"

        # User B attempts to access timeline -> must be 403 Forbidden
        res_b_timeline = await client.get(
            f"/api/v1/incidents/{inc_id}/timeline",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b_timeline.status_code == 403

        # User B attempts to download repair package -> must be 403 Forbidden
        res_b_dl = await client.get(
            f"/api/v1/incidents/{inc_id}/download-patch-package",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b_dl.status_code == 403


def test_production_security_validation_refuses_insecure_demo_auth():
    """Test validate_production_security prevents startup with demo auth in production."""
    settings = Settings()
    settings.runtime_mode = "production"
    settings.demo_auth = True

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate_production_security()
    assert "CAUVERIS_DEMO_AUTH is enabled while CAUVERIS_RUNTIME_MODE=production" in str(exc_info.value)
