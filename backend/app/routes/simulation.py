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


@simulation_bp.post("/simulation/evaluate")
def evaluate_simulation():
    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("seeds") is not None:
            seeds = [int(seed) for seed in payload["seeds"]]
        else:
            seed_count = int(payload.get("seedCount", 20))
            start_seed = int(payload.get("startSeed", 1))
            if seed_count < 1 or seed_count > 1000:
                raise SimulationValidationError("seedCount must be between 1 and 1000")
            seeds = list(range(start_seed, start_seed + seed_count))
        customer_count = int(payload.get("customerCount", SimulationService.DEFAULT_COUNT))
        threshold = float(payload.get("materiallyWorseThreshold", 0.10))
        as_of = SimulationService.DEFAULT_AS_OF
        if payload.get("asOfDate"):
            from datetime import date
            as_of = date.fromisoformat(str(payload["asOfDate"]))
        results = SimulationService.evaluate_seeds(seeds, customer_count, as_of, threshold)
    except (TypeError, ValueError, SimulationValidationError) as exc:
        return failure_response(str(exc), status_code=400)
    return success_response(results)


@simulation_bp.post("/simulation/stress-evaluate")
def stress_evaluate_simulation():
    payload = request.get_json(silent=True) or {}
    try:
        customer_count = int(payload.get("customerCount", SimulationService.DEFAULT_COUNT))
        threshold = float(payload.get("materiallyWorseThreshold", 0.10))
        results = SimulationService.evaluate_stress_scenarios(customer_count=customer_count, materially_worse_threshold=threshold)
    except (TypeError, ValueError, SimulationValidationError) as exc:
        return failure_response(str(exc), status_code=400)
    return success_response(results)


@simulation_bp.get("/simulation/results/<run_id>")
def simulation_results(run_id):
    try:
        run = SimulationService.get(run_id)
    except LookupError as exc:
        return failure_response(str(exc), status_code=404)
    return success_response(run.to_dict())
