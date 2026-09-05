from datetime import datetime
from uuid import uuid4

from app.extensions import db


class Merchant(db.Model):
    __tablename__ = "merchants"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"merchant-{uuid4().hex[:8]}")
    name = db.Column(db.String(120), nullable=False, default="KiranaKart")
    email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customers = db.relationship("Customer", back_populates="merchant", cascade="all, delete-orphan")
    ledger_entries = db.relationship("LedgerEntry", back_populates="merchant", cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="merchant", cascade="all, delete-orphan")
    payment_links = db.relationship("PaymentLink", back_populates="merchant", cascade="all, delete-orphan")
    collection_events = db.relationship("CollectionEvent", back_populates="merchant", cascade="all, delete-orphan")
    collection_tasks = db.relationship("CollectionTask", back_populates="merchant", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
