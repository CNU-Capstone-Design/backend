import json
import uuid
import base64
from io import BytesIO
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from PIL import Image as PILImage
from app import db
from app.models.simulation import Simulation


def compress_thumbnail(data_url: str, max_size: int = 1200) -> str:
    """base64 data URL을 1200px 이하로 리사이즈하여 JPEG로 재인코딩."""
    try:
        header, b64 = data_url.split(",", 1)
        img = PILImage.open(BytesIO(base64.b64decode(b64)))
        img.thumbnail((max_size, max_size), PILImage.LANCZOS)
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        compressed = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{compressed}"
    except Exception:
        return data_url  # 실패하면 원본 그대로

gallery_bp = Blueprint("gallery", __name__)


@gallery_bp.route("", methods=["GET"])
@jwt_required()
def list_gallery():
    from app.models.user import User
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    # X-Encryption-Password 헤더 검증 (bcrypt 해시 비교)
    enc_pw = request.headers.get("X-Encryption-Password", "")
    unlocked = bool(enc_pw and user and user.check_encryption_password(enc_pw))

    sims = (
        Simulation.query.filter_by(user_id=user_id)
        .order_by(Simulation.created_at.desc())
        .all()
    )

    result = []
    for s in sims:
        d = s.to_dict()
        if not unlocked:
            d["thumbnail"] = None  # 비밀번호 없으면 썸네일 숨김
        result.append(d)

    return jsonify(result), 200


@gallery_bp.route("", methods=["POST"])
@jwt_required()
def save_simulation():
    """워크스페이스에서 시뮬레이션을 저장합니다 (create or update)."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    simulation_id   = data.get("simulation_id") or str(uuid.uuid4())
    name            = (data.get("name") or "시뮬레이션").strip()
    image_id        = data.get("image_id")
    aligned_image_id = data.get("aligned_image_id")
    face_parts      = data.get("face_parts", [])
    modifications   = data.get("modifications", [])

    # before: FFHQ-aligned 이미지 / after: AI 생성 결과 이미지
    raw_thumbnail        = data.get("thumbnail")          # before (aligned)
    raw_result_thumbnail = data.get("result_thumbnail")   # after  (result)
    thumbnail        = compress_thumbnail(raw_thumbnail)        if raw_thumbnail        else None
    result_thumbnail = compress_thumbnail(raw_result_thumbnail) if raw_result_thumbnail else None

    # Upsert: update if exists, create if not
    sim = Simulation.query.filter_by(id=simulation_id, user_id=user_id).first()
    if sim:
        sim.name             = name
        sim.thumbnail        = thumbnail
        sim.result_thumbnail = result_thumbnail
        sim.face_parts_json  = json.dumps(face_parts)
        sim.modifications_json = json.dumps(modifications)
        if image_id:
            sim.image_id = image_id
        if aligned_image_id:
            sim.aligned_image_id = aligned_image_id
    else:
        sim = Simulation(
            id=simulation_id,
            user_id=user_id,
            image_id=image_id,
            aligned_image_id=aligned_image_id,
            name=name,
            status="completed",
            thumbnail=thumbnail,
            result_thumbnail=result_thumbnail,
            face_parts_json=json.dumps(face_parts),
            modifications_json=json.dumps(modifications),
        )
        db.session.add(sim)

    db.session.commit()
    return jsonify(sim.to_dict()), 201


@gallery_bp.route("/<simulation_id>", methods=["GET"])
@jwt_required()
def get_simulation(simulation_id):
    from app.models.user import User
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    enc_pw = request.headers.get("X-Encryption-Password", "")
    unlocked = bool(enc_pw and user and user.check_encryption_password(enc_pw))

    sim = Simulation.query.filter_by(id=simulation_id, user_id=user_id).first()
    if not sim:
        return jsonify({"error": "시뮬레이션을 찾을 수 없습니다."}), 404

    d = sim.to_dict()
    if not unlocked:
        d["thumbnail"] = None
    return jsonify(d), 200


@gallery_bp.route("/<simulation_id>", methods=["DELETE"])
@jwt_required()
def delete_simulation(simulation_id):
    user_id = int(get_jwt_identity())
    sim = Simulation.query.filter_by(id=simulation_id, user_id=user_id).first()
    if not sim:
        return jsonify({"error": "시뮬레이션을 찾을 수 없습니다."}), 404

    if sim.result_filename:
        from app.utils.image import delete_encrypted_file
        delete_encrypted_file(sim.result_filename)

    db.session.delete(sim)
    db.session.commit()
    return jsonify({"message": "시뮬레이션이 삭제되었습니다."}), 200


@gallery_bp.route("/<simulation_id>", methods=["PATCH"])
@jwt_required()
def rename_simulation(simulation_id):
    user_id = int(get_jwt_identity())
    sim = Simulation.query.filter_by(id=simulation_id, user_id=user_id).first()
    if not sim:
        return jsonify({"error": "시뮬레이션을 찾을 수 없습니다."}), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name 필드가 필요합니다."}), 400

    sim.name = name
    db.session.commit()
    return jsonify(sim.to_dict()), 200
