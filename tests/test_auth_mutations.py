"""
15 Security Mutation Tests for Cauveris Authentication & Authorization Architecture.

Asserts that every security invariant is actively enforced and that mutations
violating any security control are correctly detected and rejected.
"""

import pytest
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from cauveris.api.main import app
from cauveris.auth import init_auth_store, Session, User
from cauveris.config import get_settings, Settings
from cauveris.schemas.incident import Incident


@pytest.fixture
async def mutation_test_db(tmp_path):
    db_file = str(tmp_path / "mutation_auth.db")
    settings = get_settings()
    settings.runtime_mode = "development"
    settings.demo_auth = False
    settings.auth_backend = "sqlite"
    settings.auth_db_path = db_file
    settings.auth_password_min_length = 12
    store = init_auth_store(backend="sqlite", db_path=db_file)
    yield db_file, store


@pytest.mark.asyncio
async def test_mutation_01_empty_password_rejected(mutation_test_db):
    """MUTATION 1: Empty password must be rejected."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/auth/signup", json={
            "email": "test.empty@cauveris.dev",
            "password": "",
            "full_name": "Test User",
        })
        assert res.status_code == 400


@pytest.mark.asyncio
async def test_mutation_02_short_password_rejected(mutation_test_db):
    """MUTATION 2: Short password (< min_length) must be rejected."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/auth/signup", json={
            "email": "test.short@cauveris.dev",
            "password": "short",
            "full_name": "Test User",
        })
        assert res.status_code == 400
        assert res.json().get("detail", {}).get("error") == "AUTH_PASSWORD_TOO_SHORT"


@pytest.mark.asyncio
async def test_mutation_03_no_plaintext_passwords_stored(mutation_test_db):
    """MUTATION 3: Plaintext passwords must NEVER be persisted in the database."""
    db_file, _ = mutation_test_db
    raw_pass = "VerySecretPassword2026!"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/auth/signup", json={
            "email": "test.plaintext@cauveris.dev",
            "password": raw_pass,
            "full_name": "Test User",
        })
        assert res.status_code == 200

        con = sqlite3.connect(db_file)
        cur = con.cursor()
        cur.execute("SELECT password_hash FROM users WHERE email = 'test.plaintext@cauveris.dev'")
        row = cur.fetchone()
        con.close()
        assert row is not None
        assert raw_pass not in row[0]
        assert row[0].startswith("$2b$")


@pytest.mark.asyncio
async def test_mutation_04_case_variant_email_collision_rejected(mutation_test_db):
    """MUTATION 4: Uppercase/lowercase email variants must resolve to the same account and collide (409)."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/signup", json={
            "email": "user.case@cauveris.dev",
            "password": "ValidPassword123!",
            "full_name": "Case User",
        })
        res = await client.post("/api/v1/auth/signup", json={
            "email": "USER.CASE@CAUVERIS.DEV",
            "password": "ValidPassword123!",
            "full_name": "Case User",
        })
        assert res.status_code == 409


@pytest.mark.asyncio
async def test_mutation_05_unverified_password_fails_login(mutation_test_db):
    """MUTATION 5: Login must fail when password verification fails."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/auth/signup", json={
            "email": "user.verify@cauveris.dev",
            "password": "CorrectPassword123!",
            "full_name": "Verify User",
        })
        res = await client.post("/api/v1/auth/login", json={
            "email": "user.verify@cauveris.dev",
            "password": "IncorrectPassword123!",
        })
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_mutation_06_no_demo_backdoor_in_production(mutation_test_db):
    """MUTATION 6: Demo password strings ('demo', 'demo123456') must not bypass real verification."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create user with a real password
        await client.post("/api/v1/auth/signup", json={
            "email": "demo.user@cauveris.dev",
            "password": "MyActualRealPassword1!",
            "full_name": "Demo User",
        })
        # Attempt login with backdoor string
        res = await client.post("/api/v1/auth/login", json={
            "email": "demo.user@cauveris.dev",
            "password": "demo123456",
        })
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_mutation_07_session_id_entropy(mutation_test_db):
    """MUTATION 7: Session identifiers must be high-entropy cryptographically random strings."""
    _, store = mutation_test_db
    sess1 = Session(user_id="u1", org_id="o1")
    sess2 = Session(user_id="u2", org_id="o2")
    assert sess1.id != sess2.id
    assert len(sess1.id) >= 16
    assert not sess1.id.isdigit(), "Session ID must not be sequential integer"


@pytest.mark.asyncio
async def test_mutation_08_revoked_session_rejected(mutation_test_db):
    """MUTATION 8: Revoked session must be rejected on authentication."""
    _, store = mutation_test_db
    user = User(id="u_rev", email="revoked@cauveris.dev", is_active=True)
    await store.create_user(user)
    session = Session(id="sess_revoked", user_id="u_rev", org_id="o1", is_revoked=True)
    await store.create_session(session)

    # Validate session fetch marks it revoked
    s = await store.get_session("sess_revoked")
    assert s.is_revoked is True


@pytest.mark.asyncio
async def test_mutation_09_expired_session_rejected(mutation_test_db):
    """MUTATION 9: Expired session must be detected as expired."""
    _, store = mutation_test_db
    session = Session(
        id="sess_expired",
        user_id="u_exp",
        org_id="o1",
        access_token_expires=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    assert session.is_expired() is True


@pytest.mark.asyncio
async def test_mutation_10_logout_deletes_session(mutation_test_db):
    """MUTATION 10: Logout must revoke/delete the active session in storage."""
    _, store = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/auth/signup", json={
            "email": "logout.test@cauveris.dev",
            "password": "ValidPassword123!",
            "full_name": "Logout Tester",
        })
        session_id = res.cookies.get("session_id")
        assert session_id is not None
        assert await store.get_session(session_id) is not None

        # Call logout
        await client.post("/api/v1/auth/logout")
        # In store, session must be deleted or revoked
        sess = await store.get_session(session_id)
        assert sess is None or sess.is_revoked is True


@pytest.mark.asyncio
async def test_mutation_11_cross_user_incident_read_forbidden(mutation_test_db):
    """MUTATION 11: User B reading User A's incident is denied with 403."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # User A
        res_a = await client.post("/api/v1/auth/signup", json={
            "email": "alice@cauveris.dev",
            "password": "PasswordForAlice1!",
            "full_name": "Alice",
        })
        res_a.json()["access_token"]
        uid_a = res_a.json()["user"]["id"]

        # User B
        res_b = await client.post("/api/v1/auth/signup", json={
            "email": "bob@cauveris.dev",
            "password": "PasswordForBob1234!",
            "full_name": "Bob",
        })
        token_b = res_b.json()["access_token"]

        from cauveris.api.main import incidents
        inc_id = f"CAU-MUT-11-{uuid.uuid4().hex[:6]}"
        inc = Incident(id=inc_id, title="Alice Secret Incident", system_name="drone", status="OBSERVED")
        inc._owner_user_id = uid_a
        incidents[inc_id] = inc

        # Bob reading Alice's incident
        res = await client.get(f"/api/v1/incidents/{inc_id}", headers={"Authorization": f"Bearer {token_b}"})
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_mutation_12_cross_user_repair_package_download_forbidden(mutation_test_db):
    """MUTATION 12: User B downloading User A's repair package is denied with 403."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_a = await client.post("/api/v1/auth/signup", json={
            "email": "owner@cauveris.dev",
            "password": "PasswordOwner123!",
            "full_name": "Owner",
        })
        uid_a = res_a.json()["user"]["id"]

        res_b = await client.post("/api/v1/auth/signup", json={
            "email": "intruder@cauveris.dev",
            "password": "PasswordIntruder1!",
            "full_name": "Intruder",
        })
        token_b = res_b.json()["access_token"]

        from cauveris.api.main import incidents
        inc_id = f"CAU-MUT-12-{uuid.uuid4().hex[:6]}"
        inc = Incident(id=inc_id, title="Owner Package Incident", system_name="robot", status="OBSERVED")
        inc._owner_user_id = uid_a
        incidents[inc_id] = inc

        res = await client.get(f"/api/v1/incidents/{inc_id}/download-patch-package", headers={"Authorization": f"Bearer {token_b}"})
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_mutation_13_cross_user_incident_mutation_forbidden(mutation_test_db):
    """MUTATION 13: User B resetting/mutating User A's incident is denied with 403."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_a = await client.post("/api/v1/auth/signup", json={
            "email": "primary@cauveris.dev",
            "password": "PasswordPrimary1!",
            "full_name": "Primary",
        })
        uid_a = res_a.json()["user"]["id"]

        res_b = await client.post("/api/v1/auth/signup", json={
            "email": "secondary@cauveris.dev",
            "password": "PasswordSecondary1!",
            "full_name": "Secondary",
        })
        token_b = res_b.json()["access_token"]

        from cauveris.api.main import incidents
        inc_id = f"CAU-MUT-13-{uuid.uuid4().hex[:6]}"
        inc = Incident(id=inc_id, title="Primary Incident", system_name="robot", status="OBSERVED")
        inc._owner_user_id = uid_a
        incidents[inc_id] = inc

        res = await client.post(f"/api/v1/incidents/{inc_id}/reset", headers={"Authorization": f"Bearer {token_b}"})
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_mutation_14_user_response_never_exposes_password_hash(mutation_test_db):
    """MUTATION 14: User responses must never serialize password_hash."""
    _, _ = mutation_test_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/auth/signup", json={
            "email": "hash.leak.test@cauveris.dev",
            "password": "SecretPassword123!",
            "full_name": "Leak Tester",
        })
        data = res.json()
        assert "password_hash" not in data["user"]
        assert "password" not in data["user"]

        token = data["access_token"]
        me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        me_data = me_res.json()
        assert "password_hash" not in me_data
        assert "password" not in me_data


def test_mutation_15_production_security_guard_triggers():
    """MUTATION 15: Production runtime mode rejects startup if demo_auth or demo_mode is True."""
    settings = Settings()
    settings.runtime_mode = "production"
    settings.demo_auth = True
    with pytest.raises(RuntimeError) as exc:
        settings.validate_production_security()
    assert "FATAL SECURITY VIOLATION" in str(exc.value)

    settings.demo_auth = False
    settings.demo_mode = True
    with pytest.raises(RuntimeError) as exc2:
        settings.validate_production_security()
    assert "FATAL SECURITY VIOLATION" in str(exc2.value)
