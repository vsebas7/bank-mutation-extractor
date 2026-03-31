import os
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

    # Cek apakah ada token reset password di query params
    params = st.query_params
    if "type" in params and params["type"] == "recovery":
        _reset_password_page()
        return

    tab_login, tab_register, tab_forgot = st.tabs(["Login", "Register", "Forgot Password"])

    # ── Login ─────────────────────────────────────────────────────────────────
    with tab_login:
        email    = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

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

    # ── Register ──────────────────────────────────────────────────────────────
    with tab_register:
        reg_email    = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        reg_confirm  = st.text_input("Konfirmasi Password", type="password", key="reg_confirm")

        if st.button("Register", use_container_width=True):
            if reg_password != reg_confirm:
                st.error("Password tidak sama.")
            elif len(reg_password) < 6:
                st.error("Password minimal 6 karakter.")
            else:
                try:
                    supabase = get_supabase()
                    supabase.auth.sign_up({
                        "email":    reg_email,
                        "password": reg_password,
                    })
                    st.success("Registrasi berhasil! Cek email kamu untuk konfirmasi akun.")
                except Exception as e:
                    st.error(f"Registrasi gagal: {e}")

    # ── Forgot Password ───────────────────────────────────────────────────────
    with tab_forgot:
        forgot_email = st.text_input("Email", key="forgot_email")

        if st.button("Kirim Link Reset Password", use_container_width=True):
            if not forgot_email:
                st.error("Masukkan email kamu.")
            else:
                try:
                    supabase = get_supabase()
                    supabase.auth.reset_password_email(
                        forgot_email,
                        options={
                            "redirect_to": "https://bank-mutation-extractor.streamlit.app"
                        }
                    )
                    st.success("Link reset password sudah dikirim ke email kamu!")
                except Exception as e:
                    st.error(f"Gagal kirim email: {e}")


def _reset_password_page():
    """Halaman set password baru setelah klik link dari email."""
    st.subheader("🔑 Set Password Baru")

    new_password     = st.text_input("Password Baru", type="password", key="new_password")
    confirm_password = st.text_input("Konfirmasi Password", type="password", key="confirm_password")

    if st.button("Update Password", use_container_width=True):
        if new_password != confirm_password:
            st.error("Password tidak sama.")
        elif len(new_password) < 6:
            st.error("Password minimal 6 karakter.")
        else:
            try:
                supabase = get_supabase()
                supabase.auth.update_user({"password": new_password})
                st.success("Password berhasil diupdate! Silakan login.")
                # Hapus query params recovery
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
