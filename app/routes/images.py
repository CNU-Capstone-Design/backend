import uuid
import base64
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from io import BytesIO
from app import db
from app.models.simulation import Image
from app.utils.image import allowed_file, save_encrypted_image, load_decrypted_image, delete_encrypted_file

images_bp = Blueprint("images", __name__)

DETECTED_PARTS = ["skin", "nose", "eye_g", "l_eye", "r_eye", "l_brow", "r_brow", "l_lip", "u_lip"]


@images_bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_image():
    user_id = int(get_jwt_identity())

    if "file" not in request.files:
        return jsonify({"error": "file 필드가 없습니다."}), 400

    file = request.files["file"]
    if not file.filename or not allowed_file(file.filename):
        return jsonify({"error": "JPG 또는 PNG 파일만 업로드할 수 있습니다."}), 400

    # User 테이블의 encryption_password 사용 (업로드 요청에서 별도 입력 불필요)
    from app.models.user import User
    user = User.query.get(user_id)
    if not user or not user._enc_pw_backup:
        return jsonify({"error": "이미지 암호화 비밀번호가 설정되지 않은 계정입니다."}), 400
    encryption_password = user._enc_pw_backup

    file_bytes = file.read()
    if len(file_bytes) == 0:
        return jsonify({"error": "빈 파일입니다."}), 400

    try:
        filename, iv, salt = save_encrypted_image(file_bytes, encryption_password, prefix="orig")
    except Exception:
        return jsonify({"error": "이미지 처리에 실패했습니다."}), 400

    image_id = str(uuid.uuid4())
    img_record = Image(
        id=image_id,
        user_id=user_id,
        filename=filename,
        iv=iv,
        kdf_salt=salt,
        encryption_password=encryption_password,
    )
    db.session.add(img_record)
    db.session.commit()

    return jsonify({
        "image_id": image_id,
        "detected_parts": DETECTED_PARTS,
        "created_at": img_record.created_at.isoformat(),
    }), 200


@images_bp.route("/<image_id>", methods=["GET"])
@jwt_required()
def get_image(image_id):
    user_id = int(get_jwt_identity())
    img = Image.query.filter_by(id=image_id, user_id=user_id).first()
    if not img:
        return jsonify({"error": "이미지를 찾을 수 없습니다."}), 404
    if img.original_deleted:
        return jsonify({"error": "원본 이미지는 삭제되었습니다."}), 410

    # 비밀번호: 헤더 또는 DB에서 읽음
    password = request.headers.get("X-Encryption-Password") or img.encryption_password

    try:
        image_bytes = load_decrypted_image(img.filename, img.iv, img.kdf_salt, password)
    except Exception:
        return jsonify({"error": "복호화 실패. 비밀번호를 확인하세요."}), 403

    return send_file(BytesIO(image_bytes), mimetype="image/jpeg")


@images_bp.route("/<image_id>/base64", methods=["GET"])
@jwt_required()
def get_image_base64(image_id):
    user_id = int(get_jwt_identity())
    img = Image.query.filter_by(id=image_id, user_id=user_id).first()
    if not img:
        return jsonify({"error": "이미지를 찾을 수 없습니다."}), 404
    if img.original_deleted:
        return jsonify({"error": "원본 이미지는 삭제되었습니다."}), 410

    password = request.headers.get("X-Encryption-Password") or img.encryption_password

    try:
        image_bytes = load_decrypted_image(img.filename, img.iv, img.kdf_salt, password)
    except Exception:
        return jsonify({"error": "복호화 실패. 비밀번호를 확인하세요."}), 403

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return jsonify({"image_id": image_id, "data_url": f"data:image/jpeg;base64,{encoded}"}), 200


@images_bp.route("/<image_id>", methods=["DELETE"])
@jwt_required()
def delete_image(image_id):
    user_id = int(get_jwt_identity())
    img = Image.query.filter_by(id=image_id, user_id=user_id).first()
    if not img:
        return jsonify({"error": "이미지를 찾을 수 없습니다."}), 404

    delete_encrypted_file(img.filename)
    img.original_deleted = True
    db.session.commit()

    return jsonify({"message": "원본 이미지가 삭제되었습니다."}), 200
