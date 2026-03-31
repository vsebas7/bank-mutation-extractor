import os
import time
import hashlib
import midtransclient
import streamlit as st
from supabase import create_client
from services.db import get_plans


def get_midtrans_client():
    server_key    = os.environ.get("MIDTRANS_SERVER_KEY") or st.secrets.get("MIDTRANS_SERVER_KEY")
    is_production = os.environ.get("MIDTRANS_ENV", "sandbox") == "production"
    return midtransclient.Snap(
        is_production=is_production,
        server_key=server_key,
    )


def get_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
    client = create_client(url, key)
    if "token" in st.session_state:
        client.postgrest.auth(st.session_state["token"])
    return client

def create_invoice(user_email: str, plan: str, billing_cycle: str) -> dict:
    PLANS  = get_plans()
    plan_data = PLANS.get(plan.lower())
    amount = int(
        plan_data["price_annual"] if billing_cycle == "annual" 
        else plan_data["price_monthly"]
    )
    snap   = get_midtrans_client()

    # Order ID pendek: 8 char hash email + plan + cycle + timestamp
    email_hash  = hashlib.md5(user_email.encode()).hexdigest()[:8]
    order_id    = f"{email_hash}_{plan[:3]}_{billing_cycle[:3]}_{int(time.time())}"

    param = {
        "transaction_details": {
            "order_id":     order_id,
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

    # Simpan order_id → user ke Supabase
    supabase = get_supabase()
    user_id  = st.session_state["user"].id

    supabase.table("invoices").insert({
        "order_id":     order_id,
        "user_id":      user_id,
        "plan":         plan,
        "billing_cycle": billing_cycle,
        "amount":       amount,
        "status":       "pending",
    }).execute()

    return {
        "invoice_url": transaction["redirect_url"],
        "snap_token":  transaction["token"],
        "order_id":    order_id,
    }
