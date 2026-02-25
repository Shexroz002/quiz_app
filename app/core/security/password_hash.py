from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    """Hash a password for storing."""
    return password_hash.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a hashed value."""
    return password_hash.verify(password, hashed)