from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.models.payment import Payment


class ValidationError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class PaymentService:
    @staticmethod
    def validate_payload(payload):
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object", {"body": "expected object"})

        amount = payload.get("amount")
        if amount is None:
            raise ValidationError("Amount is required", {"amount": "required"})
        try:
            numeric_amount = Decimal(str(amount))
        except Exception as exc:  # pragma: no cover
            raise ValidationError("Amount must be numeric", {"amount": "invalid"}) from exc
        if numeric_amount <= 0:
            raise ValidationError("Amount must be greater than zero", {"amount": "min_value"})

        status = (payload.get("status") or "pending").strip().lower()
        if status not in {"pending", "completed", "failed", "refunded"}:
            raise ValidationError("Payment status is invalid", {"status": "invalid"})

        return {
            "amount": numeric_amount,
            "currency": (payload.get("currency") or "INR").upper(),
            "provider": (payload.get("provider") or "internal").strip() or "internal",
            "status": status,
            "provider_payment_id": payload.get("providerPaymentId") or None,
            "provider_order_id": payload.get("providerOrderId") or None,
            "provider_payment_link_id": payload.get("providerPaymentLinkId") or None,
            "paid_at": payload.get("paidAt") or None,
        }

    @staticmethod
    def list_payments(merchant_id=None):
        query = Payment.query
        if merchant_id:
            query = query.filter_by(merchant_id=merchant_id)
        return query.order_by(Payment.created_at.desc()).all()

    @staticmethod
    def create_payment(merchant_id, customer_id, payload):
        data = PaymentService.validate_payload(payload)
        payment = Payment(
            merchant_id=merchant_id,
            customer_id=customer_id,
            ledger_entry_id=payload.get("ledgerEntryId") or None,
            payment_link_id=payload.get("paymentLinkId") or None,
            provider=data["provider"],
            provider_payment_id=data["provider_payment_id"],
            provider_order_id=data["provider_order_id"],
            provider_payment_link_id=data["provider_payment_link_id"],
            amount=data["amount"],
            currency=data["currency"],
            status=data["status"],
            paid_at=datetime.utcnow() if data["status"] == "completed" else None,
        )
        db.session.add(payment)
        db.session.commit()
        return payment
