from flask import Blueprint, request

from app.extensions import db
from app.models.collection_event import CollectionEvent
from app.services.collection_service import CollectionService, ValidationError
from app.services.customer_service import CustomerService

collection_events_bp = Blueprint("collection_events", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    from flask import jsonify
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, details=None, status_code=400):
    from flask import jsonify
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@collection_events_bp.get("/collection-events")
def list_collection_events():
    merchant_id = request.args.get("merchantId") or "merchant-001"
    events = CollectionService.list_collection_events(merchant_id)
    return success_response([event.to_dict() for event in events])


@collection_events_bp.get("/customers/<customer_id>/collection-events")
def get_customer_collection_events(customer_id):
    customer = CustomerService.get_customer(customer_id)
    if not customer:
        return failure_response("Customer not found", {"customerId": customer_id}, 404)
    events = CollectionService.list_collection_events(customer.merchant_id, customer_id)
    return success_response([event.to_dict() for event in events])


@collection_events_bp.post("/collection-events")
def create_collection_event():
    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customerId")
    if not customer_id:
        return failure_response("Customer ID is required", {"customerId": "required"}, 400)
    if not CustomerService.get_customer(customer_id):
        return failure_response("Customer not found", {"customerId": customer_id}, 404)
    try:
        event = CollectionService.create_collection_event(payload.get("merchantId") or "merchant-001", customer_id, payload)
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to create collection event", {"message": str(exc)}, 500)
    return success_response(event.to_dict(), 201)


@collection_events_bp.get("/collection-events/<event_id>")
def get_collection_event(event_id):
    event = db.session.get(CollectionEvent, event_id)
    if not event:
        return failure_response("Collection event not found", {"eventId": event_id}, 404)
    return success_response(event.to_dict())
