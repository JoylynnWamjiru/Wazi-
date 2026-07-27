"""Authentication dependency for admin API routes.

All /api/* endpoints require a Bearer token matching ADMIN_PASSWORD.
Used as a FastAPI dependency: ``Depends(verify_admin)``.

Usage in a route:
    @router.get("/api/sources")
    async def list_sources(token: str = Depends(verify_admin)):
        ...
"""

import os

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

security = HTTPBearer()


def verify_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Verify the Bearer token matches ADMIN_PASSWORD.

    Returns the token string on success, raises 401 on failure.
    """
    if credentials.credentials != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
        )
    return credentials.credentials
