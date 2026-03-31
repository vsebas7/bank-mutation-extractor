"""
webhook.py — FastAPI server untuk terima webhook dari Lynk.
Jalankan terpisah dari Streamlit:
    uvicorn webhook:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, Request, HTTPException
from datetime import datetime, timezone, timedelta
from supabase import create_client
import os

app = FastAPI()

# ── Supabase (pakai service role key, bukan anon key) ─────────────────────────
def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")  # service role, bukan anon!
    return create_client(url, key)


# ── Durasi plan ───────────────────────────────────────────────────────────────
PLAN_DURATION = {
    "monthly": timedelta(days=30),
    "annual":  timedelta(days=365),
}

# ── Mapping nominal → (plan, billing_cycle) ───────────────────────────────────
# Sesuaikan dengan harga yang kamu set di Lynk dashboard
AMOUNT_TO_PLAN = {
    99000:  ("pro",        "monthly"),
    990000: ("pro",        "annual"),
    299000:  ("enterprise", "monthly"),
    2990000: ("enterprise", "annual"),
}


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/webhook/lynk")
async def lynk_webhook(request: Request):
    payload = await request.json()

    # ── 1. Parse payload dari Lynk ────────────────────────────────────────────
    status = payload.get("status", "").lower()
    amount = int(payload.get("amount", 0))
    notes  = payload.get("notes", "").strip().lower()  # email yang diisi user saat bayar

    # Hanya proses kalau status PAID
    if status != "paid":
        return {"message": "ignored", "status": status}

    if not notes:
        raise HTTPException(status_code=400, detail="notes (email) kosong")

    # ── 2. Cari user berdasarkan email ────────────────────────────────────────
    supabase = get_supabase()

    try:
        auth_result = supabase.auth.admin.list_users()
        user = next((u for u in auth_result if u.email.lower() == notes), None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal fetch users: {e}")

    if not user:
        raise HTTPException(status_code=404, detail=f"User tidak ditemukan: {notes}")

    user_id = user.id

    # ── 3. Tentukan plan dari nominal ─────────────────────────────────────────
    plan_info = AMOUNT_TO_PLAN.get(amount)
    if not plan_info:
        raise HTTPException(status_code=400, detail=f"Nominal tidak dikenali: {amount}")

    plan_name, billing_cycle = plan_info
    duration   = PLAN_DURATION[billing_cycle]
    expires_at = datetime.now(timezone.utc) + duration

    # ── 4. Update subscription di Supabase ───────────────────────────────────
    existing = supabase.table("subscriptions")\
        .select("*")\
        .eq("user_id", user_id)\
        .execute()

    now = datetime.now(timezone.utc).isoformat()

    if existing.data:
        # Kalau masih aktif, perpanjang dari expires_at yang ada (tidak di-reset)
        current_expires = existing.data[0].get("expires_at")
        if current_expires:
            current_dt = datetime.fromisoformat(current_expires.replace("Z", "+00:00"))
            if current_dt > datetime.now(timezone.utc):
                expires_at = current_dt + duration

        current_revenue = existing.data[0].get("total_revenue", 0) or 0

        supabase.table("subscriptions").update({
            "plan":          plan_name,
            "billing_cycle": billing_cycle,
            "expires_at":    expires_at.isoformat(),
            "is_active":     True,
            "total_revenue": current_revenue + amount,
            "updated_at":    now,
        }).eq("user_id", user_id).execute()
    else:
        supabase.table("subscriptions").insert({
            "user_id":       user_id,
            "plan":          plan_name,
            "billing_cycle": billing_cycle,
            "expires_at":    expires_at.isoformat(),
            "is_active":     True,
            "total_revenue": amount,
            "updated_at":    now,
        }).execute()

    return {
        "message": "subscription updated",
        "user_id": user_id,
        "plan":    plan_name,
        "cycle":   billing_cycle,
        "expires": expires_at.isoformat(),
    }
