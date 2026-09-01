from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.customer import Customer

customers_bp = Blueprint("customers", __name__, url_prefix="/api/customers")


@customers_bp.post("")
def create_customer():
    data = request.get_json()

    name = data.get("name")
    phone = data.get("phone")

    if not name or not phone:
        return jsonify({
            "error": "name and phone are required"
        }), 400

    customer = Customer(
        name=name,
        phone=phone
    )

    db.session.add(customer)
    db.session.commit()

    return jsonify({
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone
    }), 201


@customers_bp.get("")
def get_customers():
    customers = Customer.query.order_by(
        Customer.created_at.desc()
    ).all()

    return jsonify([
        {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone
        }
        for customer in customers
    ])