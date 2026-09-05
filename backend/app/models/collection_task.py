from datetime import datetime
from uuid import uuid4

from app.extensions import db


class CollectionTask(db.Model):
    __tablename__ = "collection_tasks"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"task-{uuid4().hex[:8]}")
    merchant_id = db.Column(db.String(64), db.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    customer_id = db.Column(db.String(64), db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    ledger_entry_id = db.Column(db.String(64), db.ForeignKey("ledger_entries.id", ondelete="SET NULL"), nullable=True)
    action = db.Column(db.String(30), nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    reason = db.Column(db.Text, nullable=False)
    confidence = db.Column(db.Numeric(precision=5, scale=2), nullable=False, default=0)
    recommended_amount = db.Column(db.Numeric(precision=12, scale=2), nullable=False, default=0)
    channel = db.Column(db.String(20), nullable=False, default="whatsapp")
    priority_score = db.Column(db.Numeric(precision=8, scale=2), nullable=False, default=0)
    metrics = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)

    merchant = db.relationship("Merchant", back_populates="collection_tasks")
    customer = db.relationship("Customer", back_populates="collection_tasks")
    ledger_entry = db.relationship("LedgerEntry", back_populates="collection_tasks")

    __table_args__ = (
        db.CheckConstraint("action IN ('SEND_REMINDER','OFFER_PARTIAL','ESCALATE','WAIT')", name="collection_task_action_valid"),
        db.CheckConstraint("priority IN ('low','medium','high','critical')", name="collection_task_priority_valid"),
        db.CheckConstraint("status IN ('pending','approved','rejected','completed')", name="collection_task_status_valid"),
        db.CheckConstraint("channel IN ('whatsapp','sms','email','manual')", name="collection_task_channel_valid"),
        db.CheckConstraint("confidence >= 0 AND confidence <= 1", name="collection_task_confidence_valid"),
        db.Index("ix_collection_task_customer_status", "customer_id", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "merchantId": self.merchant_id,
            "customerId": self.customer_id,
            "customerName": self.customer.name if self.customer else None,
            "ledgerEntryId": self.ledger_entry_id,
            "action": self.action,
            "priority": self.priority,
            "status": self.status,
            "reason": self.reason,
            "confidence": float(self.confidence),
            "recommendedAmount": float(self.recommended_amount),
            "channel": self.channel,
            "priorityScore": float(self.priority_score),
            "metrics": self.metrics or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "approvedAt": self.approved_at.isoformat() if self.approved_at else None,
            "rejectedAt": self.rejected_at.isoformat() if self.rejected_at else None,
        }