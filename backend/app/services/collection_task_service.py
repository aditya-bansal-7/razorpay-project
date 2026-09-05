from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.models.collection_task import CollectionTask
from app.models.customer import Customer
from app.models.payment_link import PaymentLink
from app.services.ledger_service import LedgerService
from app.services.razorpay_service import RazorpayService


class CollectionTaskService:
    ACTIVE_STATUSES = ("pending", "executing", "executed")

    class ExecutionError(RuntimeError):
        def __init__(self, message, status_code=400):
            super().__init__(message)
            self.status_code = status_code

    @staticmethod
    def _metrics(customer):
        now = datetime.utcnow()
        entries = sorted(customer.ledger_entries, key=lambda entry: entry.transaction_date or entry.created_at)
        credits = [entry for entry in entries if entry.type == "credit"]
        payments = [entry for entry in entries if entry.type == "payment"]
        balance = LedgerService.get_balance(customer.id)
        overdue = [entry for entry in credits if entry.due_date and entry.due_date < now and balance["outstanding_balance"] > 0]
        delays = []
        for payment in payments:
            if payment.transaction_date:
                due_dates = [entry.due_date for entry in credits if entry.due_date and entry.due_date <= payment.transaction_date]
                if due_dates:
                    delays.append(max(0, (payment.transaction_date - min(due_dates)).days))
        reminders = [event for event in customer.collection_events if event.event_type in {"reminder_sent", "reminder_generated"}]
        successful_reminders = [event for event in reminders if event.sent_at and any(payment.transaction_date and payment.transaction_date >= event.sent_at for payment in payments)]
        partial_payments = []
        running_balance = Decimal("0")
        for entry in entries:
            if entry.type == "credit":
                running_balance += Decimal(str(entry.amount))
            elif entry.type == "payment":
                partial_payments.append(Decimal(str(entry.amount)) < running_balance)
                running_balance -= Decimal(str(entry.amount))
        actions = [event.created_at for event in customer.collection_events if event.event_type in {"reminder_generated", "reminder_sent", "escalation", "manual_followup"}]
        return {
            "outstandingAmount": round(balance["outstanding_balance"], 2),
            "daysOverdue": max(((now - entry.due_date).days for entry in overdue), default=0),
            "averagePaymentDelay": round(sum(delays) / len(delays), 2) if delays else 0,
            "reminderSuccessRate": round(len(successful_reminders) / len(reminders), 2) if reminders else 0,
            "partialPaymentRate": round(sum(partial_payments) / len(partial_payments), 2) if partial_payments else 0,
            "daysSinceLastCollectionAction": min(((now - timestamp).days for timestamp in actions), default=None),
            "reminderCount": len(reminders),
            "paymentCount": len(payments),
        }

    @staticmethod
    def _recommendation(metrics):
        days = metrics["daysOverdue"]
        if metrics["daysSinceLastCollectionAction"] is not None and metrics["daysSinceLastCollectionAction"] <= 3:
            return "WAIT", 0.95, "A collection action happened within the last 3 days; wait for the cooldown period.", 15
        if days >= 30:
            return "ESCALATE", 0.94, "The balance has been overdue for 30 days or more.", 90 + min(days, 30)
        if metrics["partialPaymentRate"] >= 0.5 and metrics["paymentCount"] >= 2:
            return "OFFER_PARTIAL", 0.88, "This customer frequently makes partial payments; offer a smaller payment amount.", 70 + min(days, 20)
        if metrics["reminderSuccessRate"] >= 0.5 and metrics["reminderCount"] > 0:
            return "SEND_REMINDER", 0.86, "Previous reminders have resulted in payments.", 55 + min(days, 20)
        if 0 < days <= 14:
            return "SEND_REMINDER", 0.82, "The balance is recently overdue and should receive a timely reminder.", 50 + days
        return "SEND_REMINDER", 0.65, "The customer has an outstanding balance and no recent collection outcome.", 30 + min(days, 20)

    @staticmethod
    def _priority(score):
        if score >= 90:
            return "critical"
        if score >= 70:
            return "high"
        if score >= 45:
            return "medium"
        return "low"

    @staticmethod
    def evaluate_customer(customer_id, merchant_id="merchant-001"):
        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise LookupError("Customer not found")
        existing = CollectionTask.query.filter(
            CollectionTask.customer_id == customer_id,
            CollectionTask.status.in_(CollectionTaskService.ACTIVE_STATUSES),
        ).order_by(CollectionTask.created_at.desc()).first()
        if existing:
            return existing
        metrics = CollectionTaskService._metrics(customer)
        if metrics["outstandingAmount"] <= 0:
            return None
        action, confidence, reason, score = CollectionTaskService._recommendation(metrics)
        amount = metrics["outstandingAmount"]
        if action == "OFFER_PARTIAL":
            amount = max(1, round(amount * 0.25, 2))
        task = CollectionTask(
            merchant_id=merchant_id,
            customer_id=customer_id,
            ledger_entry_id=next((entry.id for entry in reversed(customer.ledger_entries) if entry.type == "credit"), None),
            action=action,
            priority=CollectionTaskService._priority(score),
            status="pending",
            reason=reason,
            confidence=confidence,
            recommended_amount=amount,
            channel="whatsapp",
            priority_score=score,
            metrics=metrics,
        )
        db.session.add(task)
        db.session.commit()
        return task

    @staticmethod
    def execute(task_id):
        task = db.session.get(CollectionTask, task_id)
        if not task:
            raise CollectionTaskService.ExecutionError("Collection task not found", 404)
        if task.status == "executed":
            raise CollectionTaskService.ExecutionError("Collection task has already been executed", 409)
        if task.status != "pending":
            raise CollectionTaskService.ExecutionError("Collection task must be pending", 409)
        task.status = "executing"
        task.execution_error = None
        task.approved_at = datetime.utcnow()
        db.session.commit()
        try:
            customer = db.session.get(Customer, task.customer_id)
            if not customer:
                raise CollectionTaskService.ExecutionError("Customer not found", 404)
            outstanding = Decimal(str(LedgerService.get_balance(customer.id)["outstanding_balance"]))
            if outstanding <= 0:
                raise CollectionTaskService.ExecutionError("Customer has no outstanding balance", 400)
            accept_partial = task.action == "OFFER_PARTIAL"
            provider_data = RazorpayService.create_payment_link(
                customer=customer,
                amount=outstanding,
                currency="INR",
                accept_partial=accept_partial,
                first_min_partial_amount=Decimal(str(task.recommended_amount)) if accept_partial else None,
                reference_id=task.id,
                notes={"customer_id": task.customer_id, "ledger_entry_id": task.ledger_entry_id, "collection_task_id": task.id},
            )
            link = PaymentLink(
                merchant_id=task.merchant_id,
                customer_id=task.customer_id,
                ledger_entry_id=task.ledger_entry_id,
                amount=outstanding,
                amount_paid=Decimal("0"),
                amount_due=outstanding,
                currency="INR",
                provider="razorpay",
                provider_link_id=provider_data["id"],
                short_url=provider_data["short_url"],
                status="issued",
                expires_at=datetime.utcfromtimestamp(provider_data["expire_by"]) if provider_data.get("expire_by") else None,
            )
            db.session.add(link)
            task.payment_link_id = provider_data["id"]
            task.payment_link_url = provider_data["short_url"]
            task.status = "executed"
            task.executed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            db.session.commit()
            return task
        except CollectionTaskService.ExecutionError as exc:
            db.session.rollback()
            task = db.session.get(CollectionTask, task_id)
            task.status = "failed"
            task.execution_error = str(exc)
            task.updated_at = datetime.utcnow()
            db.session.commit()
            raise
        except Exception as exc:
            db.session.rollback()
            task = db.session.get(CollectionTask, task_id)
            task.status = "failed"
            task.execution_error = str(exc)
            task.updated_at = datetime.utcnow()
            db.session.commit()
            raise CollectionTaskService.ExecutionError("Razorpay payment link creation failed", 502) from exc

    @staticmethod
    def queue(merchant_id="merchant-001"):
        for customer in Customer.query.filter_by(merchant_id=merchant_id).all():
            CollectionTaskService.evaluate_customer(customer.id, merchant_id)
        return CollectionTask.query.filter_by(merchant_id=merchant_id).filter(CollectionTask.status.in_(CollectionTaskService.ACTIVE_STATUSES)).order_by(CollectionTask.priority_score.desc(), CollectionTask.created_at.desc()).all()

    @staticmethod
    def set_status(task_id, status):
        task = db.session.get(CollectionTask, task_id)
        if not task:
            raise LookupError("Collection task not found")
        if status == "rejected" and task.status != "pending":
            raise CollectionTaskService.ExecutionError("Only pending collection tasks can be rejected", 409)
        task.status = status
        if status == "approved":
            task.approved_at = datetime.utcnow()
        if status == "rejected":
            task.rejected_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        db.session.commit()
        return task
