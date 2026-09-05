import os
from decimal import Decimal

import razorpay


class RazorpayService:
    @staticmethod
    def _client():
        key_id = os.getenv("RAZORPAY_KEY_ID")
        key_secret = os.getenv("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            raise RuntimeError("Razorpay credentials are not configured")
        return razorpay.Client(auth=(key_id, key_secret))

    @staticmethod
    def create_payment_link(customer, amount: Decimal, currency: str, accept_partial=False, first_min_partial_amount=None):
        payload = {
            "amount": int(amount * 100) if currency == "INR" else int(amount),
            "currency": currency,
            "description": f"Udhaar payment for {customer.name}",
            "customer": {"name": customer.name, "contact": customer.phone, "email": customer.email},
            "accept_partial": accept_partial,
        }
        if accept_partial and first_min_partial_amount is not None:
            payload["first_min_partial_amount"] = int(Decimal(str(first_min_partial_amount)) * 100)
        return RazorpayService._client().payment_link.create(payload)

    @staticmethod
    def fetch_payment_link(provider_link_id):
        return RazorpayService._client().payment_link.fetch(provider_link_id)

    @staticmethod
    def cancel_payment_link(provider_link_id):
        return RazorpayService._client().payment_link.cancel(provider_link_id)