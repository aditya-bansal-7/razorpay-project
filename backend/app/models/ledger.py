from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from app.extensions import db


class LedgerEntry(db.Model):
    __tablename__ = "ledger_entries"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"ledger-{uuid4().hex[:8]}")
    merchant_id = db.Column(db.String(64), nullable=False, default="merchant-001")
    customer_id = db.Column(db.String(64), db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(precision=12, scale=2), nullable=False)
    currency = db.Column(db.String(10), nullable=False, default="INR")
    description = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer = db.relationship("Customer", back_populates="ledger_entries")

    __table_args__ = (
        db.CheckConstraint("type IN ('credit', 'payment', 'adjustment')", name="ledger_type_valid"),
        db.CheckConstraint("amount > 0", name="ledger_amount_positive"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "merchantId": self.merchant_id,
            "customerId": self.customer_id,
            "type": self.type,
            "amount": float(self.amount),
            "currency": self.currency,
            "description": self.description,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
