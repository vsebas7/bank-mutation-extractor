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

    # ── Cek apakah ini halaman reset password ────────────────────────────────
    params = st.query_params
    if params.get("type") == "recovery" and "access_token" in params:
        _reset_password_page(params["access_token"])
        return

    # ── Cek apakah sedang di halaman forgot password ─────────────────────────
    if st.session_state.get("show_forgot"):
        _forgot_password_page()
        return

    # ── Login page utama ──────────────────────────────────────────────────────
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
                st.error("Login gagal. Periksa email dan password kamu.")

    with col2:
        if st.button("Register", use_container_width=True):
            try:
                supabase = get_supabase()
                supabase.auth.sign_up({"email": email, "password": password})
                st.success("Registrasi berhasil! Cek email kamu untuk konfirmasi akun.")
            except Exception as e:
                st.error(f"Registrasi gagal: {e}")

    # Link lupa password
    st.write("")
    if st.button("Lupa password?", type="tertiary"):
        st.session_state["show_forgot"] = True
        st.rerun()


def _forgot_password_page():
    st.subheader("🔑 Lupa Password")

    forgot_email = st.text_input("Masukkan email kamu")

    if st.button("Kirim Link Reset Password", use_container_width=True):
        if not forgot_email:
            st.error("Masukkan email kamu.")
        else:
            try:
                supabase = get_supabase()
                supabase.auth.reset_password_email(
                    forgot_email,
                    options={
                        "redirect_to": "https://bank-mutation-extractor-production.up.railway.app/reset-password"
                    }
                )
                st.success("Link reset password sudah dikirim! Cek email kamu.")
            except Exception as e:
                st.error(f"Gagal kirim email: {e}")

    st.write("")
    if st.button("← Kembali ke Login", type="tertiary"):
        st.session_state["show_forgot"] = False
        st.rerun()


def _reset_password_page(access_token: str):
    st.subheader("🔑 Set Password Baru")

    new_password     = st.text_input("Password Baru", type="password")
    confirm_password = st.text_input("Konfirmasi Password", type="password")

    if st.button("Update Password", use_container_width=True):
        if new_password != confirm_password:
            st.error("Password tidak sama.")
        elif len(new_password) < 6:
            st.error("Password minimal 6 karakter.")
        else:
            try:
                supabase = get_supabase()
                # Set session dulu dengan access token dari link
                supabase.auth.set_session(access_token, access_token)
                supabase.auth.update_user({"password": new_password})
                st.success("Password berhasil diupdate! Silakan login.")
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal update password: {e}")


def logout():
    cookie_manager.delete(COOKIE_NAME)
    supabase = get_supabase()
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()
