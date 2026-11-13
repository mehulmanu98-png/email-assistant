from app.security import hash_password, verify_password

def test_password_hash_verifies_correct_password():
    encoded = hash_password("a-long-test-password-123")
    assert verify_password("a-long-test-password-123", encoded)
    assert not verify_password("not-the-same-password", encoded)

def test_password_hash_uses_a_unique_salt():
    assert hash_password("a-long-test-password-123") != hash_password("a-long-test-password-123")
