from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.models.ledger import LedgerEntry


class ValidationError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class LedgerService:
    @staticmethod
    def validate_entry_payload(payload):
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object", {"body": "expected object"})

        entry_type = (payload.get("type") or "").strip().lower()
        amount = payload.get("amount")
        description = (payload.get("description") or "").strip() or "Ledger entry"

        if entry_type not in {"credit", "payment", "adjustment"}:
            raise ValidationError("Entry type must be credit, payment, or adjustment", {"type": "invalid"})
        if amount is None or not isinstance(amount, (int, float, str)):
            raise ValidationError("Amount is required", {"amount": "required"})

        try:
            numeric_amount = Decimal(str(amount))
        except Exception:
            raise ValidationError("Amount must be numeric", {"amount": "invalid"})

        if numeric_amount <= 0:
            raise ValidationError("Amount must be greater than zero", {"amount": "min_value"})

        return {
            "type": entry_type,
            "amount": numeric_amount,
            "description": description,
        }

    @staticmethod
    def list_for_customer(customer_id):
        return (
            LedgerEntry.query.filter_by(customer_id=customer_id)
            .order_by(LedgerEntry.created_at.desc())
            .all()
        )

    @staticmethod
    def list_all():
        return LedgerEntry.query.order_by(LedgerEntry.created_at.desc()).all()

    @staticmethod
    def get_balance(customer_id):
        rows = LedgerEntry.query.filter_by(customer_id=customer_id).all()
        total_credit = sum((Decimal(str(entry.amount)) for entry in rows if entry.type == "credit"), Decimal("0"))
        total_payment = sum((Decimal(str(entry.amount)) for entry in rows if entry.type == "payment"), Decimal("0"))
        total_adjustment = sum((Decimal(str(entry.amount)) for entry in rows if entry.type == "adjustment"), Decimal("0"))
        outstanding = total_credit - total_payment + total_adjustment
        return {
            "customerId": customer_id,
            "total_credit": float(total_credit),
            "total_payment": float(total_payment),
            "total_adjustment": float(total_adjustment),
            "outstanding_balance": float(outstanding),
            "last_updated": max((entry.updated_at for entry in rows), default=datetime.utcnow()).isoformat(),
        }

    @staticmethod
    def create_entry(customer_id, payload):
        entry_data = LedgerService.validate_entry_payload(payload)

        entry = LedgerEntry(
            merchant_id=payload.get("merchantId") or "merchant-001",
            customer_id=customer_id,
            type=entry_data["type"],
            amount=entry_data["amount"],
            currency=(payload.get("currency") or "INR").upper(),
            description=entry_data["description"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.session.add(entry)
        db.session.commit()
        return entry
