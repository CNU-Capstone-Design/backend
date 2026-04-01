"""Image validation and disk I/O helpers."""

import os
import uuid
from io import BytesIO
from PIL import Image as PILImage
from flask import current_app
from app.utils.crypto import encrypt_file, decrypt_file

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_encrypted_image(file_bytes: bytes, password: str, prefix: str = "img") -> tuple[str, bytes, bytes]:
    """암호화 후 디스크 저장.

    Returns:
        (filename_on_disk, iv, salt)
    """
    PILImage.open(BytesIO(file_bytes)).verify()

    ciphertext, iv, salt = encrypt_file(file_bytes, password)
    filename = f"{prefix}_{uuid.uuid4().hex}.enc"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    with open(path, "wb") as f:
        f.write(ciphertext)
    return filename, iv, salt


def load_decrypted_image(filename: str, iv: bytes, salt: bytes, password: str) -> bytes:
    """디스크에서 읽어 복호화."""
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    with open(path, "rb") as f:
        ciphertext = f.read()
    return decrypt_file(ciphertext, iv, salt, password)


def delete_encrypted_file(filename: str) -> None:
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(path):
        os.remove(path)
