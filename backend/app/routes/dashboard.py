from flask import Blueprint, request

from app.extensions import db
from app.services.dashboard_service import DashboardService


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    from flask import jsonify
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, details=None, status_code=400):
    from flask import jsonify
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@dashboard_bp.get("/dashboard")
def get_dashboard():
    try:
        metrics = DashboardService.get_dashboard_metrics(merchant_id=request.args.get("merchantId") or "merchant-001")
    except Exception as exc:
        db.session.rollback()
        return failure_response("Failed to load dashboard", {"message": str(exc)}, 500)
    return success_response(metrics)
