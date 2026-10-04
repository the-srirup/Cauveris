"""
Pytest configuration and shared fixtures for Cauveris tests.
"""
import pytest
import asyncio
from cauveris.api.main import (
    incidents, pipeline_tasks, pipeline_progress, pipeline_contexts,
    _incident_creation_timestamps, _active_incidents_per_user, _retained_incidents_per_user,
    _active_incidents_per_org, _retained_incidents_per_org, _anonymous_incident_count,
    _global_active_incidents
)


def reset_all_state():
    """Reset all global in-memory state."""
    incidents.clear()
    pipeline_tasks.clear()
    pipeline_progress.clear()
    pipeline_contexts.clear()
    _incident_creation_timestamps.clear()
    _active_incidents_per_user.clear()
    _retained_incidents_per_user.clear()
    _active_incidents_per_org.clear()
    _retained_incidents_per_org.clear()
    global _anonymous_incident_count, _global_active_incidents
    _anonymous_incident_count = 0
    _global_active_incidents = 0
    from cauveris.idempotency import get_idempotency_store
    store = get_idempotency_store()
    if store is not None:
        if hasattr(store, '_data'):
            store._data.clear()
    from cauveris.rate_limit import get_rate_limiter
    limiter = get_rate_limiter()
    if limiter is not None:
        if hasattr(limiter, '_data'):
            limiter._data.clear()
        if hasattr(limiter, '_locks'):
            limiter._locks.clear()
    from cauveris.concurrency import get_concurrency_manager
    mgr = get_concurrency_manager()
    if mgr is not None:
        if mgr._store is not None:
            if hasattr(mgr._store, '_slots'):
                mgr._store._slots.clear()
            if hasattr(mgr._store, '_waiting'):
                mgr._store._waiting.clear()
            if hasattr(mgr._store, '_locks'):
                mgr._store._locks.clear()
    from cauveris.job_queue import get_job_queue
    jq = get_job_queue()
    if jq is not None:
        if jq._backend is not None:
            if hasattr(jq._backend, '_queues'):
                jq._backend._queues.clear()
            if hasattr(jq._backend, '_processing'):
                jq._backend._processing.clear()
            if hasattr(jq._backend, '_dead_letter'):
                jq._backend._dead_letter.clear()
            if hasattr(jq._backend, '_completed'):
                jq._backend._completed.clear()
            if hasattr(jq._backend, '_stats'):
                jq._backend._stats = {
                    "enqueued": 0, "dequeued": 0, "completed": 0, "failed": 0,
                    "dead_lettered": 0, "cancelled": 0, "expired": 0, "rejected_full": 0
                }
    # Reset auth store
    from cauveris.auth import get_auth_store
    auth_store = get_auth_store()
    if auth_store is not None:
        if hasattr(auth_store, '_users'):
            auth_store._users.clear()
        if hasattr(auth_store, '_orgs'):
            auth_store._orgs.clear()
        if hasattr(auth_store, '_sessions'):
            auth_store._sessions.clear()
        if hasattr(auth_store, '_api_keys'):
            auth_store._api_keys.clear()
        if hasattr(auth_store, '_audit_logs'):
            auth_store._audit_logs.clear()
        # Re-add demo user if needed
        from cauveris.auth import User, UserRole, Organization
        demo_org = Organization(
            id="org_demo",
            name="Demo Organization",
            slug="demo",
            description="Demo organization for testing",
            owner_user_id="usr_demo",
            is_active=True,
        )
        demo_user = User(
            id="usr_demo",
            email="demo@cauveris.local",
            full_name="Demo User",
            role=UserRole.ENGINEER,
            org_id="org_demo",
            is_active=True,
        )
        demo_user.set_password("demo123456")
        auth_store._orgs["org_demo"] = demo_org
        auth_store._users["usr_demo"] = demo_user


@pytest.fixture(autouse=True)
def clean_state(request):
    """Reset global in-memory state before and after each test."""
    test_name = request.node.name if request.node else "unknown"
    print(f"\n>>> SETUP: {test_name}")
    reset_all_state()
    yield
    print(f">>> TEARDOWN: {test_name}")
    reset_all_state()


@pytest.fixture
async def test_user():
    """Create a test user and return auth headers."""
    from cauveris.auth import get_auth_store, init_auth_store, TokenManager, UserRole, Organization, Session
    from cauveris.config import get_settings
    import uuid

    settings = get_settings()
    # Initialize auth store if not already
    if get_auth_store() is None:
        init_auth_store(backend=settings.auth_backend, redis_url=settings.auth_redis_url)
    auth_store = get_auth_store()
    token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)

    # Create organization with unique slug
    unique_slug = f"test-org-{uuid.uuid4().hex[:8]}"
    org = await auth_store.create_org(Organization(
        name="Test Org",
        slug=unique_slug,
        description="Test organization",
    ))

    # Create user
    from cauveris.auth import User
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
        "access_token": session.access_token,
        "headers": {
            "Authorization": f"Bearer {session.access_token}",
            "Cookie": f"access_token={session.access_token}; refresh_token={session.refresh_token}"
        }
    }


@pytest.fixture
async def test_user_admin():
    """Create an admin test user and return auth headers."""
    from cauveris.auth import get_auth_store, init_auth_store, TokenManager, UserRole, Organization, Session
    from cauveris.config import get_settings
    import uuid

    settings = get_settings()
    # Initialize auth store if not already
    if get_auth_store() is None:
        init_auth_store(backend=settings.auth_backend, redis_url=settings.auth_redis_url)
    auth_store = get_auth_store()
    token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)

    # Create organization with unique slug
    unique_slug = f"admin-org-{uuid.uuid4().hex[:8]}"
    org = await auth_store.create_org(Organization(
        name="Admin Org",
        slug=unique_slug,
        description="Admin test organization",
    ))

    # Create user
    from cauveris.auth import User
    user = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@cauveris.local",
        full_name="Admin User",
        role=UserRole.ADMIN,
        org_id=org.id,
        is_active=True,
    )
    user.set_password("admin123456")
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
        "access_token": session.access_token,
        "headers": {
            "Authorization": f"Bearer {session.access_token}",
            "Cookie": f"access_token={session.access_token}; refresh_token={session.refresh_token}"
        }
    }