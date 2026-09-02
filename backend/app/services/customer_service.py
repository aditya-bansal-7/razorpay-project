from datetime import datetime

from flask import current_app

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
    def list_customers(merchant_id=None):
        query = Customer.query
        if merchant_id:
            query = query.filter_by(merchant_id=merchant_id)
        return query.order_by(Customer.created_at.desc()).all()

    @staticmethod
    def get_customer(customer_id):
        return db.session.get(Customer, customer_id)

    @staticmethod
    def default_merchant_id():
        return current_app.config.get("DEFAULT_MERCHANT_ID", "merchant-001")

    @staticmethod
    def create_customer(payload):
        data = CustomerService.validate_payload(payload)
        merchant_id = payload.get("merchantId") or CustomerService.default_merchant_id()

        existing = Customer.query.filter_by(merchant_id=merchant_id, phone=data["phone"]).first()
        if existing:
            raise ValidationError("A customer with this phone number already exists in this merchant", {"phone": "duplicate"})

        customer = Customer(
            merchant_id=merchant_id,
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
        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise LookupError("Customer not found")

        data = CustomerService.validate_payload({**customer.to_dict(), **(payload or {})})
        if payload.get("phone") and payload.get("phone") != customer.phone:
            duplicate = Customer.query.filter(Customer.merchant_id == customer.merchant_id, Customer.phone == data["phone"], Customer.id != customer_id).first()
            if duplicate:
                raise ValidationError("A customer with this phone number already exists in this merchant", {"phone": "duplicate"})

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
        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise LookupError("Customer not found")
        db.session.delete(customer)
        db.session.commit()
        return True
