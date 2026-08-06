import asyncio
import sys

sys.path.insert(0, ".")
from app.config import settings
from app.graph_mailer import send_mail


async def main() -> None:
    to_email = sys.argv[1] if len(sys.argv) > 1 else settings.graph_sender_email

    print(f"tenant={settings.graph_tenant_id} client_id={settings.graph_client_id} "
          f"sender={settings.graph_sender_email} to={to_email}")

    try:
        await send_mail(to_email, "Graph API debug test", "This is a test message from debug_graph_mail.py")
        print("SUCCESS")
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        response = getattr(exc, "response", None)
        if response is not None:
            print("BODY:", response.text)
        raise


if __name__ == "__main__":
    asyncio.run(main())
