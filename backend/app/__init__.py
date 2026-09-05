import os

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import inspect, text

from .extensions import cors, db, migrate

load_dotenv()


def create_app(test_config=None):
    app = Flask(__name__)

    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL") or "sqlite:///udhaar.db",
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
        resources={r"/api/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000", "https://razorpay-project-orpin.vercel.app"]}},
        supports_credentials=False,
    )

    from .models import Customer, LedgerEntry, Merchant, Payment, PaymentLink, CollectionEvent  # noqa: F401
    from .routes.customers import customers_bp
    from .routes.ledger import ledger_bp
    from .routes.merchant import merchant_bp
    from .routes.dashboard import dashboard_bp
    from .routes.payments import payments_bp
    from .routes.payment_links import payment_links_bp
    from .routes.collection_events import collection_events_bp
    from .services.merchant_service import MerchantService

    app.register_blueprint(merchant_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(ledger_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(payment_links_bp)
    app.register_blueprint(collection_events_bp)

    with app.app_context():
        db.create_all()

        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        if "ledger_entries" in tables:
            ledger_columns = {column["name"] for column in inspector.get_columns("ledger_entries")}
            with db.engine.begin() as connection:
                if "transaction_date" not in ledger_columns:
                    connection.execute(text("ALTER TABLE ledger_entries ADD COLUMN transaction_date TIMESTAMP"))
                if "due_date" not in ledger_columns:
                    connection.execute(text("ALTER TABLE ledger_entries ADD COLUMN due_date TIMESTAMP"))

        if "payment_links" in tables:
            payment_link_columns = {column["name"] for column in inspector.get_columns("payment_links")}
            with db.engine.begin() as connection:
                if "ledger_entry_id" not in payment_link_columns:
                    connection.execute(text("ALTER TABLE payment_links ADD COLUMN ledger_entry_id VARCHAR(64)"))
                if db.engine.dialect.name == "postgresql":
                    connection.execute(text("ALTER TABLE payment_links DROP CONSTRAINT IF EXISTS payment_link_status_valid"))
                    connection.execute(text("ALTER TABLE payment_links ADD CONSTRAINT payment_link_status_valid CHECK (status IN ('draft','issued','active','completed','expired','cancelled'))"))

        if "merchants" not in tables:
            db.create_all()

        MerchantService.ensure_default_merchant()

    @app.route("/health")
    def health():
        return jsonify({
            "success": True,
            "status": "ok",
            "message": "Udhaar AI backend is running",
        })

    return app