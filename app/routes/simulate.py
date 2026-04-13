"""
AI 시뮬레이션 라우트.
run_inference() 가 로컬 인퍼런스 서버(HierInvRegionModel)를 HTTP 로 호출합니다.

인퍼런스 서버 URL: 환경변수 INFERENCE_SERVER_URL (예: https://xxxx.ngrok.io)
인증 키:          환경변수 INFERENCE_API_KEY
"""

import os
import uuid
import json
import base64
import requests
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.simulation import Simulation, Image
from app.utils.image import save_encrypted_image, load_decrypted_image

simulate_bp = Blueprint("simulate", __name__)

# ── 인퍼런스 서버 설정 ────────────────────────────────────
_INFER_URL = os.getenv("INFERENCE_SERVER_URL", "").rstrip("/")
_INFER_KEY = os.getenv("INFERENCE_API_KEY", "")
_INFER_TIMEOUT = int(os.getenv("INFERENCE_TIMEOUT_SEC", 120))


def run_inference(image_id: str, target_parts: list, style_intensity: float) -> dict:
    """
    로컬 인퍼런스 서버(HierInvRegionModel)를 호출해 얼굴 시뮬레이션을 실행합니다.

    흐름:
      1. DB 에서 Image 레코드 조회 → 복호화
      2. base64 로 인코딩해 인퍼런스 서버 POST /infer 호출
      3. 결과 이미지를 AES-256 으로 재암호화 후 저장
      4. filename / iv / kdf_salt / 점수 반환

    Returns:
        result_filename, result_iv, result_kdf_salt, fid_score, similarity_score
    """
    if not _INFER_URL:
        raise RuntimeError(
            "INFERENCE_SERVER_URL 이 설정되지 않았습니다. "
            "백엔드 .env 에 로컬 인퍼런스 서버 URL(ngrok 등)을 입력하세요."
        )

    # 1. 원본 이미지 복호화
    img_record: Image = Image.query.filter_by(id=image_id).first()
    if not img_record:
        raise ValueError(f"image_id={image_id} 를 찾을 수 없습니다.")

    raw_bytes = load_decrypted_image(
        img_record.filename,
        img_record.iv,
        img_record.kdf_salt,
        img_record.encryption_password,
    )

    # 2. 인퍼런스 서버 호출
    payload = {
        "image":           base64.b64encode(raw_bytes).decode(),
        "target_parts":    target_parts,
        "style_intensity": style_intensity,
    }
    headers = {"Content-Type": "application/json"}
    if _INFER_KEY:
        headers["X-API-Key"] = _INFER_KEY

    resp = requests.post(
        f"{_INFER_URL}/infer",
        json=payload,
        headers=headers,
        timeout=_INFER_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"인퍼런스 서버 오류: {data['error']}")

    result_b64 = data.get("result")
    if not result_b64:
        raise RuntimeError("인퍼런스 서버에서 결과 이미지를 받지 못했습니다.")

    # 3. 결과 이미지 AES-256 암호화 후 저장
    result_bytes = base64.b64decode(result_b64)
    result_filename, result_iv, result_salt = save_encrypted_image(
        result_bytes,
        img_record.encryption_password,
        prefix="result",
    )

    return {
        "result_filename":  result_filename,
        "result_iv":        result_iv,
        "result_kdf_salt":  result_salt,
        "fid_score":        data.get("fid_score"),
        "similarity_score": data.get("similarity_score"),
    }


@simulate_bp.route("/infer", methods=["POST"])
@jwt_required()
def infer():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    image_id = data.get("image_id")
    target_parts = data.get("target_parts", [])
    style_intensity = float(data.get("style_intensity", 0.85))
    name = data.get("name", "시뮬레이션")

    if not image_id:
        return jsonify({"error": "image_id는 필수입니다."}), 400

    img = Image.query.filter_by(id=image_id, user_id=user_id).first()
    if not img:
        return jsonify({"error": "이미지를 찾을 수 없습니다."}), 404

    task_id = str(uuid.uuid4())
    simulation = Simulation(
        id=task_id,
        user_id=user_id,
        image_id=image_id,
        name=name,
        status="processing",
        target_parts=json.dumps(target_parts),
        style_intensity=style_intensity,
    )
    db.session.add(simulation)
    db.session.commit()

    # Run inference
    try:
        result = run_inference(image_id, target_parts, style_intensity)
        simulation.result_filename  = result["result_filename"]
        simulation.result_iv        = result["result_iv"]
        simulation.result_kdf_salt  = result["result_kdf_salt"]
        simulation.fid_score        = result["fid_score"]
        simulation.similarity_score = result["similarity_score"]
        simulation.status = "completed"
    except Exception as e:
        simulation.status = "failed"
        db.session.commit()
        return jsonify({"error": f"추론 실패: {str(e)}"}), 500

    db.session.commit()

    return jsonify({
        "task_id": task_id,
        "status": simulation.status,
        "estimated_time": "5s",
    }), 202


@simulate_bp.route("/result/<task_id>", methods=["GET"])
@jwt_required()
def get_result(task_id):
    user_id = int(get_jwt_identity())
    sim = Simulation.query.filter_by(id=task_id, user_id=user_id).first()
    if not sim:
        return jsonify({"error": "시뮬레이션을 찾을 수 없습니다."}), 404

    response = {
        "task_id": task_id,
        "status": sim.status,
        "created_at": sim.created_at.isoformat(),
    }

    if sim.status == "completed":
        response["metadata"] = {
            "fid_score": sim.fid_score,
            "similarity_score": sim.similarity_score,
        }
        # result_url: if result file exists expose via /api/v1/images endpoint
        if sim.result_filename:
            response["result_url"] = f"/api/v1/simulate/result/{task_id}/image"

    return jsonify(response), 200


@simulate_bp.route("/result/<task_id>/image", methods=["GET"])
@jwt_required()
def get_result_image(task_id):
    """Return decrypted result image bytes."""
    import base64
    from flask import send_file
    from io import BytesIO
    from app.utils.image import load_decrypted_image

    user_id = int(get_jwt_identity())
    sim = Simulation.query.filter_by(id=task_id, user_id=user_id).first()
    if not sim or sim.status != "completed" or not sim.result_filename:
        return jsonify({"error": "결과 이미지가 없습니다."}), 404

    # 결과 이미지를 복호화하려면 원본 Image 레코드의 암호화 비밀번호가 필요합니다.
    src_img = Image.query.filter_by(id=sim.image_id).first()
    if not src_img:
        return jsonify({"error": "원본 이미지 레코드를 찾을 수 없습니다."}), 404

    try:
        image_bytes = load_decrypted_image(
            sim.result_filename,
            sim.result_iv,
            sim.result_kdf_salt,
            src_img.encryption_password,
        )
    except Exception:
        return jsonify({"error": "결과 이미지 복호화에 실패했습니다."}), 500

    return send_file(BytesIO(image_bytes), mimetype="image/jpeg")
