import os
from pathlib import Path
import email
import pytest

from yt2md.email.send_email import EmailSender


class FakeSMTP:
    """Fake SMTP server capturing sendmail arguments for assertions."""
    last_instance: "FakeSMTP | None" = None

    def __init__(self, host, port, timeout=None):  # noqa: D401
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = False
        self.sent = []
        FakeSMTP.last_instance = self

    # Context manager protocol
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: D401
        return False

    # SMTP-like methods
    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = True
        self.user = user
        self.password = password

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent.append((from_addr, to_addrs, msg))


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "noreply@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "dummy-pass")
    yield


@pytest.fixture
def fake_smtp(monkeypatch):
    import smtplib

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    yield FakeSMTP
    FakeSMTP.last_instance = None


def _create_file(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_single_epub_attachment(tmp_path: Path, fake_smtp):
    epub = _create_file(tmp_path, "sample.epub", b"epub-bytes\n")
    sender = EmailSender()
    ok = sender.send(
        subject="Test EPUB",
        body="Here is your EPUB",
        recipients="user@example.com",
        attachments=[epub],
    )
    assert ok is True
    inst = fake_smtp.last_instance
    assert inst is not None
    assert inst.sent, "No message captured"
    raw_msg = inst.sent[0][2]
    msg = email.message_from_string(raw_msg)
    # Find attachment part
    attachments = [part for part in msg.walk() if part.get_filename()]
    assert len(attachments) == 1
    att = attachments[0]
    assert att.get_filename() == "sample.epub"
    # MIME type should be our forced application/epub+zip
    assert att.get_content_type() == "application/epub+zip"


def test_multiple_attachments_and_unknown_type(tmp_path: Path, fake_smtp):
    epub = _create_file(tmp_path, "b.epub", b"data")
    binfile = _create_file(tmp_path, "c.bin", b"binary\x00data")
    sender = EmailSender()
    ok = sender.send(
        subject="Mix",
        body="Two attachments",
        recipients="user@example.com",
        attachments=[epub, binfile],
    )
    assert ok is True
    inst = fake_smtp.last_instance
    raw_msg = inst.sent[0][2]
    msg = email.message_from_string(raw_msg)
    filenames = sorted([fn for fn in (part.get_filename() for part in msg.walk()) if fn is not None])
    assert filenames == ["b.epub", "c.bin"]


def test_missing_attachment_returns_false(tmp_path: Path, fake_smtp):
    missing = tmp_path / "nope.epub"
    sender = EmailSender()
    ok = sender.send(
        subject="Missing",
        body="Should fail",
        recipients="user@example.com",
        attachments=[missing],
    )
    assert ok is False
    # SMTP should never have been created because attachment prep aborted early
    assert fake_smtp.last_instance is None
