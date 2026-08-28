from __future__ import annotations

import html
import logging
import time

import httpx

from app.config import settings

log = logging.getLogger(__name__)

TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
SCOPE = "https://graph.microsoft.com/.default"


class MailError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


_client: httpx.AsyncClient | None = None
_token: str | None = None
_token_expires_at: float = 0.0


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.graph_timeout_seconds)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _access_token() -> str:
    """App-only token via the client credentials flow, cached until just before expiry."""
    global _token, _token_expires_at

    if _token and time.monotonic() < _token_expires_at:
        return _token

    response = await _http().post(
        TOKEN_URL.format(tenant=settings.graph_tenant_id),
        data={
            "client_id": settings.graph_client_id,
            "client_secret": settings.graph_client_secret,
            "scope": SCOPE,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        detail = response.json() if "json" in response.headers.get("content-type", "") else response.text
        log.error(
            "graph token request failed",
            extra={"status": response.status_code, "detail": str(detail)[:400]},
        )
        raise MailError("Could not authenticate against Microsoft Graph.")

    payload = response.json()
    _token = payload["access_token"]
    # Renew a minute early so an in-flight send never races the expiry.
    _token_expires_at = time.monotonic() + max(int(payload.get("expires_in", 3600)) - 60, 60)
    return _token


async def send_mail(*, to: str, subject: str, html_body: str) -> None:
    if not settings.graph_configured:
        raise MailError("Email delivery is not configured on this server.", status_code=503)

    token = await _access_token()
    response = await _http().post(
        GRAPH_SENDMAIL_URL.format(sender=settings.graph_sender),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": html_body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            # These are transactional codes; keeping them in the shared mailbox's
            # Sent Items would put live credentials in front of anyone with access.
            "saveToSentItems": False,
        },
    )

    if response.status_code not in (200, 202):
        detail = response.text[:400]
        log.error(
            "graph sendMail failed",
            extra={"status": response.status_code, "detail": detail, "sender": settings.graph_sender},
        )
        if response.status_code in (401, 403):
            raise MailError(
                "Microsoft Graph rejected the send. Check that the app registration has the "
                "Mail.Send application permission with admin consent, and that any Application "
                "Access Policy includes the sender mailbox."
            )
        raise MailError("Could not send the email.")

    log.info("otp email sent", extra={"to": to, "sender": settings.graph_sender})


def render_code_email(*, code: str, ttl_minutes: int) -> str:
    """Return the HTML body for a sign-in code. Graph sendMail takes a single
    contentType, so there is no plain-text alternative to build."""
    safe_code = html.escape(code)
    spaced = " ".join(safe_code)

    html_body = f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#f4f5f7;
               font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
           style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:12px;
                  border:1px solid #e4e6ea;">
      <tr>
        <td style="padding:32px;">
          <p style="margin:0 0 4px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;
                    color:#6b7280;">ikrux Candidate Search</p>
          <h1 style="margin:0 0 20px;font-size:20px;font-weight:600;color:#111827;">
            Your sign-in code
          </h1>
          <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#374151;">
            Enter this code to finish signing in.
          </p>
          <div style="margin:0 0 20px;padding:18px;background:#f9fafb;border:1px solid #e4e6ea;
                      border-radius:10px;text-align:center;font-size:30px;font-weight:600;
                      letter-spacing:.35em;color:#111827;font-family:ui-monospace,SFMono-Regular,
                      Menlo,Consolas,monospace;">{spaced}</div>
          <p style="margin:0 0 8px;font-size:14px;line-height:1.6;color:#6b7280;">
            It expires in {ttl_minutes} minutes and can only be used once.
          </p>
          <p style="margin:0;font-size:14px;line-height:1.6;color:#6b7280;">
            If you did not try to sign in, you can ignore this email.
          </p>
        </td>
      </tr>
    </table>
  </body>
</html>"""

    return html_body


async def healthy() -> bool:
    if not settings.graph_configured:
        return False
    try:
        await _access_token()
        return True
    except Exception:  # noqa: BLE001
        return False
