from flask import Blueprint, request

from app.extensions import db
from app.services.merchant_service import MerchantService, ValidationError

merchant_bp = Blueprint("merchant", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    from flask import jsonify
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, details=None, status_code=400):
    from flask import jsonify
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@merchant_bp.get("/merchants")
def get_merchants():
    merchants = MerchantService.list_merchants()
    return success_response([merchant.to_dict() for merchant in merchants])


@merchant_bp.get("/merchants/<merchant_id>")
def get_merchant(merchant_id):
    merchant = MerchantService.get_merchant(merchant_id)
    if not merchant:
        return failure_response("Merchant not found", {"merchantId": merchant_id}, 404)
    return success_response(merchant.to_dict())


@merchant_bp.post("/merchants")
def create_merchant():
    try:
        merchant = MerchantService.create_merchant(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to create merchant", {"message": str(exc)}, 500)
    return success_response(merchant.to_dict(), 201)
