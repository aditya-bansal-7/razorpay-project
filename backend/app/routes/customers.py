from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models.customer import Customer
from app.services.customer_service import CustomerService, ValidationError

customers_bp = Blueprint("customers", __name__, url_prefix="/api/customers")


def success_response(data=None, status_code=200):
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, details=None, status_code=400):
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@customers_bp.post("")
def create_customer():
    try:
        customer = CustomerService.create_customer(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)
    except Exception as exc:  # pragma: no cover - fail loudly in production
        db.session.rollback()
        return failure_response("Failed to create customer", {"message": str(exc)}, 500)

    return success_response(customer.to_dict(), 201)


@customers_bp.get("")
def get_customers():
    customers = CustomerService.list_customers()
    return success_response([customer.to_dict() for customer in customers])


@customers_bp.get("/<customer_id>")
def get_customer(customer_id):
    customer = CustomerService.get_customer(customer_id)
    if not customer:
        return failure_response("Customer not found", {"customerId": customer_id}, 404)
    return success_response(customer.to_dict())


@customers_bp.put("/<customer_id>")
def update_customer(customer_id):
    try:
        customer = CustomerService.update_customer(customer_id, request.get_json(silent=True) or {})
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)
    except LookupError:
        return failure_response("Customer not found", {"customerId": customer_id}, 404)
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to update customer", {"message": str(exc)}, 500)

    return success_response(customer.to_dict())


@customers_bp.patch("/<customer_id>")
def patch_customer(customer_id):
    return update_customer(customer_id)


@customers_bp.delete("/<customer_id>")
def delete_customer(customer_id):
    try:
        CustomerService.delete_customer(customer_id)
    except LookupError:
        return failure_response("Customer not found", {"customerId": customer_id}, 404)
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to delete customer", {"message": str(exc)}, 500)

    return jsonify({"success": True, "message": "Customer deleted"})


@customers_bp.get("/<customer_id>/ledger")
def list_customer_ledger(customer_id):
    customer = CustomerService.get_customer(customer_id)
    if not customer:
        return failure_response("Customer not found", {"customerId": customer_id}, 404)

    from app.services.ledger_service import LedgerService

    entries = LedgerService.list_for_customer(customer_id)
    return success_response([entry.to_dict() for entry in entries])


@customers_bp.post("/<customer_id>/ledger")
def create_customer_ledger_entry(customer_id):
    customer = CustomerService.get_customer(customer_id)
    if not customer:
        return failure_response("Customer not found", {"customerId": customer_id}, 404)

    from app.services.ledger_service import LedgerService

    try:
        entry = LedgerService.create_entry(customer_id, request.get_json(silent=True) or {})
    except ValidationError as exc:
        return failure_response(str(exc), exc.details, 400)
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to create ledger entry", {"message": str(exc)}, 500)

    return success_response(entry.to_dict(), 201)


@customers_bp.get("/<customer_id>/balance")
def customer_balance(customer_id):
    customer = CustomerService.get_customer(customer_id)
    if not customer:
        return failure_response("Customer not found", {"customerId": customer_id}, 404)

    from app.services.ledger_service import LedgerService

    balance = LedgerService.get_balance(customer_id)
    return success_response(balance)