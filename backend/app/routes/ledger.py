from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models.ledger import LedgerEntry
from app.services.ledger_service import LedgerService, ValidationError

ledger_bp = Blueprint("ledger", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, details=None, status_code=400):
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@ledger_bp.get("/ledger")
def list_ledger_entries():
    entries = LedgerService.list_all()
    return success_response([entry.to_dict() for entry in entries])


@ledger_bp.get("/ledger/<entry_id>")
def get_ledger_entry(entry_id):
    entry = db.session.get(LedgerEntry, entry_id)
    if not entry:
        return failure_response("Ledger entry not found", {"entryId": entry_id}, 404)
    return success_response(entry.to_dict())


@ledger_bp.post("/ledger")
def create_ledger_entry():
    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customerId")
    if not customer_id:
        return failure_response("Customer ID is required", {"customerId": "required"}, 400)

    from app.services.customer_service import CustomerService

    if not CustomerService.get_customer(customer_id):
        return failure_response("Customer not found", {"customerId": customer_id}, 404)

    try:
        entry = LedgerService.create_entry(customer_id, payload)
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to create ledger entry", {"message": str(exc)}, 500)

    return success_response(entry.to_dict(), 201)


@ledger_bp.put("/ledger/<entry_id>")
def update_ledger_entry(entry_id):
    entry = db.session.get(LedgerEntry, entry_id)
    if not entry:
        return failure_response("Ledger entry not found", {"entryId": entry_id}, 404)

    payload = request.get_json(silent=True) or {}
    try:
        entry_data = LedgerService.validate_entry_payload(payload)
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)

    entry.type = entry_data["type"]
    entry.amount = entry_data["amount"]
    entry.description = entry_data["description"]
    entry.currency = (payload.get("currency") or "INR").upper()
    entry.updated_at = db.func.now()
    db.session.commit()
    return success_response(entry.to_dict())


@ledger_bp.delete("/ledger/<entry_id>")
def delete_ledger_entry(entry_id):
    entry = db.session.get(LedgerEntry, entry_id)
    if not entry:
        return failure_response("Ledger entry not found", {"entryId": entry_id}, 404)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"success": True, "message": "Ledger entry deleted"})
