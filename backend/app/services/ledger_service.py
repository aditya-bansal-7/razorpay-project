from datetime import datetime
from decimal import Decimal

from flask import current_app

from app.extensions import db
from app.models.customer import Customer
from app.models.ledger import LedgerEntry


class ValidationError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class LedgerService:
    @staticmethod
    def parse_date(value, field_name):
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValidationError(f"{field_name} must be an ISO date/time string", {field_name: "invalid"}) from exc
        raise ValidationError(f"{field_name} must be a date or ISO string", {field_name: "invalid"})

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
        except Exception as exc:
            raise ValidationError("Amount must be numeric", {"amount": "invalid"}) from exc

        if numeric_amount <= 0:
            raise ValidationError("Amount must be greater than zero", {"amount": "min_value"})

        transaction_date = LedgerService.parse_date(payload.get("transactionDate") or payload.get("transaction_date"), "transactionDate") or datetime.utcnow()
        due_date = LedgerService.parse_date(payload.get("dueDate") or payload.get("due_date"), "dueDate")

        return {
            "type": entry_type,
            "amount": numeric_amount,
            "description": description,
            "transaction_date": transaction_date,
            "due_date": due_date,
            "currency": (payload.get("currency") or "INR").upper(),
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
    def get_customer_status(customer_id):
        balance = LedgerService.get_balance(customer_id)
        return balance["customer_status"]

    @staticmethod
    def get_balance(customer_id):
        rows = LedgerEntry.query.filter_by(customer_id=customer_id).all()
        total_credit = sum((Decimal(str(entry.amount)) for entry in rows if entry.type == "credit"), Decimal("0"))
        total_payment = sum((Decimal(str(entry.amount)) for entry in rows if entry.type == "payment"), Decimal("0"))
        total_adjustment = sum((Decimal(str(entry.amount)) for entry in rows if entry.type == "adjustment"), Decimal("0"))
        outstanding = total_credit - total_payment + total_adjustment
        overdue_entries = [
            entry for entry in rows
            if entry.type == "credit" and entry.due_date and entry.due_date < datetime.utcnow() and outstanding > 0
        ]
        overdue_days = max(((datetime.utcnow() - entry.due_date).days for entry in overdue_entries), default=0)
        customer_status = "settled" if outstanding <= 0 else "overdue" if overdue_entries else "active"

        return {
            "customerId": customer_id,
            "total_credit": float(total_credit),
            "total_payment": float(total_payment),
            "total_adjustment": float(total_adjustment),
            "outstanding_balance": float(outstanding),
            "customer_status": customer_status,
            "days_overdue": overdue_days,
            "last_updated": max((entry.updated_at for entry in rows), default=datetime.utcnow()).isoformat(),
        }

    @staticmethod
    def create_entry(customer_id, payload):
        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise LookupError("Customer not found")

        entry_data = LedgerService.validate_entry_payload(payload)
        entry = LedgerEntry(
            merchant_id=payload.get("merchantId") or customer.merchant_id or current_app.config.get("DEFAULT_MERCHANT_ID", "merchant-001"),
            customer_id=customer_id,
            type=entry_data["type"],
            amount=entry_data["amount"],
            currency=entry_data["currency"],
            description=entry_data["description"],
            transaction_date=entry_data["transaction_date"],
            due_date=entry_data["due_date"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(entry)
        db.session.commit()
        return entry
