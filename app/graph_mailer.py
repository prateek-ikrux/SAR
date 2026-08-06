import time

import httpx

from app.config import settings

_TOKEN_URL = f"https://login.microsoftonline.com/{settings.graph_tenant_id}/oauth2/v2.0/token"
_SEND_MAIL_URL = f"https://graph.microsoft.com/v1.0/users/{settings.graph_sender_email}/sendMail"

_cached_token: str | None = None
_cached_token_expiry: float = 0.0


async def _get_access_token() -> str:
    global _cached_token, _cached_token_expiry

    if _cached_token and time.monotonic() < _cached_token_expiry:
        return _cached_token

    async with httpx.AsyncClient() as client:
        response = await client.post(
            _TOKEN_URL,
            data={
                "client_id": settings.graph_client_id,
                "client_secret": settings.graph_client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()
        payload = response.json()

    _cached_token = payload["access_token"]
    _cached_token_expiry = time.monotonic() + payload["expires_in"] - 60
    return _cached_token


async def send_mail(to_email: str, subject: str, body: str) -> None:
    token = await _get_access_token()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            _SEND_MAIL_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": to_email}}],
                },
                "saveToSentItems": False,
            },
        )
        response.raise_for_status()
