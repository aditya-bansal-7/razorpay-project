from datetime import datetime

from app.extensions import db
from app.models.collection_event import CollectionEvent


class ValidationError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class CollectionService:
    @staticmethod
    def validate_payload(payload):
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object", {"body": "expected object"})

        event_type = (payload.get("eventType") or payload.get("event_type") or "").strip()
        if event_type not in {"reminder_generated", "reminder_sent", "payment_link_created", "payment_received", "escalation", "manual_followup"}:
            raise ValidationError("Event type is invalid", {"eventType": "invalid"})

        channel = (payload.get("channel") or "manual").strip().lower()
        if channel not in {"whatsapp", "sms", "email", "manual"}:
            raise ValidationError("Channel is invalid", {"channel": "invalid"})

        status = (payload.get("status") or "scheduled").strip().lower()
        if status not in {"scheduled", "sent", "failed", "queued", "cancelled"}:
            raise ValidationError("Status is invalid", {"status": "invalid"})

        return {
            "event_type": event_type,
            "channel": channel,
            "message": payload.get("message") or None,
            "status": status,
            "scheduled_at": payload.get("scheduledAt") or None,
        }

    @staticmethod
    def list_collection_events(merchant_id=None, customer_id=None):
        query = CollectionEvent.query
        if merchant_id:
            query = query.filter_by(merchant_id=merchant_id)
        if customer_id:
            query = query.filter_by(customer_id=customer_id)
        return query.order_by(CollectionEvent.created_at.desc()).all()

    @staticmethod
    def create_collection_event(merchant_id, customer_id, payload):
        data = CollectionService.validate_payload(payload)
        event = CollectionEvent(
            merchant_id=merchant_id,
            customer_id=customer_id,
            payment_link_id=payload.get("paymentLinkId") or None,
            ledger_entry_id=payload.get("ledgerEntryId") or None,
            event_type=data["event_type"],
            channel=data["channel"],
            message=data["message"],
            status=data["status"],
            scheduled_at=datetime.fromisoformat(str(data["scheduled_at"])) if data["scheduled_at"] else None,
        )
        db.session.add(event)
        db.session.commit()
        return event
