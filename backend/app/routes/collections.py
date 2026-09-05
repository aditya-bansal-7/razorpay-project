from flask import Blueprint, jsonify

from app.services.collection_task_service import CollectionTaskService

collections_bp = Blueprint("collections", __name__, url_prefix="/api")


def success_response(data=None, status_code=200):
    return jsonify({"success": True, "data": data}), status_code


def failure_response(message, status_code=400):
    return jsonify({"success": False, "error": message}), status_code


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
        task = CollectionTaskService.set_status(task_id, "approved")
    except LookupError as exc:
        return failure_response(str(exc), 404)
    return success_response(task.to_dict())


@collections_bp.post("/collections/<task_id>/reject")
def reject_collection_task(task_id):
    try:
        task = CollectionTaskService.set_status(task_id, "rejected")
    except LookupError as exc:
        return failure_response(str(exc), 404)
    return success_response(task.to_dict())