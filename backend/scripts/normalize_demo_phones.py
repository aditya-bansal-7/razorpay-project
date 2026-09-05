import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models.customer import Customer

def normalize_phones():
    app = create_app()
    with app.app_context():
        # Find only customers created by the demo seed (those matching the old phone pattern)
        demo_customers = Customer.query.filter(Customer.phone.like("+91-555-%")).all()
        
        changed = 0
        samples = []
        
        for customer in demo_customers:
            # Old format: +91-555-1000083
            # Extract the last part which is 1000000 + i
            try:
                suffix = customer.phone.split("-")[-1]
                i = int(suffix) - 1000000
                new_phone = f"90000{10000 + i}"
                
                # Check for duplicates before assigning
                if Customer.query.filter_by(phone=new_phone).first():
                    continue
                
                customer.phone = new_phone
                changed += 1
                if len(samples) < 5:
                    samples.append(new_phone[:2] + "****" + new_phone[-4:])
            except Exception as e:
                print(f"Failed to process {customer.phone}: {e}")
                
        db.session.commit()
        
        print(f"Demo customer phone numbers changed: {changed}")
        print(f"Sample masked numbers: {samples}")
        
        # Verify exactly 10 digits
        updated_customers = Customer.query.filter(Customer.phone.like("90000100%")).all()
        all_valid = all(len(c.phone) == 10 and c.phone.isdigit() for c in updated_customers)
        print(f"Verified all demo numbers are exactly 10 digits: {all_valid}")
        
        # Verify no duplicate demo phone numbers exist
        phones = [c.phone for c in updated_customers]
        unique_phones = set(phones)
        print(f"Verified no duplicate demo phone numbers exist: {len(phones) == len(unique_phones)}")

if __name__ == "__main__":
    normalize_phones()
