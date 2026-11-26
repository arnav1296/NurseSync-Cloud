"""Settings, read from the environment.

On AWS the EC2 instance fetches these from SSM Parameter Store (/nursesync/*) at boot
and passes them to the container, so no secret is ever baked into the image. Locally
they come from backend/.env (see .env.example).
"""

import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from sarvamai import AsyncSarvamAI

load_dotenv()

# PostgreSQL on Amazon RDS (or any Postgres locally)
DATABASE_URL = os.getenv("DATABASE_URL")

# Amazon Cognito user pool that issues the access tokens the API accepts
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")

# Amazon S3 bucket for attachments and shift reports; Amazon SNS topic for alerts.
# Both optional: without them uploads answer 503 and notifications are skipped.
S3_BUCKET = os.getenv("S3_BUCKET")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")

# Shared secret the shift-change Lambda (and the one-off seed call) must present
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN")

# Voice and AI are conveniences, not dependencies: a missing key disables those
# features (the routes answer 503 or fall back) but the app still starts, and a
# nurse can always type.
AI_TIMEOUT_SECONDS = 30.0

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")

# Groq is OpenAI-compatible, so we reuse the openai client
groq_client = (
    AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY,
        timeout=AI_TIMEOUT_SECONDS,
        max_retries=1,
    )
    if GROQ_API_KEY
    else None
)
sarvam_client = (
    AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY, timeout=AI_TIMEOUT_SECONDS)
    if SARVAM_API_KEY
    else None
)

# transcription confidence below this asks the nurse to check more carefully
REVIEW_CONFIDENCE_THRESHOLD = 0.75

# In production CloudFront serves the site and the API from one origin, so CORS only
# matters for local development and the Tauri shell.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:1420,http://localhost:5173,tauri://localhost",
    ).split(",")
    if origin.strip()
]
ALLOWED_ORIGIN_REGEX = os.getenv("ALLOWED_ORIGIN_REGEX", r"https://[a-z0-9]+\.cloudfront\.net")
