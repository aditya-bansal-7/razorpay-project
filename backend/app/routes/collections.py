from flask import Blueprint, jsonify

from app.extensions import db
from app.models.collection_task import CollectionTask
from app.services.collection_task_service import CollectionTaskService

collections_bp = Blueprint("collections", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, status_code=400, details=None):
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


@collections_bp.get("/collections/queue")
def collection_queue():
    tasks = CollectionTaskService.queue()
    return success_response([task.to_dict() for task in tasks])


@collections_bp.post("/collections/evaluate/<customer_id>")
def evaluate_customer(customer_id):
    try:
        task = CollectionTaskService.evaluate_customer(customer_id)
    except LookupError as exc:
        return failure_response(str(exc), 404)
    return success_response(task.to_dict() if task else None)


@collections_bp.post("/collections/<task_id>/approve")
def approve_collection_task(task_id):
    try:
            task = CollectionTaskService.execute(task_id)
    except CollectionTaskService.ExecutionError as exc:
        task = db.session.get(CollectionTask, task_id)
        return failure_response(str(exc), exc.status_code, {"taskId": task_id, "status": task.status if task else None, "executionError": task.execution_error if task else None})
    return success_response(task.to_dict())


@collections_bp.post("/collections/<task_id>/reject")
def reject_collection_task(task_id):
    try:
        task = CollectionTaskService.set_status(task_id, "rejected")
    except CollectionTaskService.ExecutionError as exc:
        return failure_response(str(exc), exc.status_code)
    except LookupError as exc:
        return failure_response(str(exc), 404)
    return success_response(task.to_dict())