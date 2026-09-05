from flask import Blueprint, jsonify, request

from app.services.simulation_service import SimulationService, SimulationValidationError

simulation_bp = Blueprint("simulation", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, details=None, status_code=400):
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@simulation_bp.post("/simulation/generate")
def generate_simulation():
    try:
        run = SimulationService.generate("merchant-001", request.get_json(silent=True) or {})
    except SimulationValidationError as exc:
        return failure_response(str(exc), status_code=400)
    return success_response(run.to_dict(), 201)


@simulation_bp.post("/simulation/run")
def run_simulation():
    payload = request.get_json(silent=True) or {}
    run_id = payload.get("id") or payload.get("runId")
    if not run_id:
        return failure_response("Simulation run ID is required", {"runId": "required"})
    try:
        run = SimulationService.run(run_id)
    except LookupError as exc:
        return failure_response(str(exc), status_code=404)
    return success_response(run.to_dict())


@simulation_bp.get("/simulation/results/<run_id>")
def simulation_results(run_id):
    try:
        run = SimulationService.get(run_id)
    except LookupError as exc:
        return failure_response(str(exc), status_code=404)
    return success_response(run.to_dict())
