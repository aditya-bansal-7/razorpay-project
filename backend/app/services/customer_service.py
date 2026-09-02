from datetime import datetime

from app.extensions import db
from app.models.customer import Customer


class ValidationError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class CustomerService:
    @staticmethod
    def validate_payload(payload):
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object", {"body": "expected object"})

        name = (payload.get("name") or "").strip()
        phone = (payload.get("phone") or "").strip()
        email = (payload.get("email") or "").strip() or None
        address = (payload.get("address") or "").strip() or None

        if not name:
            raise ValidationError("Customer name is required", {"name": "required"})
        if not phone:
            raise ValidationError("Customer phone is required", {"phone": "required"})
        if len(phone) < 10:
            raise ValidationError("Phone number must be at least 10 digits", {"phone": "min_length"})

        if email and "@" not in email:
            raise ValidationError("Email is invalid", {"email": "invalid"})

        return {
            "name": name,
            "phone": phone,
            "email": email,
            "address": address,
        }

    @staticmethod
    def list_customers():
        return Customer.query.order_by(Customer.created_at.desc()).all()

    @staticmethod
    def get_customer(customer_id):
        return Customer.query.get(customer_id)

    @staticmethod
    def create_customer(payload):
        data = CustomerService.validate_payload(payload)

        existing = Customer.query.filter_by(phone=data["phone"]).first()
        if existing:
            raise ValidationError("A customer with this phone number already exists", {"phone": "duplicate"})

        customer = Customer(
            merchant_id=payload.get("merchantId") or "merchant-001",
            name=data["name"],
            phone=data["phone"],
            email=data["email"],
            address=data["address"],
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(customer)
        db.session.commit()
        return customer

    @staticmethod
    def update_customer(customer_id, payload):
        customer = Customer.query.get(customer_id)
        if not customer:
            raise LookupError("Customer not found")

        data = CustomerService.validate_payload({**customer.to_dict(), **(payload or {})})

        if payload.get("phone") and payload.get("phone") != customer.phone:
            duplicate = Customer.query.filter(Customer.phone == data["phone"], Customer.id != customer_id).first()
            if duplicate:
                raise ValidationError("A customer with this phone number already exists", {"phone": "duplicate"})

        customer.name = data["name"]
        customer.phone = data["phone"]
        customer.email = data["email"]
        customer.address = data["address"]
        if payload.get("status") in {"active", "inactive", "overdue", "settled"}:
            customer.status = payload["status"]
        customer.updated_at = datetime.utcnow()
        db.session.commit()
        return customer

    @staticmethod
    def delete_customer(customer_id):
        customer = Customer.query.get(customer_id)
        if not customer:
            raise LookupError("Customer not found")
        db.session.delete(customer)
        db.session.commit()
        return True
