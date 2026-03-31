from fastapi import FastAPI, Request
from payment import activate_plan
import hmac, hashlib

app = FastAPI()

XENDIT_WEBHOOK_TOKEN = "your-xendit-webhook-token"  # dari Xendit dashboard

@app.post("/webhook/xendit")
async def xendit_webhook(request: Request):
    # Verifikasi token
    token = request.headers.get("x-callback-token")
    if token != XENDIT_WEBHOOK_TOKEN:
        return {"status": "unauthorized"}

    body = await request.json()

    if body.get("status") == "PAID":
        external_id = body["external_id"]  # format: email_plan_cycle_timestamp
        parts = external_id.split("_")
        email = parts[0]
        plan = parts[1]
        billing_cycle = parts[2]
        payment_id = body["id"]

        # Cari user_id dari email
        from db import get_supabase
        supabase = get_supabase()
        user = supabase.auth.admin.get_user_by_email(email)
        
        if user:
            activate_plan(user.id, plan, billing_cycle, payment_id)

    return {"status": "ok"}