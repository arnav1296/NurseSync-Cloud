"""Amazon SNS: push notifications for alerts, handoffs and shift change.

Every message goes to one topic with a `recipient` attribute (the staff email). A staff
member's email subscription carries a filter policy on that attribute, so they only
receive their own messages; an unfiltered subscription (the demo inbox) receives all.

Notifications are best effort: a failure is logged, never shown to the nurse, because
the record itself is already saved.
"""

import asyncio
import json
import logging
from functools import lru_cache
from typing import Optional

import boto3

from config import AWS_REGION, SNS_TOPIC_ARN

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client():
    return boto3.client("sns", region_name=AWS_REGION)


def _publish(subject: str, message: str, recipient: Optional[str]) -> None:
    attributes = {}
    if recipient:
        attributes["recipient"] = {"DataType": "String", "StringValue": recipient}
    _client().publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject[:100],
        Message=message,
        MessageAttributes=attributes,
    )


def enabled() -> bool:
    """Lets callers skip lookups that only exist to address a notification."""
    return bool(SNS_TOPIC_ARN)


async def notify(subject: str, message: str, recipient: Optional[str] = None) -> None:
    if not SNS_TOPIC_ARN:
        return
    try:
        await asyncio.to_thread(_publish, subject, message, recipient)
    except Exception as exc:
        logger.warning("SNS publish failed: %s", exc)


def _subscribe(email: str) -> None:
    _client().subscribe(
        TopicArn=SNS_TOPIC_ARN,
        Protocol="email",
        Endpoint=email,
        Attributes={"FilterPolicy": json.dumps({"recipient": [email]})},
    )


async def subscribe_staff(email: str) -> None:
    """Email subscription for one staff member (they confirm it from their inbox)."""
    if not SNS_TOPIC_ARN:
        return
    try:
        await asyncio.to_thread(_subscribe, email)
    except Exception as exc:
        logger.warning("SNS subscribe failed for %s: %s", email, exc)
