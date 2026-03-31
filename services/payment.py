import os
import time
import midtransclient
import streamlit as st


def get_midtrans_client():
    server_key = os.environ.get("MIDTRANS_SERVER_KEY") or st.secrets.get("MIDTRANS_SERVER_KEY")
    is_production = os.environ.get("MIDTRANS_ENV", "sandbox") == "production"

    return midtransclient.Snap(
        is_production=is_production,
        server_key=server_key,
    )


PLAN_PRICE = {
    ("pro",        "monthly"): 99000,
    ("pro",        "annual"):  990000,
    ("enterprise", "monthly"): 299000,
    ("enterprise", "annual"):  2990000,
}


def create_invoice(user_email: str, plan: str, billing_cycle: str) -> dict:

    snap = get_midtrans_client()

    amount      = PLAN_PRICE.get((plan.lower(), billing_cycle.lower()))
    external_id = f"{user_email}_{plan}_{billing_cycle}_{int(time.time())}"

    param = {
        "transaction_details": {
            "order_id":     external_id,
            "gross_amount": amount,
        },
        "customer_details": {
            "email": user_email,
        },
        "enabled_payments": [
            "gopay",
            "shopeepay",
            "qris",
            "bca_va",
            "bni_va",
            "bri_va",
            "mandiri_bill",
            "credit_card",
        ],
        "item_details": [
            {
                "id":       f"{plan}_{billing_cycle}",
                "price":    amount,
                "quantity": 1,
                "name":     f"Plan {plan.capitalize()} - {billing_cycle.capitalize()}",
            }
        ],
    }

    transaction = snap.create_transaction(param)

    return {
        "invoice_url": transaction["redirect_url"],
        "snap_token":  transaction["token"],
        "order_id":    external_id,
    }
