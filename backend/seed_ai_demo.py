"""Development seed script to create a reproducible demo customer for AI Strategist testing."""

from datetime import datetime, timedelta
from app import create_app
from app.extensions import db
from app.models.customer import Customer
from app.models.ledger import LedgerEntry
from app.models.collection_event import CollectionEvent
from app.services.merchant_service import MerchantService
from app.services.collection_task_service import CollectionTaskService

def seed_demo_customer():
    app = create_app()
    with app.app_context():
        # Ensure default merchant exists
        MerchantService.ensure_default_merchant()
        merchant_id = "merchant-001"
        
        customer_name = "Gemini Demo Customer"
        
        # Check if exists and reset
        customer = Customer.query.filter_by(name=customer_name).first()
        if customer:
            print(f"Customer '{customer_name}' already exists. Resetting state...")
            LedgerEntry.query.filter_by(customer_id=customer.id).delete()
            CollectionEvent.query.filter_by(customer_id=customer.id).delete()
            db.session.delete(customer)
            db.session.commit()
            
        print(f"Creating '{customer_name}'...")
        customer = Customer(
            merchant_id=merchant_id,
            name=customer_name,
            phone="9000000000",
            email="gemini.demo@example.com"
        )
        db.session.add(customer)
        db.session.commit()
        
        now = datetime.utcnow()
        
        # Outstanding balance: 15,000, Overdue: ~45 days
        credit_due_date = now - timedelta(days=45)
        # Assuming the transaction happened some days before the due date (e.g. 15 days net terms)
        credit_transaction_date = credit_due_date - timedelta(days=15)
        
        credit = LedgerEntry(
            merchant_id=merchant_id,
            customer_id=customer.id,
            type="credit",
            amount=15000.00,
            description="Software Licensing - Yearly Plan",
            transaction_date=credit_transaction_date,
            due_date=credit_due_date
        )
        db.session.add(credit)
        db.session.commit()
        
        # Several previous reminder events (e.g., sent at 40 days ago, 25 days ago, and 5 days ago)
        # This gives a low reminder success rate (since there are no payments)
        # and ensures it's past the 3-day cooldown.
        reminders = [
            now - timedelta(days=40),
            now - timedelta(days=25),
            now - timedelta(days=5),
        ]
        
        for idx, reminder_date in enumerate(reminders):
            event = CollectionEvent(
                merchant_id=merchant_id,
                customer_id=customer.id,
                ledger_entry_id=credit.id,
                event_type="reminder_sent",
                channel="email",
                status="sent",
                sent_at=reminder_date,
                created_at=reminder_date,
                updated_at=reminder_date
            )
            db.session.add(event)
            
        db.session.commit()
        
        print("\n--- Seed Completed Successfully ---")
        print(f"Customer Name : {customer.name}")
        print(f"Customer ID   : {customer.id}")
        
        # Calculate and print metrics
        metrics = CollectionTaskService._metrics(customer)
        print("\n--- Extracted Metrics ---")
        for key, value in metrics.items():
            print(f"  {key}: {value}")
            
        print("\nReady for AI evaluation!")
        print("Run the following curl command to test the pipeline:\n")
        print(f"curl -X POST http://localhost:5000/api/ai/collection-strategy \\")
        print("     -H \"Content-Type: application/json\" \\")
        print(f"     -d '{{\"customerId\": \"{customer.id}\"}}'\n")

if __name__ == "__main__":
    seed_demo_customer()
