"""Amazon Cognito: creating and removing staff logins.

boto3 is synchronous, so each call runs in a worker thread to keep the event loop free.
Users are created with a permanent password, so the first sign-in doesn't stop at a
"set a new password" challenge, and are put in the Cognito group matching their role.
"""

import asyncio
from functools import lru_cache

import boto3

from config import AWS_REGION, COGNITO_USER_POOL_ID


@lru_cache(maxsize=1)
def _client():
    return boto3.client("cognito-idp", region_name=AWS_REGION)


def _create_user(email: str, password: str, role: str) -> str:
    client = _client()
    response = client.admin_create_user(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=email,
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
        # the admin hands the password over in person; no invitation email
        MessageAction="SUPPRESS",
    )
    client.admin_set_user_password(
        UserPoolId=COGNITO_USER_POOL_ID, Username=email, Password=password, Permanent=True
    )
    client.admin_add_user_to_group(
        UserPoolId=COGNITO_USER_POOL_ID, Username=email, GroupName=role
    )
    attributes = {a["Name"]: a["Value"] for a in response["User"]["Attributes"]}
    return attributes["sub"]


def _delete_user(email: str) -> None:
    _client().admin_delete_user(UserPoolId=COGNITO_USER_POOL_ID, Username=email)


async def create_auth_user(email: str, password: str, role: str) -> str:
    """Create a Cognito login and return its `sub`."""
    return await asyncio.to_thread(_create_user, email, password, role)


async def delete_auth_user(email: str) -> None:
    await asyncio.to_thread(_delete_user, email)
