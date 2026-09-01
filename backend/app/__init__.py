import os

from flask import Flask
from dotenv import load_dotenv

from .extensions import db, migrate, cors

load_dotenv()


def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

    db.init_app(app)
    migrate.init_app(app, db)
    cors(app)

    from .models import Customer
    from .routes.customers import customers_bp

    app.register_blueprint(customers_bp)

    @app.route("/health")
    def health():
        return {
            "status": "ok",
            "message": "Udhaar AI backend is running"
        }

    return app