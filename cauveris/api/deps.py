"""
FastAPI dependency injection utilities for authentication and context.
"""

from typing import Optional
from fastapi import HTTPException, Request


async def get_current_user(request: Request) -> tuple[str, str, str]:
    """
    Get authenticated user identity from request state.
    Returns: (user_id, org_id, role)
    Raises HTTPException 401 if not authenticated.
    """
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return (
        request.state.auth_user_id,
        request.state.auth_org_id,
        request.state.auth_role,
    )


async def get_optional_user(request: Request) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Get user identity if authenticated, otherwise None."""
    if getattr(request.state, "authenticated", False):
        return (
            request.state.auth_user_id,
            request.state.auth_org_id,
            request.state.auth_role,
        )
    return None, None, None
