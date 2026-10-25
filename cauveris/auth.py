"""
Authentication and Authorization Module for Cauveris.
Provides user authentication, JWT token management, session handling, and RBAC.
"""

import asyncio
import hashlib
import hmac
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import logging

import jwt
from pydantic import BaseModel


logger = logging.getLogger(__name__)

# Password hashing context
# Use a simple hash for testing (replace with proper bcrypt in production)


def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt."""
    salt = secrets.token_hex(16)
    hash_val = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"sha256${salt}${hash_val}"


try:
    # NOTE: passlib 1.7.4 cannot detect the backend of bcrypt >= 4.1 and
    # raises "password cannot be longer than 72 bytes" for every input, so the
    # bcrypt library is used directly instead of through passlib.
    import bcrypt as _bcrypt

    _BCRYPT_MAX_BYTES = 72

    def _bcrypt_hash(secret: str) -> str:
        return _bcrypt.hashpw(
            secret.encode("utf-8")[:_BCRYPT_MAX_BYTES], _bcrypt.gensalt()
        ).decode("ascii")

    def _bcrypt_verify(secret: str, hashed: str) -> bool:
        try:
            return bool(
                _bcrypt.checkpw(
                    secret.encode("utf-8")[:_BCRYPT_MAX_BYTES], hashed.encode("ascii")
                )
            )
        except (ValueError, TypeError):
            return False

except Exception:  # pragma: no cover - bcrypt is an optional hardening
    _bcrypt = None  # type: ignore[assignment]

    def _bcrypt_hash(secret: str) -> str:  # type: ignore[misc]
        return hash_password(secret)

    def _bcrypt_verify(secret: str, hashed: str) -> bool:  # type: ignore[misc]
        return verify_password(secret, hashed)


_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$", "$2x$")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a secret against a stored hash.

    Supports the built-in salted SHA-256 format (``sha256$salt$hash``) as well
    as bcrypt hashes (``$2b$...``) produced for API keys.
    """
    if not password_hash:
        return False
    if password_hash.startswith("sha256$"):
        parts = password_hash.split("$", 2)
        if len(parts) != 3:
            return False
        _, salt, hash_val = parts
        if not salt or not hash_val:
            return False
        return hmac.compare_digest(
            hashlib.sha256((password + salt).encode()).hexdigest(), hash_val
        )
    if password_hash.startswith(_BCRYPT_PREFIXES):
        return _bcrypt_verify(password, password_hash)
    return False


# Create a mock context for compatibility
class MockPwdContext:
    def hash(self, password: str) -> str:
        return hash_password(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return verify_password(password, password_hash)


class BcryptPwdContext:
    """Hashing context for high-entropy API keys."""

    def hash(self, password: str) -> str:
        return _bcrypt_hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return verify_password(password, password_hash)


pwd_context = MockPwdContext()
api_key_pwd_context = BcryptPwdContext()


class UserRole(str, Enum):
    """System roles with hierarchical permissions."""

    VIEWER = "viewer"  # Read-only access to assigned incidents
    ANALYST = "analyst"  # Can run investigations, validate evidence
    ENGINEER = "engineer"  # Can run simulations, engineer mode, apply patches
    ADMIN = "admin"  # Full system access, user/org management
    SUPER_ADMIN = "super_admin"  # Platform-level admin, cross-org access


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"
    RESET_PASSWORD = "reset_password"
    EMAIL_VERIFICATION = "email_verification"


class AuthMethod(str, Enum):
    PASSWORD = "password"
    OAUTH_GOOGLE = "oauth_google"
    OAUTH_GITHUB = "oauth_github"
    OAUTH_MICROSOFT = "oauth_microsoft"
    API_KEY = "api_key"
    MFA_TOTP = "mfa_totp"


# Role permission matrix
_VIEWER_PERMISSIONS: Set[str] = {
    "incident:read",
    "incident:list",
    "timeline:read",
    "hypothesis:read",
    "experiment:read",
    "patch:read",
    "report:read",
    "evidence:read",
    "job_queue:read",
    "concurrency:read",
}

_ANALYST_PERMISSIONS: Set[str] = {
    "incident:read",
    "incident:list",
    "incident:create",
    "incident:update_own",
    "incident:validate",
    "timeline:read",
    "hypothesis:read",
    "hypothesis:create",
    "experiment:read",
    "experiment:create",
    "patch:read",
    "report:read",
    "evidence:read",
    "evidence:upload",
    "evidence:validate",
    "pipeline:start",
    "pipeline:cancel_own",
    "job_queue:read",
    "job_queue:submit",
    "concurrency:read",
}

_ENGINEER_PERMISSIONS: Set[str] = {
    "incident:read",
    "incident:list",
    "incident:create",
    "incident:update_own",
    "incident:reconstruct",
    "incident:cancel",
    "incident:reset",
    "incident:retry",
    "incident:validate",
    "timeline:read",
    "hypothesis:read",
    "hypothesis:create",
    "hypothesis:test",
    "experiment:read",
    "experiment:create",
    "experiment:run",
    "patch:read",
    "patch:create",
    "patch:apply",
    "patch:download",
    "patch:export",
    "report:read",
    "evidence:read",
    "evidence:upload",
    "evidence:validate",
    "pipeline:start",
    "pipeline:cancel_own",
    "simulation:run",
    "engineer_mode:access",
    "job_queue:read",
    "job_queue:submit",
    "job_queue:cancel",
    "concurrency:read",
}

# Permissions that only administrators hold.
_ADMIN_PERMISSIONS: Set[str] = {
    "incident:*",
    "incident:update_any",
    "incident:delete_any",
    "user:read",
    "user:create",
    "user:update",
    "user:delete",
    "org:read",
    "org:create",
    "org:update",
    "org:delete",
    "quota:override",
    "audit:read",
    "system:config",
    "api_key:manage",
    "job_queue:*",
    "job_queue:manage_any",
    "concurrency:*",
    "concurrency:manage",
}

ROLE_PERMISSIONS: Dict[UserRole, Set[str]] = {
    UserRole.VIEWER: set(_VIEWER_PERMISSIONS),
    UserRole.ANALYST: set(_ANALYST_PERMISSIONS),
    UserRole.ENGINEER: set(_ENGINEER_PERMISSIONS),
    UserRole.ADMIN: (
        # All analyst + engineer permissions plus the admin-only ones.
        _ANALYST_PERMISSIONS | _ENGINEER_PERMISSIONS | _ADMIN_PERMISSIONS
    ),
    UserRole.SUPER_ADMIN: {
        "*",  # All permissions
    },
}

# Canonical list of concrete permissions. Wildcards are expanded against this
# set, so every permission string used anywhere in the codebase should be
# listed here.
ALL_PERMISSIONS: Set[str] = {
    "incident:read",
    "incident:list",
    "incident:create",
    "incident:update_own",
    "incident:update_any",
    "incident:delete_any",
    "incident:reconstruct",
    "incident:cancel",
    "incident:reset",
    "incident:retry",
    "incident:validate",
    "timeline:read",
    "hypothesis:read",
    "hypothesis:create",
    "hypothesis:test",
    "experiment:read",
    "experiment:create",
    "experiment:run",
    "patch:read",
    "patch:create",
    "patch:apply",
    "patch:download",
    "patch:export",
    "report:read",
    "evidence:read",
    "evidence:upload",
    "evidence:validate",
    "pipeline:start",
    "pipeline:cancel_own",
    "pipeline:cancel_any",
    "simulation:run",
    "engineer_mode:access",
    "user:read",
    "user:create",
    "user:update",
    "user:delete",
    "org:read",
    "org:create",
    "org:update",
    "org:delete",
    "quota:override",
    "audit:read",
    "system:config",
    "api_key:manage",
    "job_queue:read",
    "job_queue:submit",
    "job_queue:cancel",
    "job_queue:manage_any",
    "concurrency:read",
    "concurrency:manage",
}


def expand_permissions(perms: Set[str]) -> Set[str]:
    """Expand wildcard permissions into concrete permission names.

    ``*`` grants every known permission and is itself retained so callers that
    test for the literal wildcard keep working. ``namespace:*`` grants every
    known permission in that namespace and the wildcard form is retained so
    namespace checks still work for permissions added later.
    """
    expanded: Set[str] = set()
    for perm in perms:
        if perm == "*":
            expanded.update(ALL_PERMISSIONS)
            expanded.add("*")
        elif perm.endswith(":*"):
            prefix = perm[:-2]
            expanded.update(p for p in ALL_PERMISSIONS if p.startswith(prefix))
            expanded.add(perm)
        else:
            expanded.add(perm)
    return expanded


@dataclass
class User:
    """User account model."""

    id: str = field(default_factory=lambda: f"usr_{uuid.uuid4().hex[:16]}")
    email: str = ""
    email_verified: bool = False
    password_hash: str = ""
    full_name: str = ""
    avatar_url: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    org_id: str = ""
    is_active: bool = True
    is_superuser: bool = False
    mfa_enabled: bool = False
    mfa_secret: Optional[str] = None
    last_login: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def verify_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.password_hash)

    def set_password(self, password: str) -> None:
        self.password_hash = pwd_context.hash(password)

    def has_permission(self, permission: str) -> bool:
        """Check whether the role grants a permission.

        Honours the global ``*`` wildcard (super admin) as well as namespace
        wildcards such as ``incident:*``.
        """
        perms = expand_permissions(ROLE_PERMISSIONS.get(self.role, set()))
        if "*" in perms:
            return True
        if permission in perms:
            return True
        namespace = permission.split(":", 1)[0]
        return f"{namespace}:*" in perms

    def has_any_permission(self, permissions: List[str]) -> bool:
        return any(self.has_permission(p) for p in permissions)

    def has_all_permissions(self, permissions: List[str]) -> bool:
        return all(self.has_permission(p) for p in permissions)


@dataclass
class Organization:
    """Organization/tenant model."""

    id: str = field(default_factory=lambda: f"org_{uuid.uuid4().hex[:16]}")
    name: str = ""
    slug: str = ""
    description: str = ""
    owner_user_id: str = ""
    is_active: bool = True
    settings: Dict[str, Any] = field(default_factory=dict)
    quotas: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_quota(self, key: str, default: int = 0) -> int:
        return self.quotas.get(key, default)


@dataclass
class Session:
    """User session model."""

    id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:16]}")
    user_id: str = ""
    org_id: str = ""
    access_token: str = ""
    refresh_token: str = ""
    access_token_expires: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=1)
    )
    refresh_token_expires: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=30)
    )
    ip_address: str = ""
    user_agent: str = ""
    device_fingerprint: Optional[str] = None
    is_revoked: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.access_token_expires

    def is_refresh_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.refresh_token_expires

    def revoke(self) -> None:
        self.is_revoked = True


API_KEY_PREFIX_LENGTH = 8


@dataclass
class APIKey:
    """API key for service-to-service authentication."""
    id: str = field(default_factory=lambda: f"key_{uuid.uuid4().hex[:16]}")
    name: str = ""
    org_id: str = ""
    user_id: str = ""  # Creator
    key_hash: str = ""
    key_prefix: str = ""  # First 8 chars for identification
    permissions: List[str] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)  # e.g., ["incidents:read", "pipelines:write"]
    rate_limit: Optional[int] = None  # Requests per minute
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def verify_key(self, raw_key: str) -> bool:
        return api_key_pwd_context.verify(raw_key, self.key_hash)

    def set_key(self, raw_key: str) -> None:
        self.key_hash = api_key_pwd_context.hash(raw_key)
        self.key_prefix = raw_key[:API_KEY_PREFIX_LENGTH]


@dataclass
class AuditLogEntry:
    """Security audit log entry."""

    id: str = field(default_factory=lambda: f"aud_{uuid.uuid4().hex[:16]}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    session_id: Optional[str] = None
    api_key_id: Optional[str] = None
    auth_method: Optional[AuthMethod] = None
    action: str = ""  # e.g., "incident.create", "pipeline.start", "auth.login"
    resource_type: str = ""  # e.g., "incident", "user", "org"
    resource_id: Optional[str] = None
    resource_owner_id: Optional[str] = None
    decision: str = ""  # "allow", "deny", "error"
    reason: Optional[str] = None
    ip_address: str = ""
    user_agent: str = ""
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuthStore(ABC):
    """Abstract storage interface for auth data."""

    @abstractmethod
    async def create_user(self, user: User) -> User:
        pass

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[User]:
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[User]:
        pass

    @abstractmethod
    async def update_user(self, user: User) -> User:
        pass

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        pass

    @abstractmethod
    async def list_users(
        self, org_id: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[User]:
        pass

    @abstractmethod
    async def create_org(self, org: Organization) -> Organization:
        pass

    @abstractmethod
    async def get_org(self, org_id: str) -> Optional[Organization]:
        pass

    @abstractmethod
    async def get_org_by_slug(self, slug: str) -> Optional[Organization]:
        pass

    @abstractmethod
    async def update_org(self, org: Organization) -> Organization:
        pass

    @abstractmethod
    async def delete_org(self, org_id: str) -> bool:
        pass

    @abstractmethod
    async def create_session(self, session: Session) -> Session:
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Session]:
        pass

    @abstractmethod
    async def get_session_by_access_token(self, token: str) -> Optional[Session]:
        pass

    @abstractmethod
    async def get_session_by_refresh_token(self, token: str) -> Optional[Session]:
        pass

    @abstractmethod
    async def update_session(self, session: Session) -> Session:
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        pass

    @abstractmethod
    async def revoke_user_sessions(
        self, user_id: str, exclude_session_id: Optional[str] = None
    ) -> int:
        pass

    async def revoke_sessions_by_id(self, session_ids: List[str]) -> int:
        """
        Revoke the given sessions. Returns the number of sessions revoked.

        The default implementation works with any backend that supports
        ``get_session``/``update_session``; backends that keep additional
        token indexes should override it.
        """
        revoked = 0
        for session_id in session_ids:
            session = await self.get_session(session_id)
            if session is None or session.is_revoked:
                continue
            session.revoke()
            await self.update_session(session)
            revoked += 1
        return revoked

    @abstractmethod
    async def list_user_sessions(self, user_id: str) -> List[Session]:
        pass

    @abstractmethod
    async def create_api_key(self, api_key: APIKey) -> APIKey:
        pass

    @abstractmethod
    async def get_api_key(self, key_id: str) -> Optional[APIKey]:
        pass

    @abstractmethod
    async def get_api_key_by_prefix(self, prefix: str) -> Optional[APIKey]:
        pass

    @abstractmethod
    async def list_api_keys(self, org_id: str, user_id: Optional[str] = None) -> List[APIKey]:
        pass

    @abstractmethod
    async def update_api_key(self, api_key: APIKey) -> APIKey:
        pass

    @abstractmethod
    async def delete_api_key(self, key_id: str) -> bool:
        pass

    @abstractmethod
    async def write_audit_log(self, entry: AuditLogEntry) -> None:
        pass

    @abstractmethod
    async def read_audit_logs(
        self,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        action: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLogEntry]:
        pass


class InMemoryAuthStore(AuthStore):
    """In-memory auth store for development/testing."""

    def __init__(self):
        self._users: Dict[str, User] = {}
        self._users_by_email: Dict[str, str] = {}
        self._orgs: Dict[str, Organization] = {}
        self._orgs_by_slug: Dict[str, str] = {}
        self._sessions: Dict[str, Session] = {}
        self._sessions_by_access: Dict[str, str] = {}
        self._sessions_by_refresh: Dict[str, str] = {}
        self._api_keys: Dict[str, APIKey] = {}
        self._api_keys_by_prefix: Dict[str, List[str]] = {}
        self._audit_logs: List[AuditLogEntry] = []
        self._lock = asyncio.Lock()

    async def list_user_sessions(self, user_id: str) -> List[Session]:
        """List all sessions for a user."""
        return [s for s in self._sessions.values() if s.user_id == user_id]

    async def create_user(self, user: User) -> User:
        async with self._lock:
            if user.email.lower() in self._users_by_email:
                raise ValueError(f"User with email {user.email} already exists")
            self._users[user.id] = user
            self._users_by_email[user.email.lower()] = user.id
        return user

    async def get_user(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        user_id = self._users_by_email.get(email.lower())
        return self._users.get(user_id) if user_id else None

    async def update_user(self, user: User) -> User:
        async with self._lock:
            user.updated_at = datetime.now(timezone.utc)
            if user.id in self._users:
                old_email = self._users[user.id].email.lower()
                if old_email != user.email.lower():
                    self._users_by_email.pop(old_email, None)
                    self._users_by_email[user.email.lower()] = user.id
            self._users[user.id] = user
        return user

    async def delete_user(self, user_id: str) -> bool:
        async with self._lock:
            user = self._users.pop(user_id, None)
            if user:
                self._users_by_email.pop(user.email.lower(), None)
                return True
        return False

    async def list_users(
        self, org_id: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[User]:
        users = list(self._users.values())
        if org_id:
            users = [u for u in users if u.org_id == org_id]
        return users[offset : offset + limit]

    async def create_org(self, org: Organization) -> Organization:
        async with self._lock:
            if org.slug.lower() in self._orgs_by_slug:
                raise ValueError(f"Organization with slug {org.slug} already exists")
            self._orgs[org.id] = org
            self._orgs_by_slug[org.slug.lower()] = org.id
        return org

    async def get_org(self, org_id: str) -> Optional[Organization]:
        return self._orgs.get(org_id)

    async def get_org_by_slug(self, slug: str) -> Optional[Organization]:
        org_id = self._orgs_by_slug.get(slug.lower())
        return self._orgs.get(org_id) if org_id else None

    async def update_org(self, org: Organization) -> Organization:
        async with self._lock:
            org.updated_at = datetime.now(timezone.utc)
            if org.id in self._orgs:
                old_slug = self._orgs[org.id].slug.lower()
                if old_slug != org.slug.lower():
                    self._orgs_by_slug.pop(old_slug, None)
                    self._orgs_by_slug[org.slug.lower()] = org.id
            self._orgs[org.id] = org
        return org

    async def delete_org(self, org_id: str) -> bool:
        async with self._lock:
            org = self._orgs.pop(org_id, None)
            if org:
                self._orgs_by_slug.pop(org.slug.lower(), None)
                return True
        return False

    async def create_session(self, session: Session) -> Session:
        async with self._lock:
            self._sessions[session.id] = session
            self._sessions_by_access[session.access_token] = session.id
            self._sessions_by_refresh[session.refresh_token] = session.id
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    async def get_session_by_access_token(self, token: str) -> Optional[Session]:
        session_id = self._sessions_by_access.get(token)
        return self._sessions.get(session_id) if session_id else None

    async def get_session_by_refresh_token(self, token: str) -> Optional[Session]:
        session_id = self._sessions_by_refresh.get(token)
        return self._sessions.get(session_id) if session_id else None

    async def update_session(self, session: Session) -> Session:
        async with self._lock:
            session.last_activity = datetime.now(timezone.utc)
            # Update token indexes - the session may have rotated its refresh token
            # Remove old refresh token from index if present (by checking all entries for this session)
            old_refresh_tokens = [
                token for token, sid in self._sessions_by_refresh.items() if sid == session.id
            ]
            for old_token in old_refresh_tokens:
                self._sessions_by_refresh.pop(old_token, None)
            # Add the current refresh token
            if session.refresh_token:
                self._sessions_by_refresh[session.refresh_token] = session.id
            # Also update access token index
            if session.access_token:
                self._sessions_by_access[session.access_token] = session.id
            self._sessions[session.id] = session
        return session

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                self._sessions_by_access.pop(session.access_token, None)
                self._sessions_by_refresh.pop(session.refresh_token, None)
                return True
        return False

    async def revoke_user_sessions(
        self, user_id: str, exclude_session_id: Optional[str] = None
    ) -> int:
        async with self._lock:
            count = 0
            for session in list(self._sessions.values()):
                if session.user_id == user_id and session.id != exclude_session_id:
                    session.revoke()
                    self._sessions_by_access.pop(session.access_token, None)
                    self._sessions_by_refresh.pop(session.refresh_token, None)
                    count += 1
        return count

    async def revoke_sessions_by_id(self, session_ids: List[str]) -> int:
        async with self._lock:
            count = 0
            for session_id in session_ids:
                session = self._sessions.get(session_id)
                if session is None or session.is_revoked:
                    continue
                session.revoke()
                self._sessions_by_access.pop(session.access_token, None)
                self._sessions_by_refresh.pop(session.refresh_token, None)
                count += 1
        return count

    async def create_api_key(self, api_key: APIKey) -> APIKey:
        async with self._lock:
            self._api_keys[api_key.id] = api_key
            # Several keys can legitimately share the same short prefix, so
            # every candidate is kept; otherwise a new key would shadow an
            # existing one and make it permanently unusable.
            self._api_keys_by_prefix.setdefault(api_key.key_prefix, []).append(api_key.id)
        return api_key

    async def get_api_key(self, key_id: str) -> Optional[APIKey]:
        return self._api_keys.get(key_id)

    async def get_api_key_by_prefix(self, prefix: str) -> Optional[APIKey]:
        for key_id in self._api_keys_by_prefix.get(prefix) or []:
            key = self._api_keys.get(key_id)
            if key is not None:
                return key
        return None

    async def get_api_key_by_raw_key(self, raw_key: str) -> Optional[APIKey]:
        """Resolve an API key from its raw secret.

        The stored prefix is only a short, collision-prone label, so every
        candidate sharing the prefix is verified before one is returned.
        """
        prefix = raw_key[:API_KEY_PREFIX_LENGTH]
        for key_id in self._api_keys_by_prefix.get(prefix) or []:
            key = self._api_keys.get(key_id)
            if key is not None and key.verify_key(raw_key):
                return key
        return None

    async def list_api_keys(self, org_id: str, user_id: Optional[str] = None) -> List[APIKey]:
        keys = [k for k in self._api_keys.values() if k.org_id == org_id]
        if user_id:
            keys = [k for k in keys if k.user_id == user_id]
        return keys

    async def update_api_key(self, api_key: APIKey) -> APIKey:
        async with self._lock:
            previous = self._api_keys.get(api_key.id)
            self._api_keys[api_key.id] = api_key
            if previous is not None and previous.key_prefix != api_key.key_prefix:
                candidates = self._api_keys_by_prefix.get(previous.key_prefix) or []
                if api_key.id in candidates:
                    candidates.remove(api_key.id)
                if not candidates:
                    self._api_keys_by_prefix.pop(previous.key_prefix, None)
                self._api_keys_by_prefix.setdefault(api_key.key_prefix, []).append(api_key.id)
        return api_key

    async def delete_api_key(self, key_id: str) -> bool:
        async with self._lock:
            key = self._api_keys.pop(key_id, None)
            if key:
                candidates = self._api_keys_by_prefix.get(key.key_prefix) or []
                if key_id in candidates:
                    candidates.remove(key_id)
                if not candidates:
                    self._api_keys_by_prefix.pop(key.key_prefix, None)
                return True
        return False

    async def write_audit_log(self, entry: AuditLogEntry) -> None:
        async with self._lock:
            self._audit_logs.append(entry)

    async def read_audit_logs(
        self,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        action: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLogEntry]:
        logs = self._audit_logs
        if user_id:
            logs = [entry for entry in logs if entry.user_id == user_id]
        if org_id:
            logs = [entry for entry in logs if entry.org_id == org_id]
        if action:
            logs = [entry for entry in logs if entry.action == action]
        if start_time:
            logs = [entry for entry in logs if entry.timestamp >= start_time]
        if end_time:
            logs = [entry for entry in logs if entry.timestamp <= end_time]
        logs.sort(key=lambda x: x.timestamp, reverse=True)
        return logs[offset : offset + limit]


# Global store instance
_auth_store: Optional[AuthStore] = None


def init_auth_store(backend: str = "memory", redis_url: str = "") -> AuthStore:
    """Initialize the global auth store."""
    global _auth_store
    if backend == "redis":
        raise NotImplementedError("Redis auth store not yet implemented")
    else:
        _auth_store = InMemoryAuthStore()
    return _auth_store


def get_auth_store() -> Optional[AuthStore]:
    """Get the global auth store."""
    return _auth_store


# JWT Token Management
class TokenManager:
    """JWT token creation and validation."""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_access_token(self, user: User, session: Session, org: Organization) -> str:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)
        payload = {
            "sub": user.id,
            "org_id": org.id,
            "session_id": session.id,
            "role": user.role.value,
            "email": user.email,
            "name": user.full_name,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "type": TokenType.ACCESS.value,
            "jti": secrets.token_urlsafe(16),
        }
        session.access_token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        session.access_token_expires = expires
        return session.access_token

    def create_refresh_token(self, session: Session) -> str:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)
        payload = {
            "sub": session.user_id,
            "session_id": session.id,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "type": TokenType.REFRESH.value,
            "jti": secrets.token_urlsafe(16),
        }
        session.refresh_token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        session.refresh_token_expires = expires
        return session.refresh_token

    def decode_token(self, token: str, expected_type: Optional[TokenType] = None) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if expected_type and payload.get("type") != expected_type.value:
                raise jwt.InvalidTokenError(f"Expected token type {expected_type.value}")
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TokenInvalidError(str(e))

    def create_api_key_token(self, api_key: APIKey) -> str:
        """Create a long-lived token for API key usage."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": api_key.user_id,
            "org_id": api_key.org_id,
            "api_key_id": api_key.id,
            "scopes": api_key.scopes,
            "iat": int(now.timestamp()),
            "type": TokenType.API_KEY.value,
            "jti": secrets.token_urlsafe(16),
        }
        if api_key.expires_at:
            payload["exp"] = int(api_key.expires_at.timestamp())
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)


class TokenExpiredError(Exception):
    pass


class TokenInvalidError(Exception):
    pass


# Pydantic models for API
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: Dict[str, Any]


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False
    mfa_code: Optional[str] = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    org_name: Optional[str] = None
    org_slug: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class APIKeyCreateRequest(BaseModel):
    name: str
    scopes: List[str] = []
    expires_in_days: Optional[int] = None
    rate_limit: Optional[int] = None


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    key: str  # Only returned on creation
    scopes: List[str]
    expires_at: Optional[datetime]
    created_at: datetime


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: UserRole
    org_id: str
    is_active: bool
    mfa_enabled: bool
    created_at: datetime


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    is_active: bool
    quotas: Dict[str, int]
    created_at: datetime


# Authorization decorators and utilities
class AuthorizationError(Exception):
    def __init__(self, message: str, required_permission: Optional[str] = None):
        self.message = message
        self.required_permission = required_permission
        super().__init__(message)


def require_permission(permission: str):
    """Decorator to require a specific permission."""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Will be implemented with FastAPI dependency injection
            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def authorize(
    store: AuthStore,
    user: User,
    permission: str,
    resource_type: str = "",
    resource_id: str = "",
    resource_owner_id: str = "",
    ip: str = "",
    user_agent: str = "",
    request_id: str = "",
) -> bool:
    """
    Central authorization function with audit logging.
    Returns True if authorized, raises AuthorizationError if denied.
    """
    allowed = user.has_permission(permission)

    # Log audit entry
    await store.write_audit_log(
        AuditLogEntry(
            user_id=user.id,
            org_id=user.org_id,
            action=permission.replace(":", "."),
            resource_type=resource_type,
            resource_id=resource_id,
            resource_owner_id=resource_owner_id,
            decision="allow" if allowed else "deny",
            reason=None if allowed else f"Missing permission: {permission}",
            ip_address=ip,
            user_agent=user_agent,
            request_id=request_id,
        )
    )

    if not allowed:
        raise AuthorizationError(
            f"Insufficient permissions. Required: {permission}",
            required_permission=permission,
        )
    return True


async def authorize_resource_owner(
    store: AuthStore,
    user: User,
    resource_owner_id: str,
    permission: str = "incident:update_own",
    **kwargs,
) -> bool:
    """Authorize if user owns the resource or has admin permission."""
    if user.org_id and user.org_id == resource_owner_id:
        return await authorize(store, user, permission, **kwargs)

    # Check if user has admin permission to access any resource
    if user.has_permission("incident:update_any") or user.has_permission("*"):
        return await authorize(store, user, "incident:update_any", **kwargs)

    raise AuthorizationError(
        "Not authorized to access this resource",
        required_permission=permission,
    )
