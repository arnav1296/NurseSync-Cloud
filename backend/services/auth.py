"""Request identity.

Every write in this API used to take a client-supplied `nurse_id`, which meant
any caller could log or hand off as anyone. Identity comes from the Amazon
Cognito access token and nothing else — the client cannot name itself.

The token is verified locally against the user pool's published signing keys
(JWKS): signature, expiry, issuer, token type and app client. No round trip to
Cognito per request; the keys are fetched once and cached.
"""

import asyncio
from functools import lru_cache
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status

from config import AWS_REGION, COGNITO_CLIENT_ID, COGNITO_USER_POOL_ID
from services.db import get_staff_by_sub


def _issuer() -> str:
    return f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{_issuer()}/.well-known/jwks.json", cache_keys=True)


def _verify(token: str) -> dict:
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=_issuer(),
        # access tokens carry client_id instead of aud, checked below
        options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
    )
    if claims.get("token_use") != "access" or claims.get("client_id") != COGNITO_CLIENT_ID:
        raise jwt.InvalidTokenError("not an access token for this app")
    return claims


async def _resolve_sub(token: str) -> str:
    try:
        # the first call fetches the signing keys over the network
        claims = await asyncio.to_thread(_verify, token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
        )
    return claims["sub"]


async def get_current_staff(authorization: str = Header(default="")) -> dict:
    """Resolve the signed-in staff member, or raise 401/403."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = await _resolve_sub(token.strip())
    staff: Optional[dict] = await get_staff_by_sub(sub)

    if not staff:
        # signed in to Cognito but never onboarded into the ward roster
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No staff profile is linked to this account.",
        )
    if not staff.get("active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account is deactivated."
        )

    return staff


async def get_current_nurse(staff: dict = Depends(get_current_staff)) -> dict:
    """Nurse-only routes."""
    if staff["role"] != "nurse":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for nursing staff.",
        )
    return staff


async def get_current_doctor(staff: dict = Depends(get_current_staff)) -> dict:
    if staff["role"] != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for doctors.",
        )
    return staff


async def get_current_admin(staff: dict = Depends(get_current_staff)) -> dict:
    if staff["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for administrators.",
        )
    return staff
