import streamlit as st
import xendit
import os
from datetime import datetime, timezone, timedelta

def get_xendit_client():
    try:
        api_key = st.secrets["XENDIT_SECRET_KEY"]
    except:
        api_key = os.environ.get("XENDIT_SECRET_KEY")
    xendit.set_api_key(api_key)

def create_invoice(user_email, plan, billing_cycle):
    """Buat invoice Xendit untuk upgrade plan"""
    get_xendit_client()

    from plans import PLANS
    price = PLANS[plan][f"price_{billing_cycle}"]
    duration = "Bulanan" if billing_cycle == "monthly" else "Tahunan"

    invoice = xendit.Invoice.create(
        external_id=f"{user_email}_{plan}_{billing_cycle}_{int(datetime.now().timestamp())}",
        amount=price,
        payer_email=user_email,
        description=f"Mutasi Bank App — Plan {plan.capitalize()} {duration}",
        currency="IDR",
        invoice_duration=86400,  # expired dalam 24 jam
        payment_methods=["QRIS", "BCA", "BNI", "BRI", "MANDIRI", "OVO", "DANA", "CREDIT_CARD"],
        success_redirect_url="https://yourdomain.com/?payment=success",
        failure_redirect_url="https://yourdomain.com/?payment=failed",
    )

    return invoice

def activate_plan(user_id, plan, billing_cycle, payment_id):
    """Aktifkan plan setelah pembayaran berhasil"""
    from db import get_supabase
    supabase = get_supabase()

    now = datetime.now(timezone.utc)
    if billing_cycle == "monthly":
        expires_at = now + timedelta(days=30)
    else:
        expires_at = now + timedelta(days=365)

    supabase.table("subscriptions").update({
        "plan": plan,
        "billing_cycle": billing_cycle,
        "expires_at": expires_at.isoformat(),
        "last_payment_id": payment_id,
        "last_payment_date": now.isoformat(),
        "is_active": True
    }).eq("user_id", user_id).execute()