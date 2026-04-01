"""
AI 시뮬레이션 라우트.
현재는 AI 모델(BiSeNet/SEAN) 없이 stub 응답을 반환합니다.
모델 연동 시 run_inference() 함수만 교체하면 됩니다.
"""

import uuid
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.simulation import Simulation, Image

simulate_bp = Blueprint("simulate", __name__)


def run_inference(image_id: str, target_parts: list, style_intensity: float) -> dict:
    """
    AI 추론 stub.
    실제 BiSeNet + SEAN 모델 연동 시 이 함수를 교체합니다.
    Returns dict with keys: result_filename, result_iv, fid_score, similarity_score
    """
    # TODO: BiSeNet 파싱 → SEAN 추론 → 결과 이미지 AES 암호화 저장
    return {
        "result_filename": None,
        "result_iv": None,
        "fid_score": None,
        "similarity_score": None,
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

    # Run inference (stub for now)
    try:
        result = run_inference(image_id, target_parts, style_intensity)
        simulation.result_filename = result["result_filename"]
        simulation.result_iv = result["result_iv"]
        simulation.fid_score = result["fid_score"]
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

    try:
        image_bytes = load_decrypted_image(sim.result_filename, sim.result_iv)
    except Exception:
        return jsonify({"error": "결과 이미지 복호화에 실패했습니다."}), 500

    return send_file(BytesIO(image_bytes), mimetype="image/jpeg")
