from datetime import datetime, timedelta
from decimal import Decimal

from app.extensions import db
from app.models.payment_link import PaymentLink


class ValidationError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class PaymentLinkService:
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

        provider = (payload.get("provider") or "internal").strip().lower()
        if provider not in {"internal", "razorpay"}:
            raise ValidationError("Provider is invalid", {"provider": "invalid"})

        status = (payload.get("status") or "draft").strip().lower()
        if status not in {"draft", "active", "completed", "expired", "cancelled"}:
            raise ValidationError("Payment link status is invalid", {"status": "invalid"})

        return {
            "amount": numeric_amount,
            "currency": (payload.get("currency") or "INR").upper(),
            "provider": provider,
            "status": status,
            "expires_at": payload.get("expiresAt") or None,
            "short_url": payload.get("shortUrl") or None,
            "provider_link_id": payload.get("providerLinkId") or None,
        }

    @staticmethod
    def list_payment_links(merchant_id=None):
        query = PaymentLink.query
        if merchant_id:
            query = query.filter_by(merchant_id=merchant_id)
        return query.order_by(PaymentLink.created_at.desc()).all()

    @staticmethod
    def create_payment_link(merchant_id, customer_id, payload):
        data = PaymentLinkService.validate_payload(payload)
        expires_at = None
        if payload.get("expiresAt"):
            expires_at = datetime.fromisoformat(str(payload.get("expiresAt")))
        elif data["provider"] == "internal":
            expires_at = datetime.utcnow() + timedelta(days=7)

        payment_link = PaymentLink(
            merchant_id=merchant_id,
            customer_id=customer_id,
            amount=data["amount"],
            amount_paid=Decimal("0"),
            amount_due=data["amount"],
            currency=data["currency"],
            provider=data["provider"],
            provider_link_id=data["provider_link_id"],
            short_url=data["short_url"],
            status=data["status"],
            expires_at=expires_at,
        )
        db.session.add(payment_link)
        db.session.commit()
        return payment_link
