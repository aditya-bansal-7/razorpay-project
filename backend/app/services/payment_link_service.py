from datetime import datetime, timedelta
from decimal import Decimal

from app.extensions import db
from app.models.customer import Customer
from app.models.collection_task import CollectionTask
from app.models.ledger import LedgerEntry
from app.models.payment import Payment
from app.models.payment_link import PaymentLink
from app.services.ledger_service import LedgerService
from app.services.razorpay_service import RazorpayService


class ValidationError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class PaymentLinkService:
    @staticmethod
    def apply_provider_payment(event):
        entity = event.get("payload", {}).get("payment_link", {}).get("entity", {})
        provider_link_id = entity.get("id")
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        provider_payment_id = payment_entity.get("id")
        link = PaymentLink.query.filter_by(provider_link_id=provider_link_id).first()
        if not link or not provider_payment_id:
            raise LookupError("Payment link or provider payment not found")
        if Payment.query.filter_by(provider_payment_id=provider_payment_id).first():
            return link

        new_amount_paid = Decimal(str(entity.get("amount_paid", 0))) / Decimal("100")
        delta = new_amount_paid - Decimal(str(link.amount_paid))
        if delta <= 0:
            return link

        payment = Payment(
            merchant_id=link.merchant_id,
            customer_id=link.customer_id,
            ledger_entry_id=None,
            payment_link_id=link.id,
            provider="razorpay",
            provider_payment_id=provider_payment_id,
            amount=delta,
            currency=link.currency,
            status="completed",
            paid_at=datetime.utcnow(),
        )
        ledger_entry = LedgerEntry(
            merchant_id=link.merchant_id,
            customer_id=link.customer_id,
            type="payment",
            amount=delta,
            currency=link.currency,
            description="Razorpay payment received",
            transaction_date=payment.paid_at,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        payment.ledger_entry = ledger_entry
        link.amount_paid = new_amount_paid
        link.amount_due = max(Decimal("0"), Decimal(str(link.amount)) - new_amount_paid)
        link.status = "completed" if link.amount_due == 0 else "active"
        task = CollectionTask.query.filter_by(payment_link_id=provider_link_id).first()
        if task:
            balance = LedgerService.get_balance(task.customer_id)
            if link.amount_due > 0:
                from app.services.collection_task_service import CollectionTaskService

                metrics = CollectionTaskService._metrics(task.customer)
                action, confidence, reason, score = CollectionTaskService._recommendation(metrics)
                task.action = action
                task.priority = CollectionTaskService._priority(score)
                task.reason = reason
                task.confidence = confidence
                task.priority_score = score
                task.metrics = metrics
            else:
                task.metrics = {**(task.metrics or {}), "outstandingAmount": balance["outstanding_balance"], "daysOverdue": balance.get("days_overdue", 0), "customerStatus": balance.get("customer_status")}
            task.recommended_amount = link.amount_due
            task.status = "completed" if link.amount_due == 0 else "executed"
            task.updated_at = datetime.utcnow()
        db.session.add(payment)
        db.session.commit()
        return link

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

        return {
            "amount": numeric_amount,
            "currency": (payload.get("currency") or "INR").upper(),
            "accept_partial": bool(payload.get("acceptPartial", False)),
            "first_min_partial_amount": payload.get("firstMinPartialAmount"),
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
        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise LookupError("Customer not found")

        balance = LedgerService.get_balance(customer_id)["outstanding_balance"]
        if data["amount"] > Decimal(str(balance)):
            raise ValidationError("Payment link amount cannot exceed outstanding balance", {"amount": "exceeds_outstanding"})

        ledger_entry_id = payload.get("ledgerEntryId") or None
        if ledger_entry_id and not db.session.get(LedgerEntry, ledger_entry_id):
            raise ValidationError("Ledger entry not found", {"ledgerEntryId": "not_found"})

        provider_data = RazorpayService.create_payment_link(
            customer=customer,
            amount=data["amount"],
            currency=data["currency"],
            accept_partial=data["accept_partial"],
            first_min_partial_amount=data["first_min_partial_amount"],
            reference_id=payload.get("referenceId"),
            notes=payload.get("notes"),
        )

        payment_link = PaymentLink(
            merchant_id=merchant_id,
            customer_id=customer_id,
            ledger_entry_id=ledger_entry_id,
            amount=data["amount"],
            amount_paid=Decimal("0"),
            amount_due=data["amount"],
            currency=data["currency"],
            provider="razorpay",
            provider_link_id=provider_data["id"],
            short_url=provider_data["short_url"],
            status="issued",
            expires_at=(datetime.utcfromtimestamp(provider_data["expire_by"]) if provider_data.get("expire_by") else None),
        )
        db.session.add(payment_link)
        db.session.commit()
        return payment_link
