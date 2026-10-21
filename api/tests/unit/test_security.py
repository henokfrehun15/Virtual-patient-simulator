from app.core.security import hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    password = "correct-horse-battery-staple"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(hashed, password)
    assert not verify_password(hashed, "wrong-password")
