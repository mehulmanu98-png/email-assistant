from app.providers import _find_icloud_uid

class FakeIMAP:
    def __init__(self, result=(b"98765",)):
        self.result = result
    def uid(self, *args):
        return "OK", [b" ".join(self.result)]

def test_stored_uid_is_used_for_messages_without_message_id():
    assert _find_icloud_uid(FakeIMAP(), "icloud-uid-12345") == b"12345"

def test_old_unsafe_sequence_ids_are_rejected():
    import pytest
    with pytest.raises(RuntimeError):
        _find_icloud_uid(FakeIMAP(), "icloud-seq-12")

def test_real_message_id_is_resolved_with_imap_search():
    assert _find_icloud_uid(FakeIMAP(), "<mail@example.com>") == b"98765"
