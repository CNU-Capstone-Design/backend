from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app import db
from app.models.user import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip() or None
    password = data.get("password", "")
    encryption_password = (data.get("encryption_password") or "").strip()

    if not username or not password:
        return jsonify({"error": "username과 password는 필수입니다."}), 400

    if not encryption_password:
        return jsonify({"error": "이미지 암호화 비밀번호는 필수입니다."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "이미 사용 중인 아이디입니다."}), 409

    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "이미 사용 중인 이메일입니다."}), 409

    user = User(username=username, email=email)
    user.set_password(password)
    user.set_encryption_password(encryption_password)
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({
        "message": "회원가입 성공",
        "token": token,
        "user": user.to_dict(),
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    # Support both 'username' (frontend) and 'email' (API spec)
    identifier = (data.get("username") or data.get("email") or "").strip()
    password = data.get("password", "")

    if not identifier or not password:
        return jsonify({"error": "아이디/이메일과 비밀번호를 입력해주세요."}), 400

    # Try username first, then email
    user = User.query.filter_by(username=identifier).first()
    if not user:
        user = User.query.filter_by(email=identifier).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "아이디 또는 비밀번호가 올바르지 않습니다."}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({
        "token": token,
        "user": user.to_dict(),
    }), 200


@auth_bp.route("/verify-encryption-password", methods=["POST"])
@jwt_required()
def verify_encryption_password():
    """암호화 비밀번호 검증 — 맞으면 200, 틀리면 401."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404

    data = request.get_json(silent=True) or {}
    provided = (data.get("encryption_password") or "").strip()

    if not provided:
        return jsonify({"error": "encryption_password는 필수입니다."}), 400

    if not user.check_encryption_password(provided):
        return jsonify({"error": "암호화 비밀번호가 올바르지 않습니다."}), 403

    return jsonify({"message": "검증 성공"}), 200
