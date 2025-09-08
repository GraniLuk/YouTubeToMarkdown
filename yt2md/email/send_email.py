"""Production-ready email sending utilities for yt2md.

Features:
    * Secrets only via environment (.env already in .gitignore)
    * Retry & backoff
    * Plain text / HTML bodies
    * Optional file attachments (including EPUB: *application/epub+zip*)
    * Minimal functional helper

Environment variables (either UPPERCASE or lowercase accepted):
    EMAIL_ADDRESS / email_address       -> sender (required)
    EMAIL_PASSWORD / email_password     -> app password (required)
    EMAIL_SMTP_SERVER                   -> default smtp.gmail.com
    EMAIL_SMTP_PORT                     -> default 587
"""

from __future__ import annotations

import os
import smtplib
import time
import mimetypes
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Sequence, Union

from dotenv import load_dotenv

from yt2md.logger import get_logger

logger = get_logger("email")


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------
def _first_env(*names: str) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None


def _required_env(*names: str) -> str:
    val = _first_env(*names)
    if not val:
        raise RuntimeError(f"Missing required environment variable (any of): {', '.join(names)}")
    return val


# ---------------------------------------------------------------------------
# EmailSender
# ---------------------------------------------------------------------------
class EmailSender:
    """SMTP email sender with retry logic."""

    def __init__(
        self,
        *,
        smtp_server: str | None = None,
        port: int | None = None,
        sender_address: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        max_retries: int = 2,
        retry_delay: float = 2.0,
    ) -> None:
        # Load .env (idempotent)
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
        self.smtp_server: str = smtp_server or _first_env("EMAIL_SMTP_SERVER") or "smtp.gmail.com"
        self.port: int = port or int(_first_env("EMAIL_SMTP_PORT") or 587)
        self.sender_address: str = sender_address or _required_env("EMAIL_ADDRESS", "email_address")
        self.password: str = password or _required_env("EMAIL_PASSWORD", "email_password")
        self.use_tls = use_tls
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _normalize_recipients(self, recipients: Union[str, Sequence[str] | None]) -> List[str]:
        if recipients is None:
            raise ValueError("No recipients provided.")
        if isinstance(recipients, str):
            return [r.strip() for r in recipients.split(",") if r.strip()]
        return [r.strip() for r in recipients if r and r.strip()]

    def _attach_files(self, msg: MIMEMultipart, attachments: Sequence[os.PathLike | str]):
        """Attach files to the email message.

        Each path must exist; if any attachment fails to read, we raise to abort the send
        rather than sending a partial email silently.
        """
        for raw_path in attachments:
            path = Path(raw_path)
            if not path.is_file():
                raise FileNotFoundError(f"Attachment not found: {path}")

            ctype, encoding = mimetypes.guess_type(path.name)
            if ctype is None or encoding is not None:
                # Fallback for unknown types or encoded types
                if path.suffix.lower() == ".epub":
                    ctype = "application/epub+zip"
                else:
                    ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)

            with path.open("rb") as f:
                payload = MIMEBase(maintype, subtype)
                payload.set_payload(f.read())
            encoders.encode_base64(payload)
            payload.add_header(
                "Content-Disposition",
                "attachment",
                filename=path.name,
            )
            msg.attach(payload)
            logger.debug(f"Attached file {path} ({ctype}, {path.stat().st_size} bytes)")

    def send(
        self,
        subject: str,
        body: str,
        recipients: Union[str, Sequence[str] | None],
        *,
        cc: Union[str, Sequence[str] | None] = None,
        bcc: Union[str, Sequence[str] | None] = None,
        is_html: bool = False,
        attachments: Sequence[os.PathLike | str] | None = None,
    ) -> bool:
        to_list = self._normalize_recipients(recipients)
        cc_list = self._normalize_recipients(cc) if cc else []
        bcc_list = self._normalize_recipients(bcc) if bcc else []
        all_recipients: List[str] = list(dict.fromkeys(to_list + cc_list + bcc_list))
        if not all_recipients:
            raise ValueError("No valid recipients specified.")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_address
        msg["To"] = ", ".join(to_list)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg.attach(MIMEText(body, "html" if is_html else "plain", _charset="utf-8"))

        # Handle attachments (if any) before sending
        if attachments:
            try:
                self._attach_files(msg, attachments)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Failed preparing attachments: {e}")
                return False

        attempt = 0
        while True:
            try:
                with smtplib.SMTP(self.smtp_server, self.port, timeout=30) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.sender_address, self.password)
                    server.sendmail(self.sender_address, all_recipients, msg.as_string())
                logger.info(f"Email sent to {all_recipients} (attempt {attempt + 1})")
                return True
            except smtplib.SMTPAuthenticationError as e:
                logger.error("SMTP authentication failed; verify EMAIL_PASSWORD app password.")
                logger.debug(f"Auth error: {e}")
                return False
            except smtplib.SMTPException as e:
                attempt += 1
                logger.warning(f"SMTP error attempt {attempt}: {e.__class__.__name__}: {e}")
                if attempt > self.max_retries:
                    logger.error("Max retries exceeded; abandoning email send.")
                    return False
                time.sleep(self.retry_delay * attempt)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Unexpected email send error: {e.__class__.__name__}: {e}")
                return False


def send_email(
    subject: str,
    body: str,
    recipients: Union[str, Sequence[str] | None],
    **kwargs,
) -> bool:
    """Functional helper creating a transient EmailSender.

    Supports all keyword arguments of :meth:`EmailSender.send`, including
    `attachments=[...]`.
    """
    return EmailSender().send(subject=subject, body=body, recipients=recipients, **kwargs)


__all__ = ["EmailSender", "send_email"]


if __name__ == "__main__":  # Manual smoke test
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    recipient = _first_env("email_address")
    if not recipient:
        logger.error("Set email_address to run test.")
    else:
        ok = send_email(
            subject="YT2MD Test Email",
            body="This is a test email from YT2MD system.",
            recipients=recipient,
        )
        print("Success" if ok else "Failed")
