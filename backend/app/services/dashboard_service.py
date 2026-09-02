from datetime import datetime

from app.extensions import db
from app.models.customer import Customer
from app.models.ledger import LedgerEntry


class DashboardService:
    @staticmethod
    def get_dashboard_metrics(merchant_id=None):
        query = LedgerEntry.query
        if merchant_id:
            query = query.filter_by(merchant_id=merchant_id)

        entries = query.all()
        customers = Customer.query.filter_by(merchant_id=merchant_id).all() if merchant_id else Customer.query.all()

        total_customers = len(customers)
        total_outstanding = sum((entry.amount for entry in entries if entry.type == "credit"), 0)
        total_paid = sum((entry.amount for entry in entries if entry.type == "payment"), 0)
        total_adjustment = sum((entry.amount for entry in entries if entry.type == "adjustment"), 0)

        total_outstanding_balance = total_outstanding - total_paid + total_adjustment
        overdue_amount = 0
        overdue_customer_count = 0
        for customer in customers:
            balance = DashboardService._balance_for_customer(customer.id)
            if balance["customer_status"] == "overdue":
                overdue_customer_count += 1
                overdue_amount += max(balance["outstanding_balance"], 0)

        average_balance = (total_outstanding_balance / total_customers) if total_customers else 0
        return {
            "totalCustomers": total_customers,
            "totalOutstandingBalance": float(total_outstanding_balance),
            "totalCollected": float(total_paid),
            "averageBalance": float(average_balance),
            "overdueAmount": float(overdue_amount),
            "overdueCustomerCount": overdue_customer_count,
            "lastUpdated": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _balance_for_customer(customer_id):
        from app.services.ledger_service import LedgerService
        balance = LedgerService.get_balance(customer_id)
        return balance
