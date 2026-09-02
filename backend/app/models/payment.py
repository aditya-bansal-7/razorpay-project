from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from app.extensions import db


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"payment-{uuid4().hex[:8]}")
    merchant_id = db.Column(db.String(64), db.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    customer_id = db.Column(db.String(64), db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    ledger_entry_id = db.Column(db.String(64), db.ForeignKey("ledger_entries.id", ondelete="SET NULL"), nullable=True)
    payment_link_id = db.Column(db.String(64), db.ForeignKey("payment_links.id", ondelete="SET NULL"), nullable=True)
    provider = db.Column(db.String(30), nullable=True)
    provider_payment_id = db.Column(db.String(120), nullable=True)
    provider_order_id = db.Column(db.String(120), nullable=True)
    provider_payment_link_id = db.Column(db.String(120), nullable=True)
    amount = db.Column(db.Numeric(precision=12, scale=2), nullable=False)
    currency = db.Column(db.String(10), nullable=False, default="INR")
    status = db.Column(db.String(20), nullable=False, default="pending")
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = db.relationship("Merchant", back_populates="payments")
    customer = db.relationship("Customer", back_populates="payments")
    ledger_entry = db.relationship("LedgerEntry", back_populates="payments")
    payment_link = db.relationship("PaymentLink", back_populates="payments")

    __table_args__ = (
        db.CheckConstraint("status IN ('pending','completed','failed','refunded')", name="payment_status_valid"),
        db.CheckConstraint("amount > 0", name="payment_amount_positive"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "merchantId": self.merchant_id,
            "customerId": self.customer_id,
            "ledgerEntryId": self.ledger_entry_id,
            "paymentLinkId": self.payment_link_id,
            "provider": self.provider,
            "providerPaymentId": self.provider_payment_id,
            "providerOrderId": self.provider_order_id,
            "providerPaymentLinkId": self.provider_payment_link_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "status": self.status,
            "paidAt": self.paid_at.isoformat() if self.paid_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
