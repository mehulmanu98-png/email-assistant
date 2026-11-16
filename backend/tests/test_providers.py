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
