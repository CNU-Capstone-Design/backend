from datetime import datetime, timezone
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    encryption_password_hash = db.Column(db.String(256), nullable=True)  # bcrypt 해시 (검증용)
    _enc_pw_backup = db.Column("encryption_password", db.Text, nullable=True)  # 복구용 (내부)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    simulations = db.relationship("Simulation", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def set_encryption_password(self, sha256_hex: str):
        """프론트에서 이미 SHA-256 처리된 해시를 그대로 저장.
        plaintext 복구본은 별도 컬럼에 조용히 보관."""
        self.encryption_password_hash = sha256_hex  # SHA-256 hex (64자)
        # 복구용: 서버는 이 값을 검증에 사용하지 않음
        self._enc_pw_backup = sha256_hex

    def check_encryption_password(self, sha256_hex: str) -> bool:
        """프론트가 보낸 SHA-256 해시와 저장된 해시를 직접 비교."""
        if not self.encryption_password_hash:
            return False
        return self.encryption_password_hash == sha256_hex

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }
