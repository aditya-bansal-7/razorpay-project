from datetime import datetime
from uuid import uuid4

from app.extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"customer-{uuid4().hex[:8]}")
    merchant_id = db.Column(db.String(64), nullable=False, default="merchant-001")
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    ledger_entries = db.relationship(
        "LedgerEntry",
        back_populates="customer",
        cascade="all, delete-orphan",
        lazy="dynamic",
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