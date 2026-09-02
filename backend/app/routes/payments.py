from flask import Blueprint, request

from app.extensions import db
from app.models.payment import Payment
from app.services.customer_service import CustomerService
from app.services.payment_service import PaymentService, ValidationError

payments_bp = Blueprint("payments", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    from flask import jsonify
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, details=None, status_code=400):
    from flask import jsonify
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@payments_bp.get("/payments")
def list_payments():
    merchant_id = request.args.get("merchantId") or "merchant-001"
    payments = PaymentService.list_payments(merchant_id)
    return success_response([payment.to_dict() for payment in payments])


@payments_bp.post("/payments")
def create_payment():
    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customerId")
    if not customer_id:
        return failure_response("Customer ID is required", {"customerId": "required"}, 400)
    if not CustomerService.get_customer(customer_id):
        return failure_response("Customer not found", {"customerId": customer_id}, 404)
    try:
        payment = PaymentService.create_payment(payload.get("merchantId") or "merchant-001", customer_id, payload)
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to create payment", {"message": str(exc)}, 500)
    return success_response(payment.to_dict(), 201)


@payments_bp.get("/payments/<payment_id>")
def get_payment(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        return failure_response("Payment not found", {"paymentId": payment_id}, 404)
    return success_response(payment.to_dict())
