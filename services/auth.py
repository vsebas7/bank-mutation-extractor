import streamlit as st
from supabase import create_client
import extra_streamlit_components as stx

COOKIE_NAME    = "sb_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 hari

cookie_manager = stx.CookieManager()


def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def restore_session_from_cookie():
    """
    Coba restore session dari cookie saat session_state kosong.
    Dipanggil di awal app.py sebelum auth gate.
    """
    if "user" in st.session_state:
        return

    token = cookie_manager.get(COOKIE_NAME)
    if not token:
        return

    try:
        supabase = get_supabase()
        res = supabase.auth.get_user(token)
        if res and res.user:
            st.session_state["user"]  = res.user
            st.session_state["token"] = token
    except Exception:
        cookie_manager.delete(COOKIE_NAME)


def login_page():
    st.title("🏦 Mutasi Bank App")
    st.subheader("Login")

    email    = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Login", use_container_width=True):
            try:
                supabase = get_supabase()
                res = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password,
                })
                st.session_state["user"]  = res.user
                st.session_state["token"] = res.session.access_token

                cookie_manager.set(
                    COOKIE_NAME,
                    res.session.access_token,
                    max_age=COOKIE_MAX_AGE,
                )
                st.rerun()
            except Exception:
                st.error("Login failed. Check your email/password.")

    with col2:
        if st.button("Register", use_container_width=True):
            try:
                supabase = get_supabase()
                supabase.auth.sign_up({"email": email, "password": password})
                st.success("Check your email to confirm your account!")
            except Exception as e:
                st.error(f"Registration failed: {e}")


def logout():
    cookie_manager.delete(COOKIE_NAME)
    supabase = get_supabase()
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()