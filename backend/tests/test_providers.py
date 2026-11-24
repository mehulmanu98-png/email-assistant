from app.providers import _find_icloud_uid

class FakeIMAP:
    def __init__(self, result=(b"98765",), validity=b"54321"):
        self.result = result
        self.validity = validity
    def uid(self, *args):
        return "OK", [b" ".join(self.result)]
    def response(self, code):
        return "UIDVALIDITY", [self.validity]

def test_stored_uid_is_used_only_when_uidvalidity_matches():
    assert _find_icloud_uid(FakeIMAP(), "icloud-uidv-54321-12345") == b"12345"

def test_stale_uidvalidity_blocks_provider_action():
    import pytest
    with pytest.raises(RuntimeError, match="mailbox identity changed"):
        _find_icloud_uid(FakeIMAP(validity=b"99999"), "icloud-uidv-54321-12345")

def test_unverified_or_old_uids_are_rejected():
    import pytest
    for message_id in ("icloud-uid-12345", "icloud-uid-unverified-12345"):
        with pytest.raises(RuntimeError):
            _find_icloud_uid(FakeIMAP(), message_id)

def test_old_unsafe_sequence_ids_are_rejected():
    import pytest
    with pytest.raises(RuntimeError):
        _find_icloud_uid(FakeIMAP(), "icloud-seq-12")

def test_real_message_id_is_resolved_with_imap_search():
    fake = FakeIMAP((b"98765",))
    assert _find_icloud_uid(fake, "<mail@example.com>") == b"98765"

def test_uidvalidity_helper_reads_numeric_mailbox_identity():
    from app.providers import _read_icloud_uidvalidity
    assert _read_icloud_uidvalidity(FakeIMAP(validity=b"7654321")) == "7654321"

def test_uidvalidity_helper_rejects_non_numeric_response():
    from app.providers import _read_icloud_uidvalidity
    assert _read_icloud_uidvalidity(FakeIMAP(validity=b"not-a-number")) is None


def test_icloud_original_attachment_metadata_and_bytes_are_read_only(monkeypatch):
    from email.message import EmailMessage as MIMEMessage
    from app import providers
    from app.models import EmailAccount

    original = MIMEMessage()
    original["From"] = "sender@example.com"
    original["To"] = "owner@example.com"
    original["Subject"] = "Original with invoice"
    original.set_content("Please find the invoice attached.")
    original.add_attachment(
        b"%PDF-1.7 test content",
        maintype="application",
        subtype="pdf",
        filename="invoice.pdf",
    )
    raw = original.as_bytes()

    class FakeAttachmentIMAP:
        def select(self, mailbox, readonly=True):
            return "OK", [b"1"]
        def uid(self, *args):
            return "OK", [(b"1 (BODY.PEEK[])", raw)]
        def logout(self):
            return "BYE"

    fake = FakeAttachmentIMAP()
    monkeypatch.setattr(providers, "_connect", lambda account: (fake, "unused"))
    monkeypatch.setattr(providers, "_find_icloud_uid", lambda client, message_id: b"1")
    account = EmailAccount(
        id=1, user_id=1, provider="icloud", email="owner@example.com",
        encrypted_secret="unused", connection_status="connected"
    )

    metadata = providers.list_icloud_attachments(account, "icloud-uidv-123-1")
    assert len(metadata) == 1
    assert metadata[0]["filename"] == "invoice.pdf"
    assert metadata[0]["mime_type"] == "application/pdf"
    assert metadata[0]["can_preview"] is True

    downloaded = providers.get_icloud_attachment(account, "icloud-uidv-123-1", 0)
    assert downloaded["data"] == b"%PDF-1.7 test content"
    assert downloaded["filename"] == "invoice.pdf"


def test_icloud_read_state_writes_and_verifies_seen_flag(monkeypatch):
    from app import providers
    from app.models import EmailAccount

    class FakeReadIMAP:
        def __init__(self):
            self.calls = []
        def select(self, mailbox, readonly=True):
            assert mailbox == "INBOX"
            assert readonly is False
            return "OK", [b"1"]
        def uid(self, *args):
            self.calls.append(args)
            if args[0] == "STORE":
                return "OK", [b"stored"]
            if args[0] == "FETCH":
                return "OK", [(b"1 (FLAGS (\\Seen))",)]
            raise AssertionError(args)
        def logout(self):
            return "BYE"

    fake = FakeReadIMAP()
    monkeypatch.setattr(providers, "_connect", lambda account: (fake, "unused"))
    monkeypatch.setattr(providers, "_find_icloud_uid", lambda client, message_id: b"123")
    account = EmailAccount(
        id=1, user_id=1, provider="icloud", email="owner@example.com",
        encrypted_secret="unused", connection_status="connected"
    )

    assert providers.set_icloud_read(account, "<mail@example.com>", True) is True
    assert fake.calls == [
        ("STORE", b"123", "+FLAGS.SILENT", "(\\Seen)"),
        ("FETCH", b"123", "(FLAGS)"),
    ]


def test_icloud_read_state_fails_when_seen_flag_is_not_confirmed(monkeypatch):
    import pytest
    from app import providers
    from app.models import EmailAccount

    class FakeReadIMAP:
        def select(self, mailbox, readonly=True):
            return "OK", [b"1"]
        def uid(self, *args):
            if args[0] == "STORE":
                return "OK", [b"stored"]
            return "OK", [(b"1 (FLAGS ())",)]
        def logout(self):
            return "BYE"

    monkeypatch.setattr(providers, "_connect", lambda account: (FakeReadIMAP(), "unused"))
    monkeypatch.setattr(providers, "_find_icloud_uid", lambda client, message_id: b"123")
    account = EmailAccount(
        id=1, user_id=1, provider="icloud", email="owner@example.com",
        encrypted_secret="unused", connection_status="connected"
    )

    with pytest.raises(RuntimeError, match="different read state"):
        providers.set_icloud_read(account, "<mail@example.com>", True)



def test_icloud_reply_sets_exact_threading_headers(monkeypatch):
    from email import message_from_bytes
    from app import providers
    from app.models import EmailAccount, EmailMessage as StoredMessage

    sent = {}

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): pass
        def starttls(self, context=None): pass
        def login(self, user, password): pass
        def send_message(self, message, from_addr=None, to_addrs=None):
            sent["raw"] = message.as_bytes()
            sent["to_addrs"] = to_addrs
            return {}

    class FakeFernet:
        def decrypt(self, value): return b"app-password"

    monkeypatch.setattr(providers, "_connect", lambda account: (None, "unused"))
    monkeypatch.setattr(providers, "get_fernet", lambda: FakeFernet())
    monkeypatch.setattr(providers.smtplib, "SMTP", FakeSMTP)

    account = EmailAccount(
        id=1, user_id=1, provider="icloud", email="owner@example.com",
        encrypted_secret="encrypted", connection_status="connected"
    )
    source = StoredMessage(
        id=7, user_id=1, account_id=1,
        provider_message_id="<original@example.com>",
        thread_key="<root@example.com> <original@example.com>",
        sender="Tony <tony@example.com>",
        recipients="owner@example.com, colleague@example.com",
        subject="答复: Machine enquiry",
        body_text="Original message",
    )

    provider_id = providers.send_icloud(
        account, ["tony@example.com"], ["colleague@example.com"], [],
        "答复: Machine enquiry", "Thanks", source
    )
    sent_message = message_from_bytes(sent["raw"])
    assert sent_message["Message-ID"] == provider_id
    assert sent_message["In-Reply-To"] == "<original@example.com>"
    assert sent_message["References"] == "<root@example.com> <original@example.com>"
    assert sent["to_addrs"] == ["tony@example.com", "colleague@example.com"]
