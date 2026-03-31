from supabase import create_client
import streamlit as st
import os
import pandas as pd

def get_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
    client = create_client(url, key)
    
    # ✅ Inject user's auth token so RLS knows who is inserting
    if "token" in st.session_state:
        client.postgrest.auth(st.session_state["token"])
    
    return client

def get_subscription():
    """Get current user's subscription, create free one if doesn't exist"""
    supabase = get_supabase()
    user_id = st.session_state["user"].id

    result = supabase.table("subscriptions")\
        .select("*")\
        .eq("user_id", user_id)\
        .execute()

    # If no subscription found, create a free one
    if not result.data:
        supabase.table("subscriptions").insert({
            "user_id": user_id,
            "plan": "free",
            "billing_cycle": None,
            "expires_at": None
        }).execute()

        # Fetch again after insert
        result = supabase.table("subscriptions")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()

    return result.data[0]

def is_subscription_active():
    """Check if user's subscription is still valid"""
    from datetime import datetime, timezone
    sub = get_subscription()

    if sub["plan"] == "free":
        return True  # free never expires

    if not sub["expires_at"]:
        return False

    expires = datetime.fromisoformat(sub["expires_at"].replace("Z", "+00:00"))
    return datetime.now(timezone.utc) < expires

@st.cache_data(ttl=60)  # ✅ cache 1 menit, tidak perlu hit DB tiap rerun
def get_plans():
    """Fetch semua plans dari database"""
    supabase = get_supabase()
    result = supabase.table("plans")\
        .select("*")\
        .eq("is_active", True)\
        .execute()
    
    # Convert ke dict dengan name sebagai key, sama seperti PLANS sebelumnya
    return {p["name"]: p for p in result.data}