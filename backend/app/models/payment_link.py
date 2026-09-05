from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from app.extensions import db


class PaymentLink(db.Model):
    __tablename__ = "payment_links"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"payment-link-{uuid4().hex[:8]}")
    merchant_id = db.Column(db.String(64), db.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    customer_id = db.Column(db.String(64), db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    ledger_entry_id = db.Column(db.String(64), db.ForeignKey("ledger_entries.id", ondelete="SET NULL"), nullable=True)
    amount = db.Column(db.Numeric(precision=12, scale=2), nullable=False)
    amount_paid = db.Column(db.Numeric(precision=12, scale=2), nullable=False, default=Decimal("0"))
    amount_due = db.Column(db.Numeric(precision=12, scale=2), nullable=False, default=Decimal("0"))
    currency = db.Column(db.String(10), nullable=False, default="INR")
    provider = db.Column(db.String(20), nullable=False, default="internal")
    provider_link_id = db.Column(db.String(120), nullable=True)
    short_url = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft")
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = db.relationship("Merchant", back_populates="payment_links")
    customer = db.relationship("Customer", back_populates="payment_links")
    ledger_entry = db.relationship("LedgerEntry", back_populates="payment_links")
    payments = db.relationship("Payment", back_populates="payment_link", cascade="all, delete-orphan")
    collection_events = db.relationship("CollectionEvent", back_populates="payment_link", cascade="all, delete-orphan")

    __table_args__ = (
        db.CheckConstraint("provider IN ('internal','razorpay')", name="payment_link_provider_valid"),
        db.CheckConstraint("amount > 0", name="payment_link_amount_positive"),
        db.CheckConstraint("status IN ('draft','issued','active','completed','expired','cancelled')", name="payment_link_status_valid"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "merchantId": self.merchant_id,
            "customerId": self.customer_id,
            "ledgerEntryId": self.ledger_entry_id,
            "amount": float(self.amount),
            "amountPaid": float(self.amount_paid),
            "amountDue": float(self.amount_due),
            "currency": self.currency,
            "provider": self.provider,
            "providerLinkId": self.provider_link_id,
            "shortUrl": self.short_url,
            "status": self.status,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
