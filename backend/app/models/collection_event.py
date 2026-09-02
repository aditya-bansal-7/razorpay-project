from datetime import datetime
from uuid import uuid4

from app.extensions import db


class CollectionEvent(db.Model):
    __tablename__ = "collection_events"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"event-{uuid4().hex[:8]}")
    merchant_id = db.Column(db.String(64), db.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    customer_id = db.Column(db.String(64), db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    payment_link_id = db.Column(db.String(64), db.ForeignKey("payment_links.id", ondelete="SET NULL"), nullable=True)
    ledger_entry_id = db.Column(db.String(64), db.ForeignKey("ledger_entries.id", ondelete="SET NULL"), nullable=True)
    event_type = db.Column(db.String(30), nullable=False)
    channel = db.Column(db.String(20), nullable=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="scheduled")
    scheduled_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = db.relationship("Merchant", back_populates="collection_events")
    customer = db.relationship("Customer", back_populates="collection_events")
    payment_link = db.relationship("PaymentLink", back_populates="collection_events")
    ledger_entry = db.relationship("LedgerEntry", back_populates="collection_events")

    __table_args__ = (
        db.CheckConstraint("event_type IN ('reminder_generated','reminder_sent','payment_link_created','payment_received','escalation','manual_followup')", name="collection_event_type_valid"),
        db.CheckConstraint("channel IN ('whatsapp','sms','email','manual')", name="collection_event_channel_valid"),
        db.CheckConstraint("status IN ('scheduled','sent','failed','queued','cancelled')", name="collection_event_status_valid"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "merchantId": self.merchant_id,
            "customerId": self.customer_id,
            "paymentLinkId": self.payment_link_id,
            "ledgerEntryId": self.ledger_entry_id,
            "eventType": self.event_type,
            "channel": self.channel,
            "message": self.message,
            "status": self.status,
            "scheduledAt": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sentAt": self.sent_at.isoformat() if self.sent_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
