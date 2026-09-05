from datetime import datetime
from uuid import uuid4

from app.extensions import db


class SimulationRun(db.Model):
    __tablename__ = "simulation_runs"

    id = db.Column(db.String(64), primary_key=True, default=lambda: f"simulation-{uuid4().hex[:10]}")
    merchant_id = db.Column(db.String(64), nullable=False, default="merchant-001")
    seed = db.Column(db.Integer, nullable=False)
    customer_count = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="generated")
    dataset = db.Column(db.JSON, nullable=False, default=dict)
    results = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.CheckConstraint("status IN ('generated','completed','failed')", name="simulation_run_status_valid"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "merchantId": self.merchant_id,
            "seed": self.seed,
            "customerCount": self.customer_count,
            "status": self.status,
            "results": self.results,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }