from datetime import datetime, timezone
from app import db


class Image(db.Model):
    """업로드된 원본 이미지. 실제 파일은 사용자 비밀번호 기반 AES-256으로 암호화."""

    __tablename__ = "images"

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename = db.Column(db.String(256), nullable=False)    # 암호화된 파일 경로
    iv = db.Column(db.LargeBinary(16), nullable=False)      # AES IV
    kdf_salt = db.Column(db.LargeBinary(16), nullable=False)  # PBKDF2 salt
    encryption_password = db.Column(db.Text, nullable=False)  # 복구용 비밀번호 (원문)
    original_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    simulations = db.relationship("Simulation", backref="source_image", lazy=True)

    def to_dict(self):
        return {
            "image_id": self.id,
            "created_at": self.created_at.isoformat(),
            "original_deleted": self.original_deleted,
        }


class Simulation(db.Model):
    __tablename__ = "simulations"

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    image_id = db.Column(db.String(36), db.ForeignKey("images.id"), nullable=True)
    # FFHQ-aligned 이미지 ID (segment 마스크용)
    aligned_image_id = db.Column(db.String(36), nullable=True)
    name = db.Column(db.String(200), nullable=False, default="시뮬레이션")
    status = db.Column(db.String(20), default="pending")
    target_parts = db.Column(db.Text, nullable=True)
    style_intensity = db.Column(db.Float, default=0.85)
    result_filename = db.Column(db.String(256), nullable=True)
    result_iv = db.Column(db.LargeBinary(16), nullable=True)
    result_kdf_salt = db.Column(db.LargeBinary(16), nullable=True)
    fid_score = db.Column(db.Float, nullable=True)
    similarity_score = db.Column(db.Float, nullable=True)
    # before: FFHQ-aligned 이미지 썸네일 (갤러리 Before 용)
    thumbnail = db.Column(db.Text, nullable=True)
    # after: AI 생성 결과 이미지 썸네일 (갤러리 After 용)
    result_thumbnail = db.Column(db.Text, nullable=True)
    face_parts_json = db.Column(db.Text, nullable=True)
    modifications_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        import json
        return {
            "simulation_id": self.id,
            "image_id": self.image_id,
            "aligned_image_id": self.aligned_image_id,
            "name": self.name,
            "status": self.status,
            "thumbnail": self.thumbnail,
            "result_thumbnail": self.result_thumbnail,
            "face_parts": json.loads(self.face_parts_json) if self.face_parts_json else [],
            "modifications": json.loads(self.modifications_json) if self.modifications_json else [],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
