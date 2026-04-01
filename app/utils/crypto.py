"""AES-256-CBC encryption/decryption for image files.

키 유도 방식:
  - 사용자가 지정한 암호화 비밀번호 + 랜덤 salt → PBKDF2(SHA-256, 200,000회) → 32-byte AES 키
  - salt와 IV는 DB(Image 테이블)에, 암호문은 디스크(.enc)에 저장
  - 비밀번호 자체도 DB에 저장 (어드민 복구용)

복호화에 필요한 것: 비밀번호 + salt + IV + 암호문
"""

import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256


def derive_key(password: str, salt: bytes) -> bytes:
    """PBKDF2-SHA256으로 비밀번호 → 32-byte AES 키 유도."""
    return PBKDF2(
        password.encode("utf-8"),
        salt,
        dkLen=32,
        count=200_000,
        hmac_hash_module=SHA256,
    )


def encrypt_file(plaintext: bytes, password: str) -> tuple[bytes, bytes, bytes]:
    """AES-256-CBC로 암호화.

    Returns:
        (ciphertext, iv, salt)
    """
    salt = os.urandom(16)
    key = derive_key(password, salt)
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))
    return ciphertext, iv, salt


def decrypt_file(ciphertext: bytes, iv: bytes, salt: bytes, password: str) -> bytes:
    """AES-256-CBC 복호화."""
    key = derive_key(password, salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ciphertext), AES.block_size)
