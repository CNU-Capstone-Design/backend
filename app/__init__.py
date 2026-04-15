import os
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)

    # Config
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///face_sim.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "uploads")
    app.config["MAX_CONTENT_LENGTH"] = int(
        os.getenv("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)  # 50MB
    )

    # Extensions
    db.init_app(app)
    jwt.init_app(app)
    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.images import images_bp
    from app.routes.simulate import simulate_bp
    from app.routes.gallery import gallery_bp

    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(images_bp, url_prefix="/api/v1/images")
    app.register_blueprint(simulate_bp, url_prefix="/api/v1/simulate")
    app.register_blueprint(gallery_bp, url_prefix="/api/v1/gallery")

    # Create tables + 컬럼 추가 마이그레이션 (SQLite)
    with app.app_context():
        db.create_all()
        _migrate_db()

    return app


def _migrate_db():
    """기존 DB에 새 컬럼이 없으면 추가합니다 (SQLite ALTER TABLE)."""
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE simulations ADD COLUMN aligned_image_id VARCHAR(36)",
        "ALTER TABLE simulations ADD COLUMN result_thumbnail TEXT",
    ]
    with db.engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # 이미 존재하면 무시
