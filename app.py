import tempfile
from io import BytesIO

import pandas as pd
import pdfplumber
import streamlit as st

from services.auth    import login_page, logout, restore_session_from_cookie
from services.db      import get_plans, get_subscription, is_subscription_active
from services.upgrade import show_upgrade_page
from core.helpers     import month_key, extract_account_number

from core.constants import DEFAULT_YEAR, BANK_DISPLAY_NAME
from core.detector  import detect_bank
from parsers        import PARSER_REGISTRY

st.set_page_config(page_title="Mutasi Bank PDF", layout="wide")

# ═══════════════════════════════════════════════════
# RESTORE SESSION dari cookie (sebelum auth gate)
# ═══════════════════════════════════════════════════

restore_session_from_cookie()

# ═══════════════════════════════════════════════════
# AUTH GATE
# ═══════════════════════════════════════════════════

if "user" not in st.session_state:
    login_page()
    st.stop()

PLANS  = get_plans()
sub    = get_subscription()
plan   = sub["plan"] if is_subscription_active() else "free"
limits = PLANS[plan]


# ═══════════════════════════════════════════════════
# URL ROUTING via query_params
# ═══════════════════════════════════════════════════

PAGES = {
    "konversi": "🏦 Konversi Mutasi",
    "upgrade":  "⬆️ Upgrade Plan",
}

DEFAULT_PAGE = "konversi"


def get_current_page() -> str:
    page = st.query_params.get("page", DEFAULT_PAGE)
    return page if page in PAGES else DEFAULT_PAGE


def set_page(page_key: str):
    st.query_params["page"] = page_key
    st.rerun()


# ═══════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════

def _open_pdf_or_stop(path: str, password: str, filename: str):
    try:
        with pdfplumber.open(path, password=password) as pdf:
            _ = pdf.pages[0]
    except Exception:
        st.error(f"❌ Tidak bisa membuka **{filename}**. Pastikan passwordnya sudah benar.")
        st.stop()


def _validate_single_bank(banks: list[str]):
    unique = set(banks)
    if len(unique) > 1:
        st.warning(
            f"⚠️ Terdeteksi lebih dari 1 bank: **{', '.join(b.upper() for b in unique)}**. "
            "Harap upload PDF dari bank yang sama saja."
        )
        st.stop()


def _validate_single_year(years: list[int]):
    unique = set(years)
    if len(unique) > 1:
        st.warning(
            f"⚠️ Terdeteksi transaksi dari tahun berbeda: "
            f"**{', '.join(str(y) for y in sorted(unique))}**. "
            "Harap upload PDF dari tahun yang sama saja."
        )
        st.stop()


def _build_excel(data_by_month: dict) -> BytesIO:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for month, dfs in sorted(data_by_month.items()):
            pd.concat(dfs, ignore_index=True).to_excel(writer, sheet_name=month, index=False)
    output.seek(0)
    return output


def _make_filename(name_input: str, bank: str, account: str, year: int) -> str:
    if name_input.strip():
        name = name_input.strip()
        return name if name.lower().endswith(".xlsx") else name + ".xlsx"
    bank_label = BANK_DISPLAY_NAME.get(bank, bank) or "BANK"
    acc_label  = account or ""
    return f"Mutasi {bank_label} {acc_label} {year}.xlsx"


# ═══════════════════════════════════════════════════
# MAIN PAGE
# ═══════════════════════════════════════════════════

def show_main_page():
    st.title("🏦 Mutasi Bank PDF → Excel (Auto Detect)")

    year         = st.number_input("Tahun Mutasi", value=DEFAULT_YEAR)
    excel_name   = st.text_input("Nama file Excel (opsional)", placeholder="Contoh: Mutasi Januari 2025")
    pdf_password = st.text_input("Password PDF (kosongkan jika tidak ada)", type="password")
    uploaded_files = st.file_uploader("Upload PDF Mutasi", type="pdf", accept_multiple_files=True)

    if not uploaded_files:
        return

    data_by_month          = {}
    detected_bank          = None
    detected_account       = None
    banks_in_session: list = []
    years_in_session: list = []

    with st.spinner("🔍 Parsing semua PDF..."):
        for uploaded in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded.read())
                path = tmp.name

            _open_pdf_or_stop(path, pdf_password, uploaded.name)

            bank       = detect_bank(path, pdf_password)
            account_no = extract_account_number(path, pdf_password)

            if detected_bank is None:
                detected_bank    = bank
                detected_account = account_no

            bank_base = BANK_DISPLAY_NAME.get(bank, (bank or "").lower())
            banks_in_session.append(bank_base)
            _validate_single_bank(banks_in_session)

            parser = PARSER_REGISTRY.get(bank)
            if parser is None:
                st.warning(f"⚠️ Bank tidak dikenali: {uploaded.name}")
                continue

            df_temp = parser(path, pdf_password, year=year)

            if df_temp is not None and not df_temp.empty and "date" in df_temp.columns:
                file_years = pd.to_datetime(df_temp["date"], dayfirst=True).dt.year.unique().tolist()
                years_in_session.extend(file_years)
                _validate_single_year(years_in_session)

            if df_temp is None or df_temp.empty or "date" not in df_temp.columns:
                st.warning(f"⚠️ Tidak ada transaksi valid: {uploaded.name}")
                continue

            data_by_month.setdefault(month_key(df_temp), []).append(df_temp)

    if not data_by_month:
        st.error("❌ Tidak ada transaksi yang berhasil di-extract.")
        return

    output     = _build_excel(data_by_month)
    filename   = _make_filename(excel_name, detected_bank, detected_account, year)
    bank_label = BANK_DISPLAY_NAME.get(detected_bank, detected_bank)

    st.success(f"✅ Excel berhasil dibuat → {bank_label}")
    st.info("🔒 File Anda tidak disimpan di server kami.")
    st.download_button(
        "⬇️ Download Excel (per bulan)",
        output,
        filename,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ═══════════════════════════════════════════════════
# SIDEBAR + ROUTING
# ═══════════════════════════════════════════════════

current_page = get_current_page()

with st.sidebar:
    st.write(f"👤 {st.session_state['user'].email}")
    st.write(f"📦 Plan: **{plan.capitalize()}**")
    st.divider()

    for key, label in PAGES.items():
        if st.button(label, use_container_width=True, type="primary" if key == current_page else "secondary"):
            set_page(key)

    st.divider()
    if st.button("Logout", use_container_width=True):
        logout()

# ═══════════════════════════════════════════════════
# RENDER PAGE
# ═══════════════════════════════════════════════════

if current_page == "konversi":
    show_main_page()
elif current_page == "upgrade":
    show_upgrade_page()