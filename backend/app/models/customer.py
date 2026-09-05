from datetime import datetime
from uuid import uuid4

from app.extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"customer-{uuid4().hex[:8]}")
    merchant_id = db.Column(db.String(64), db.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    merchant = db.relationship("Merchant", back_populates="customers")
    ledger_entries = db.relationship("LedgerEntry", back_populates="customer", cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="customer", cascade="all, delete-orphan")
    payment_links = db.relationship("PaymentLink", back_populates="customer", cascade="all, delete-orphan")
    collection_events = db.relationship("CollectionEvent", back_populates="customer", cascade="all, delete-orphan")
    collection_tasks = db.relationship("CollectionTask", back_populates="customer", cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("merchant_id", "phone", name="uq_customer_merchant_phone"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "merchantId": self.merchant_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "status": self.status,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }