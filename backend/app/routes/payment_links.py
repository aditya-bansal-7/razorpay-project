from flask import Blueprint, request

from app.extensions import db
from app.models.payment_link import PaymentLink
from app.services.customer_service import CustomerService
from app.services.payment_link_service import PaymentLinkService, ValidationError

payment_links_bp = Blueprint("payment_links", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    from flask import jsonify
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, details=None, status_code=400):
    from flask import jsonify
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@payment_links_bp.get("/payment-links")
def list_payment_links():
    merchant_id = request.args.get("merchantId") or "merchant-001"
    links = PaymentLinkService.list_payment_links(merchant_id)
    return success_response([link.to_dict() for link in links])


@payment_links_bp.post("/payment-links")
def create_payment_link():
    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customerId")
    if not customer_id:
        return failure_response("Customer ID is required", {"customerId": "required"}, 400)
    if not CustomerService.get_customer(customer_id):
        return failure_response("Customer not found", {"customerId": customer_id}, 404)
    try:
        link = PaymentLinkService.create_payment_link(payload.get("merchantId") or "merchant-001", customer_id, payload)
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to create payment link", {"message": str(exc)}, 500)
    return success_response(link.to_dict(), 201)


@payment_links_bp.get("/payment-links/<payment_link_id>")
def get_payment_link(payment_link_id):
    link = db.session.get(PaymentLink, payment_link_id)
    if not link:
        return failure_response("Payment link not found", {"paymentLinkId": payment_link_id}, 404)
    return success_response(link.to_dict())
