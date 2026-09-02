from datetime import datetime

from app.extensions import db
from app.models.merchant import Merchant


class ValidationError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class MerchantService:
    @staticmethod
    def ensure_default_merchant():
        try:
            if not db.inspect(db.engine).has_table("merchants"):
                return None
        except Exception:
            return None

        merchant = Merchant.query.filter_by(id="merchant-001").first()
        if merchant:
            return merchant

        merchant = Merchant(
            id="merchant-001",
            name="KiranaKart",
            email="merchant@kiranakart.local",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(merchant)
        db.session.commit()
        return merchant

    @staticmethod
    def list_merchants():
        return Merchant.query.order_by(Merchant.created_at.desc()).all()

    @staticmethod
    def get_merchant(merchant_id):
        return db.session.get(Merchant, merchant_id)

    @staticmethod
    def create_merchant(payload):
        data = payload or {}
        name = (data.get("name") or "KiranaKart").strip() or "KiranaKart"
        email = (data.get("email") or "").strip() or None
        merchant = Merchant(name=name, email=email)
        db.session.add(merchant)
        db.session.commit()
        return merchant
