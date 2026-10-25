"""
Regression tests for refresh token rotation and reuse detection.

This tests the security fix for: after a client refreshes, the previous refresh
token must be invalidated (rotation detection). Presenting an already-rotated
refresh token must be rejected with 401.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from cauveris.api.main import app
from cauveris.auth import (
    get_auth_store,
    init_auth_store,
    TokenManager,
    User,
    UserRole,
    Organization,
    Session,
)
from cauveris.config import get_settings
import uuid


@pytest.fixture
async def auth_setup():
    """Set up auth store and create a test user with tokens."""
    settings = get_settings()
    if get_auth_store() is None:
        init_auth_store(backend=settings.auth_backend, redis_url=settings.auth_redis_url)
    auth_store = get_auth_store()
    token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)

    # Create organization with unique slug
    unique_slug = f"test-org-{uuid.uuid4().hex[:8]}"
    org = await auth_store.create_org(
        Organization(
            name="Test Org",
            slug=unique_slug,
            description="Test organization",
        )
    )

    # Create user
    user = User(
        email=f"test-{uuid.uuid4().hex[:8]}@cauveris.local",
        full_name="Test User",
        role=UserRole.ENGINEER,
        org_id=org.id,
        is_active=True,
    )
    user.set_password("test123456")
    user = await auth_store.create_user(user)

    # Create session
    session = Session(
        user_id=user.id,
        org_id=org.id,
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )
    # Generate tokens
    session.access_token = token_manager.create_access_token(user, session, org)
    session.refresh_token = token_manager.create_refresh_token(session)
    session = await auth_store.create_session(session)

    return {
        "user": user,
        "org": org,
        "session": session,
        "auth_store": auth_store,
        "token_manager": token_manager,
    }


@pytest.mark.asyncio
async def test_refresh_token_rotation_invalidates_old_token(auth_setup):
    """
    Test that after a successful refresh, the OLD refresh token is rejected
    and the NEW refresh token works for subsequent refreshes.
    """
    session = auth_setup["session"]
    auth_store = auth_setup["auth_store"]

    old_refresh_token = session.refresh_token
    old_access_token = session.access_token

    # First refresh - should succeed
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert res.status_code == 200, f"First refresh failed: {res.text}"
        data = res.json()
        new_access_token = data["access_token"]
        new_refresh_token = data["refresh_token"]
        assert new_access_token != old_access_token, "Access token should rotate"
        assert new_refresh_token != old_refresh_token, "Refresh token should rotate"

    # Verify session was updated with new tokens
    updated_session = await auth_store.get_session(session.id)
    assert updated_session is not None
    assert updated_session.refresh_token == new_refresh_token
    assert updated_session.access_token == new_access_token

    # Second refresh with OLD refresh token - should FAIL (401)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert res.status_code == 401, f"Old refresh token should be rejected, got {res.status_code}: {res.text}"
        assert "invalid" in res.json().get("detail", "").lower() or "expired" in res.json().get("detail", "").lower()

    # Third refresh with NEW refresh token - should SUCCEED
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_refresh_token},
        )
        assert res.status_code == 200, f"Second refresh with new token failed: {res.text}"
        data = res.json()
        newest_access_token = data["access_token"]
        newest_refresh_token = data["refresh_token"]
        assert newest_access_token != new_access_token, "Access token should rotate again"
        assert newest_refresh_token != new_refresh_token, "Refresh token should rotate again"


@pytest.mark.asyncio
async def test_refresh_token_reuse_detection_via_token_manager(auth_setup):
    """
    Test token rotation reuse detection at the TokenManager/AuthStore level
    without HTTP layer, verifying the core logic.
    """
    auth_store = auth_setup["auth_store"]
    token_manager = auth_setup["token_manager"]
    user = auth_setup["user"]
    org = auth_setup["org"]
    session = auth_setup["session"]

    # Get the current refresh token from the session
    current_refresh = session.refresh_token

    # Manually rotate the token (simulate what the endpoint does)
    new_access = token_manager.create_access_token(user, session, org)
    new_refresh = token_manager.create_refresh_token(session)
    await auth_store.update_session(session)

    # Verify the new tokens are on the session
    assert session.refresh_token == new_refresh
    assert session.access_token == new_access

    # Verify the old refresh token is no longer indexed
    # (it should not map to the session anymore)
    old_session = await auth_store.get_session_by_refresh_token(current_refresh)
    assert old_session is None, "Old refresh token should not resolve to session after rotation"

    # Verify the new refresh token IS indexed
    new_session = await auth_store.get_session_by_refresh_token(new_refresh)
    assert new_session is not None
    assert new_session.id == session.id


@pytest.mark.asyncio
async def test_multiple_sequential_refreshes_work(auth_setup):
    """
    Test that multiple sequential refreshes work correctly (each new token
    can be used for the next refresh).
    """
    session = auth_setup["session"]
    auth_store = auth_setup["auth_store"]

    current_refresh = session.refresh_token

    # Perform 5 sequential refreshes
    for i in range(5):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": current_refresh},
            )
            assert res.status_code == 200, f"Refresh {i+1} failed: {res.text}"
            data = res.json()
            current_refresh = data["refresh_token"]

    # Verify final session state
    final_session = await auth_store.get_session(session.id)
    assert final_session is not None
    assert final_session.refresh_token == current_refresh

    # The last refresh token should still work for one more refresh
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": current_refresh},
        )
        assert res.status_code == 200, "Final refresh should work"


@pytest.mark.asyncio
async def test_expired_refresh_token_rejected(auth_setup):
    """Test that expired refresh tokens are rejected."""
    from datetime import datetime, timedelta, timezone
    import jwt

    token_manager = auth_setup["token_manager"]
    user = auth_setup["user"]
    org = auth_setup["org"]

    # Create a session with an already-expired refresh token
    past = datetime.now(timezone.utc) - timedelta(days=1)
    expired_session = Session(
        user_id=user.id,
        org_id=org.id,
        ip_address="127.0.0.1",
        user_agent="test-agent",
        refresh_token_expires=past,
    )
    # Manually create an expired refresh token
    expired_payload = {
        "sub": user.id,
        "session_id": expired_session.id,
        "iat": int((past - timedelta(days=30)).timestamp()),
        "exp": int(past.timestamp()),
        "type": "refresh",
        "jti": "expired-jti",
    }

    # Actually encode an expired token
    expired_refresh = jwt.encode(
        expired_payload, token_manager.secret_key, algorithm=token_manager.algorithm
    )

    # Try to use it - should fail with 401
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": expired_refresh},
        )
        assert res.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
