import os

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from .extensions import cors, db, migrate

load_dotenv()


def create_app(test_config=None):
    app = Flask(__name__)

    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-key"),
        JSON_SORT_KEYS=False,
        DEFAULT_MERCHANT_ID="merchant-001",
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(
        app,
        resources={r"/api/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000"]}},
        supports_credentials=False,
    )

    from .models import Customer, LedgerEntry
    from .routes.customers import customers_bp
    from .routes.ledger import ledger_bp

    app.register_blueprint(customers_bp)
    app.register_blueprint(ledger_bp)

    @app.route("/health")
    def health():
        return jsonify({
            "success": True,
            "status": "ok",
            "message": "Udhaar AI backend is running"
        })

    return app