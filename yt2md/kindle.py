import argparse
import logging
import os
import smtplib
import subprocess
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def convert_md_to_epub(md_path):
    """
    Convert a markdown file to epub format using pandoc

    Args:
        md_path (str): Path to the markdown file

    Returns:
        str: Path to the generated epub file or None if conversion failed
    """
    try:
        # Check if pandoc is installed
        subprocess.run(
            ["pandoc", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error(
            "Pandoc is not installed or not found in PATH. Please install pandoc: https://pandoc.org/installing.html"
        )
        return None

    # Get file details
    md_path = Path(md_path)
    if not md_path.exists():
        logger.error(f"File not found: {md_path}")
        return None

    # Define output epub path
    epub_path = md_path.with_suffix(".epub")

    try:
        # Run pandoc to convert md to epub
        logger.info(f"Converting {md_path} to EPUB format...")
        cmd = ["pandoc", str(md_path), "-o", str(epub_path)]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )

        if epub_path.exists():
            logger.info(f"Successfully converted to: {epub_path}")
            return str(epub_path)
        else:
            logger.error("Conversion failed: EPUB file wasn't created")
            return None

    except subprocess.SubprocessError as e:
        logger.error(f"Pandoc conversion failed: {e}")
        logger.error(
            f"Command output: {e.stderr.decode() if hasattr(e, 'stderr') else 'No error output'}"
        )
        return None


def send_email(
    sender_email,
    password,
    recipient_email,
    subject,
    body,
    attachment_path=None,
    smtp_server="smtp.gmail.com",
    smtp_port=587,
):
    """
    Send an email with optional attachment using SMTP

    Args:
        sender_email (str): Email account
        password (str): Email account password or app password
        recipient_email (str): Recipient email address
        subject (str): Email subject
        body (str): Email body content
        attachment_path (str, optional): Path to file to attach
        smtp_server (str): SMTP server address (default: smtp.gmail.com)
        smtp_port (int): SMTP server port (default: 587)

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Create message container
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg["Date"] = formatdate(localtime=True)
        msg["Subject"] = subject

        # Attach message body
        msg.attach(MIMEText(body))

        # Attach file if provided
        if attachment_path and os.path.exists(attachment_path):
            attachment_filename = os.path.basename(attachment_path)
            attachment = MIMEBase("application", "octet-stream")

            with open(attachment_path, "rb") as file:
                attachment.set_payload(file.read())

            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition", f'attachment; filename="{attachment_filename}"'
            )
            msg.attach(attachment)
            logger.info(f"Attached file: {attachment_filename}")

        # Connect to SMTP server
        logger.info(f"Connecting to SMTP server: {smtp_server}:{smtp_port}...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()

        # Login to sender account
        logger.info(f"Logging in as {sender_email}...")
        server.login(sender_email, password)

        # Send email
        logger.info(f"Sending email to {recipient_email}...")
        server.send_message(msg)
        server.quit()

        logger.info("Email sent successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def md_to_kindle(
    md_path,
    sender_email,
    password,
    recipient_email,
    smtp_server="smtp.gmail.com",
    smtp_port=587,
):
    """
    Convert markdown to epub and send via email

    Args:
        md_path (str): Path to markdown file
        sender_email (str): Email account
        password (str): Email account password or app password
        recipient_email (str): Recipient email address
        smtp_server (str): SMTP server address (default: smtp.gmail.com)
        smtp_port (int): SMTP server port (default: 587)

    Returns:
        bool: True if process completed successfully, False otherwise
    """
    # Convert markdown to epub
    epub_path = convert_md_to_epub(md_path)
    if not epub_path:
        return False

    # Prepare email content
    md_filename = os.path.basename(md_path)
    subject = f"Converted Document: {md_filename}"
    body = f"Attached is your converted document: {md_filename}"

    # Send email with epub attachment
    return send_email(
        sender_email=sender_email,
        password=password,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        attachment_path=epub_path,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
    )


def main():
    """Command line interface for the module"""
    parser = argparse.ArgumentParser(
        description="Convert markdown to epub and send to email"
    )
    parser.add_argument("md_path", help="Path to the markdown file")

    # Email credentials - now with environment variable fallbacks
    parser.add_argument(
        "--sender",
        "-s",
        default=os.environ.get("MD_SENDER_EMAIL"),
        help="Email sender address (default: uses MD_SENDER_EMAIL env variable)",
    )
    parser.add_argument(
        "--password",
        "-p",
        default=os.environ.get("MD_SENDER_PASSWORD"),
        help="Email password (default: uses MD_SENDER_PASSWORD env variable)",
    )
    parser.add_argument(
        "--recipient",
        "-r",
        default=os.environ.get("MD_RECIPIENT_EMAIL"),
        help="Recipient email address (default: uses MD_RECIPIENT_EMAIL env variable)",
    )

    # SMTP server settings - for non-Gmail providers
    parser.add_argument(
        "--smtp-server",
        default=os.environ.get("MD_SMTP_SERVER", "smtp.gmail.com"),
        help="SMTP server address (default: smtp.gmail.com or MD_SMTP_SERVER env variable)",
    )
    parser.add_argument(
        "--smtp-port",
        type=int,
        default=int(os.environ.get("MD_SMTP_PORT", "587")),
        help="SMTP server port (default: 587 or MD_SMTP_PORT env variable)",
    )

    # Option to only convert without sending
    parser.add_argument(
        "--convert-only",
        action="store_true",
        help="Only convert to epub without sending email",
    )

    args = parser.parse_args()

    # Check if credentials are provided
    if not args.convert_only:
        missing = []
        if not args.sender:
            missing.append("Sender email (--sender or MD_SENDER_EMAIL)")
        if not args.password:
            missing.append("Password (--password or MD_SENDER_PASSWORD)")
        if not args.recipient:
            missing.append("Recipient email (--recipient or MD_RECIPIENT_EMAIL)")

        if missing:
            for item in missing:
                logger.error(f"Missing required parameter: {item}")
            logger.info(
                "Use --convert-only if you only want to convert without sending"
            )
            return 1

    # Convert markdown to epub
    epub_path = convert_md_to_epub(args.md_path)
    if not epub_path:
        return 1

    if args.convert_only:
        logger.info(f"Conversion completed. EPUB file saved at: {epub_path}")
        return 0

    # Send email with the converted file
    success = send_email(
        sender_email=args.sender,
        password=args.password,
        recipient_email=args.recipient,
        subject=f"Converted Document: {os.path.basename(args.md_path)}",
        body=f"Attached is your converted document: {os.path.basename(args.md_path)}",
        attachment_path=epub_path,
        smtp_server=args.smtp_server,
        smtp_port=args.smtp_port,
    )

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
