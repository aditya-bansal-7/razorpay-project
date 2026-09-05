import os
import sys
import random
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models.customer import Customer
from app.models.ledger import LedgerEntry
from app.models.collection_event import CollectionEvent
from app.models.collection_task import CollectionTask
from app.services.merchant_service import MerchantService

# Configuration
TOTAL_CUSTOMERS = 150
MERCHANT_ID = "merchant-001"
SEED_VALUE = 42

FIRST_NAMES = [
    "Rahul", "Amit", "Sneha", "Priya", "Rohan", "Ananya", "Aditya", "Kavya", "Vikram", "Pooja",
    "Arjun", "Riya", "Karan", "Neha", "Varun", "Shreya", "Siddharth", "Meera", "Kunal", "Nisha",
    "Raj", "Simran", "Aarav", "Zara", "Dev", "Isha", "Karthik", "Roshni", "Sameer", "Tanvi",
    "Vivek", "Preeti", "Sanjay", "Anjali", "Tarun", "Kirti", "Gaurav", "Divya", "Nitin", "Shruti"
]

LAST_NAMES = [
    "Sharma", "Gupta", "Patel", "Singh", "Kumar", "Joshi", "Desai", "Shah", "Reddy", "Rao",
    "Iyer", "Menon", "Nair", "Verma", "Agarwal", "Yadav", "Das", "Banerjee", "Bose", "Chatterjee",
    "Chauhan", "Bhatia", "Mehta", "Srivastava", "Mishra", "Pandey", "Ghosh", "Sen", "Bhattacharya", "Sengupta",
    "Ahuja", "Chopra", "Kapur", "Malhotra", "Suri", "Trivedi", "Upadhyay", "Tiwari", "Shukla", "Bajpai"
]

def get_amount():
    """Generate a realistic random amount based on given distribution."""
    r = random.random()
    if r < 0.20:
        return random.randint(5, 50) * 100.0  # 500 - 5000
    elif r < 0.50:
        return random.randint(50, 150) * 100.0 # 5000 - 15000
    elif r < 0.80:
        return random.randint(150, 300) * 100.0 # 15000 - 30000
    elif r < 0.95:
        return random.randint(300, 750) * 100.0 # 30000 - 75000
    else:
        return random.randint(750, 1500) * 100.0 # 75000 - 150000

def create_credit(customer_id, amount, due_date):
    return LedgerEntry(
        merchant_id=MERCHANT_ID,
        customer_id=customer_id,
        type="credit",
        amount=amount,
        description="Demo Invoice",
        transaction_date=due_date - timedelta(days=random.randint(15, 30)),
        due_date=due_date
    )

def create_payment(customer_id, amount, date):
    return LedgerEntry(
        merchant_id=MERCHANT_ID,
        customer_id=customer_id,
        type="payment",
        amount=amount,
        description="Payment Received",
        transaction_date=date,
        due_date=None
    )

def create_reminder(customer_id, ledger_id, date):
    return CollectionEvent(
        merchant_id=MERCHANT_ID,
        customer_id=customer_id,
        ledger_entry_id=ledger_id,
        event_type="reminder_sent",
        channel="whatsapp",
        status="sent",
        sent_at=date,
        created_at=date,
        updated_at=date
    )
    
def create_task(customer_id, action, date):
    return CollectionTask(
        merchant_id=MERCHANT_ID,
        customer_id=customer_id,
        action=action,
        priority="medium",
        status="executed",
        reason="Demo history",
        confidence=0.8,
        recommended_amount=0,
        channel="whatsapp",
        priority_score=50,
        metrics={},
        created_at=date,
        executed_at=date,
        updated_at=date
    )

def seed_demo_data():
    app = create_app()
    with app.app_context():
        MerchantService.ensure_default_merchant()
        random.seed(SEED_VALUE)
        
        now = datetime.utcnow()
        
        # Tracking
        stats = {
            "created": 0,
            "existed": 0,
            "ledgers_created": 0,
            "payments_created": 0,
            "events_created": 0,
            "total_outstanding": 0.0,
            "total_paid": 0.0,
            "overdue_count": 0,
            "overdue_amount": 0.0,
            "best_candidates": []
        }
        
        # Check total existing records safely without printing everything
        initial_customer_count = Customer.query.count()
        print(f"Initial customers in DB: {initial_customer_count}")
        
        profiles = (
            ["reliable"] * 30 +
            ["reminder_responsive"] * 22 +
            ["partial_payment"] * 22 +
            ["moderately_late"] * 23 +
            ["resistant"] * 22 +
            ["severely_overdue"] * 15 +
            ["low_urgency"] * 16
        )
        random.shuffle(profiles)
        
        for i in range(TOTAL_CUSTOMERS):
            profile = profiles[i]
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            
            # Deterministic demo fields
            # Generate exactly 10 digits, e.g. 9000010000
            phone = f"90000{10000 + i}"
            email = f"{first_name.lower()}.{last_name.lower()}.{i}@demo.local"
            name = f"{first_name} {last_name}"
            
            # Idempotency check
            existing = Customer.query.filter_by(merchant_id=MERCHANT_ID, phone=phone).first()
            if existing:
                stats["existed"] += 1
                continue
                
            customer = Customer(
                merchant_id=MERCHANT_ID,
                name=name,
                phone=phone,
                email=email
            )
            db.session.add(customer)
            db.session.flush() # get ID
            stats["created"] += 1
            
            amount = get_amount()
            outstanding = amount
            
            credit_due_date = None
            is_overdue = False
            scenario_hint = ""
            
            if profile == "reliable":
                # Paid in full before/on due date
                credit_due_date = now - timedelta(days=random.randint(5, 45))
                credit = create_credit(customer.id, amount, credit_due_date)
                db.session.add(credit)
                db.session.flush()
                stats["ledgers_created"] += 1
                
                pay_date = credit_due_date - timedelta(days=random.randint(0, 5))
                pay = create_payment(customer.id, amount, pay_date)
                db.session.add(pay)
                stats["payments_created"] += 1
                stats["total_paid"] += amount
                outstanding = 0.0
                
            elif profile == "reminder_responsive":
                # Paid full after a reminder
                credit_due_date = now - timedelta(days=random.randint(20, 60))
                credit = create_credit(customer.id, amount, credit_due_date)
                db.session.add(credit)
                db.session.flush()
                stats["ledgers_created"] += 1
                
                rem_date = credit_due_date + timedelta(days=random.randint(3, 7))
                rem = create_reminder(customer.id, credit.id, rem_date)
                db.session.add(rem)
                stats["events_created"] += 1
                
                pay_date = rem_date + timedelta(days=random.randint(1, 3))
                pay = create_payment(customer.id, amount, pay_date)
                db.session.add(pay)
                stats["payments_created"] += 1
                stats["total_paid"] += amount
                outstanding = 0.0
                
            elif profile == "partial_payment":
                # Multiple partial payments, owes some amount
                credit_due_date = now - timedelta(days=random.randint(30, 60))
                credit = create_credit(customer.id, amount, credit_due_date)
                db.session.add(credit)
                db.session.flush()
                stats["ledgers_created"] += 1
                
                # First reminder -> payment
                rem_date_1 = credit_due_date + timedelta(days=5)
                rem1 = create_reminder(customer.id, credit.id, rem_date_1)
                db.session.add(rem1)
                
                p1_amt = round(amount * 0.4, 2)
                p1 = create_payment(customer.id, p1_amt, rem_date_1 + timedelta(days=2))
                db.session.add(p1)
                
                # Second reminder -> payment
                rem_date_2 = rem_date_1 + timedelta(days=15)
                rem2 = create_reminder(customer.id, credit.id, rem_date_2)
                db.session.add(rem2)
                
                p2_amt = round(amount * 0.3, 2)
                p2 = create_payment(customer.id, p2_amt, rem_date_2 + timedelta(days=2))
                db.session.add(p2)
                
                # Cooldown check (ensure last action > 3 days ago for most, except a few)
                last_contact = rem_date_2
                if random.random() < 0.2:
                    # Recently contacted -> WAIT scenario
                    recent = now - timedelta(days=random.randint(1, 2))
                    rem3 = create_reminder(customer.id, credit.id, recent)
                    db.session.add(rem3)
                    task = create_task(customer.id, "SEND_REMINDER", recent)
                    db.session.add(task)
                    last_contact = recent
                    scenario_hint = "WAIT (Cooldown)"
                else:
                    scenario_hint = "OFFER_PARTIAL"
                    
                stats["events_created"] += 2
                stats["payments_created"] += 2
                
                paid = p1_amt + p2_amt
                stats["total_paid"] += paid
                outstanding = amount - paid
                is_overdue = True
                
            elif profile == "moderately_late":
                # 8-15 days late, no payments, 1-2 reminders
                credit_due_date = now - timedelta(days=random.randint(8, 15))
                credit = create_credit(customer.id, amount, credit_due_date)
                db.session.add(credit)
                db.session.flush()
                stats["ledgers_created"] += 1
                
                rem_date = credit_due_date + timedelta(days=3)
                rem = create_reminder(customer.id, credit.id, rem_date)
                db.session.add(rem)
                stats["events_created"] += 1
                
                outstanding = amount
                is_overdue = True
                scenario_hint = "SEND_REMINDER"
                
            elif profile == "resistant":
                # 30-45 days late, no payments, 3-4 reminders
                credit_due_date = now - timedelta(days=random.randint(30, 45))
                credit = create_credit(customer.id, amount, credit_due_date)
                db.session.add(credit)
                db.session.flush()
                stats["ledgers_created"] += 1
                
                last_rem = None
                for d in [5, 15, 25]:
                    rem_date = credit_due_date + timedelta(days=d)
                    rem = create_reminder(customer.id, credit.id, rem_date)
                    db.session.add(rem)
                    last_rem = rem_date
                    stats["events_created"] += 1
                
                if random.random() < 0.3:
                    # Recently contacted -> WAIT scenario
                    recent = now - timedelta(days=random.randint(1, 2))
                    rem = create_reminder(customer.id, credit.id, recent)
                    db.session.add(rem)
                    task = create_task(customer.id, "SEND_REMINDER", recent)
                    db.session.add(task)
                    stats["events_created"] += 1
                    scenario_hint = "WAIT (Cooldown)"
                else:
                    scenario_hint = "ESCALATE / SEND_REMINDER"
                    
                outstanding = amount
                is_overdue = True
                
            elif profile == "severely_overdue":
                # 60-90+ days late, no payments, 5+ reminders
                credit_due_date = now - timedelta(days=random.randint(60, 95))
                credit = create_credit(customer.id, amount, credit_due_date)
                db.session.add(credit)
                db.session.flush()
                stats["ledgers_created"] += 1
                
                for d in [5, 15, 30, 45, 55]:
                    rem_date = credit_due_date + timedelta(days=d)
                    rem = create_reminder(customer.id, credit.id, rem_date)
                    db.session.add(rem)
                    stats["events_created"] += 1
                    
                outstanding = amount
                is_overdue = True
                scenario_hint = "ESCALATE"
                
            elif profile == "low_urgency":
                # Small amount, maybe not due yet or barely overdue
                amount = random.randint(5, 20) * 100.0
                credit_due_date = now + timedelta(days=random.randint(-2, 10))
                credit = create_credit(customer.id, amount, credit_due_date)
                db.session.add(credit)
                db.session.flush()
                stats["ledgers_created"] += 1
                
                outstanding = amount
                is_overdue = credit_due_date < now
                scenario_hint = "WAIT / LOW_URGENCY"

            stats["total_outstanding"] += outstanding
            if is_overdue and outstanding > 0:
                stats["overdue_count"] += 1
                stats["overdue_amount"] += outstanding
                
            # Collect best candidates for the video
            if scenario_hint and outstanding > 0:
                if len(stats["best_candidates"]) < 15:
                    if scenario_hint not in [c["hint"] for c in stats["best_candidates"]] or random.random() < 0.2:
                        days_ov = (now - credit_due_date).days if credit_due_date else 0
                        stats["best_candidates"].append({
                            "id": customer.id,
                            "name": name,
                            "outstanding": outstanding,
                            "daysOverdue": max(0, days_ov),
                            "hint": scenario_hint,
                            "profile": profile
                        })
                        
        db.session.commit()
        
        final_customer_count = Customer.query.count()
        
        print("\n=== SEED RESULTS ===")
        print(f"Script Location      : backend/scripts/seed_demo_data.py")
        print(f"Total Initial        : {initial_customer_count}")
        print(f"Demo Records Created : {stats['created']}")
        print(f"Already Existed      : {stats['existed']}")
        print(f"Total Final Customers: {final_customer_count}")
        print("-" * 30)
        print(f"Ledger Credits       : {stats['ledgers_created']}")
        print(f"Payments             : {stats['payments_created']}")
        print(f"Collection Events    : {stats['events_created']}")
        print("-" * 30)
        print(f"Total Outstanding    : Rs. {stats['total_outstanding']:,.2f}")
        print(f"Total Paid           : Rs. {stats['total_paid']:,.2f}")
        print(f"Overdue Customers    : {stats['overdue_count']}")
        print(f"Overdue Amount       : Rs. {stats['overdue_amount']:,.2f}")
        print("=" * 30)
        
        print("\n=== 10-15 BEST CANDIDATES FOR VIDEO DEMO ===")
        print(f"{'Customer ID':<22} | {'Name':<20} | {'Outstanding':<12} | {'Days Overdue':<12} | {'Scenario Hint'}")
        print("-" * 90)
        for c in stats["best_candidates"][:15]:
            print(f"{c['id']:<22} | {c['name']:<20} | Rs. {c['outstanding']:<11,.0f} | {c['daysOverdue']:<12} | {c['hint']}")

if __name__ == "__main__":
    seed_demo_data()
