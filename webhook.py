from fastapi import FastAPI, Request, HTTPException
from datetime import datetime, timezone, timedelta
from supabase import create_client
import hashlib
import os

app = FastAPI()


# ── Supabase (service role key) ───────────────────────────────────────────────
def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    return create_client(url, key)


# ── Durasi plan ───────────────────────────────────────────────────────────────
PLAN_DURATION = {
    "monthly": timedelta(days=30),
    "annual":  timedelta(days=365),
}


def verify_midtrans_signature(order_id: str, status_code: str, gross_amount: str, server_key: str, signature: str) -> bool:
    raw    = f"{order_id}{status_code}{gross_amount}{server_key}"
    hashed = hashlib.sha512(raw.encode()).hexdigest()
    return hashed == signature


def activate_plan(user_id: str, plan: str, billing_cycle: str, amount: int):
    supabase   = get_supabase()
    duration   = PLAN_DURATION[billing_cycle]
    expires_at = datetime.now(timezone.utc) + duration
    now        = datetime.now(timezone.utc).isoformat()

    existing = supabase.table("subscriptions")\
        .select("*")\
        .eq("user_id", user_id)\
        .execute()

    if existing.data:
        current_expires = existing.data[0].get("expires_at")
        if current_expires:
            current_dt = datetime.fromisoformat(current_expires.replace("Z", "+00:00"))
            if current_dt > datetime.now(timezone.utc):
                expires_at = current_dt + duration

        current_revenue = existing.data[0].get("total_revenue", 0) or 0

        supabase.table("subscriptions").update({
            "plan":          plan,
            "billing_cycle": billing_cycle,
            "expires_at":    expires_at.isoformat(),
            "is_active":     True,
            "total_revenue": current_revenue + amount,
            "updated_at":    now,
        }).eq("user_id", user_id).execute()
    else:
        supabase.table("subscriptions").insert({
            "user_id":       user_id,
            "plan":          plan,
            "billing_cycle": billing_cycle,
            "expires_at":    expires_at.isoformat(),
            "is_active":     True,
            "total_revenue": amount,
            "updated_at":    now,
        }).execute()


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/webhook/midtrans")
async def midtrans_webhook(request: Request):
    body = await request.json()

    transaction_status = body.get("transaction_status")
    fraud_status       = body.get("fraud_status")
    order_id           = body.get("order_id", "")
    gross_amount       = body.get("gross_amount", "0")
    signature_key      = body.get("signature_key", "")
    status_code        = body.get("status_code", "")

    # ── 1. Verifikasi signature ───────────────────────────────────────────────
    server_key = os.environ.get("MIDTRANS_SERVER_KEY", "")
    if not verify_midtrans_signature(order_id, status_code, gross_amount, server_key, signature_key):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # ── 2. Cek status pembayaran ──────────────────────────────────────────────
    is_paid = (
        transaction_status == "settlement"
        or (transaction_status == "capture" and fraud_status == "accept")
    )

    if not is_paid:
        return {"message": "ignored", "status": transaction_status}

    # ── 3. Cari invoice di Supabase berdasarkan order_id ─────────────────────
    supabase = get_supabase()
    invoice  = supabase.table("invoices")\
        .select("*")\
        .eq("order_id", order_id)\
        .execute()

    if not invoice.data:
        raise HTTPException(status_code=404, detail=f"Invoice tidak ditemukan: {order_id}")

    inv           = invoice.data[0]
    user_id       = inv["user_id"]
    plan          = inv["plan"]
    billing_cycle = inv["billing_cycle"]
    amount        = inv["amount"]

    # ── 4. Aktifkan plan ──────────────────────────────────────────────────────
    activate_plan(user_id, plan, billing_cycle, amount)

    # ── 5. Update status invoice ──────────────────────────────────────────────
    supabase.table("invoices").update({
        "status": "paid"
    }).eq("order_id", order_id).execute()

    return {
        "message": "subscription updated",
        "user_id": user_id,
        "plan":    plan,
        "cycle":   billing_cycle,
    }
