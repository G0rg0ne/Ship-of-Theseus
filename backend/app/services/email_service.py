"""
Email sending service for verification and transactional emails.
Uses fastapi-mail with SMTP (e.g. MailHog in dev, SendGrid/SMTP in prod).
"""
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.core.config import settings
from app.core.logger import logger


def _get_mail_config() -> ConnectionConfig:
    """Build ConnectionConfig from application settings."""
    use_credentials = bool(settings.SMTP_USER and settings.SMTP_PASSWORD)
    # MailHog and other dev SMTP on port 1025 use plain TCP; no TLS, no cert validation
    is_plain_smtp = settings.SMTP_PORT == 1025
    return ConnectionConfig(
        # ConnectionConfig requires strings; use empty string when no credentials (e.g. MailHog)
        MAIL_USERNAME=settings.SMTP_USER or "",
        MAIL_PASSWORD=settings.SMTP_PASSWORD or "",
        MAIL_FROM=settings.SMTP_FROM,
        MAIL_PORT=settings.SMTP_PORT,
        MAIL_SERVER=settings.SMTP_HOST,
        MAIL_FROM_NAME="Ship of Theseus",
        MAIL_STARTTLS=not is_plain_smtp and settings.SMTP_PORT == 587,
        MAIL_SSL_TLS=not is_plain_smtp and settings.SMTP_PORT == 465,
        USE_CREDENTIALS=use_credentials,
        VALIDATE_CERTS=not is_plain_smtp and not settings.DEBUG,
    )


async def send_verification_email(to_email: str, verification_token: str) -> None:
    """
    Send the email verification link to the user.
    Link format: {FRONTEND_URL}/verify-email?token={token}
    """
    verification_url = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={verification_token}"
    html = f"""
    <p>Thanks for signing up. Please verify your email by clicking the link below.</p>
    <p><a href="{verification_url}">Verify my email</a></p>
    <p>If you didn't create an account, you can ignore this email.</p>
    <p>This link expires in 24 hours.</p>
    """
    message = MessageSchema(
        subject="Verify your email - Ship of Theseus",
        recipients=[to_email],
        body=html,
        subtype=MessageType.html,
    )
    conf = _get_mail_config()
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        logger.info("Verification email sent", email=to_email)
    except Exception as e:
        logger.exception("Failed to send verification email", email=to_email, error=str(e))
        raise
