"""Image validation and disk I/O helpers."""

import os
import uuid
from io import BytesIO
from PIL import Image as PILImage, ExifTags
from flask import current_app
from app.utils.crypto import encrypt_file, decrypt_file

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def fix_image_orientation(image: PILImage.Image) -> PILImage.Image:
    try:
        exif = image._getexif()
        if exif is None:
            return image

        orientation_key = next(
            (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
        )
        if orientation_key is None or orientation_key not in exif:
            return image

        orientation = exif[orientation_key]
        print(f"[DEBUG] Orientation 값: {orientation}")

        if orientation == 2:
            image = image.transpose(PILImage.FLIP_LEFT_RIGHT)
        elif orientation == 3:
            image = image.rotate(180)
        elif orientation == 4:
            image = image.rotate(180).transpose(PILImage.FLIP_LEFT_RIGHT)
        elif orientation == 5:
            image = image.rotate(-90, expand=True).transpose(PILImage.FLIP_LEFT_RIGHT)
        elif orientation == 6:
            image = image.rotate(-90, expand=True)
        elif orientation == 7:
            image = image.rotate(90, expand=True).transpose(PILImage.FLIP_LEFT_RIGHT)
        elif orientation == 8:
            image = image.rotate(-90, expand=True)

    except Exception:
        pass

    return image


def save_encrypted_image(file_bytes: bytes, password: str, prefix: str = "img") -> tuple[str, bytes, bytes]:
    """EXIF 회전 보정 → EXIF 제거 → 암호화 → 디스크 저장."""

    # 1. 이미지 열기
    image = PILImage.open(BytesIO(file_bytes))

    # 2. EXIF 회전 보정
    image = fix_image_orientation(image)
    print(f"[DEBUG] 보정 후 이미지 크기: {image.size}")

    # 3. EXIF 완전 제거 후 새 이미지로 저장 (브라우저가 EXIF 재참조 못하게)
    output = BytesIO()
    clean_image = PILImage.new(image.mode, image.size)
    clean_image.paste(image)
    clean_image.save(output, format="JPEG")
    corrected_bytes = output.getvalue()

    # 4. 암호화 후 저장
    ciphertext, iv, salt = encrypt_file(corrected_bytes, password)
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