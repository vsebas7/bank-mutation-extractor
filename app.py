import tempfile
from io import BytesIO
from datetime import date

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


def _show_subscription_banner(sub: dict, plan: str):
    """Show subscription days remaining as a banner in the sidebar."""
    if plan == "free":
        return

    end_date = sub.get("end_date")
    if not end_date:
        return

    # end_date dari Supabase timestamptz — bisa string ISO dengan timezone atau datetime object
    if isinstance(end_date, str):
        # Contoh: "2025-04-01T00:00:00+07:00" atau "2025-04-01T00:00:00Z"
        from datetime import datetime, timezone
        end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00")).astimezone(timezone.utc).date()
    elif hasattr(end_date, "date"):
        end_date = end_date.date()

    days_left = (end_date - date.today()).days

    if days_left <= 0:
        st.sidebar.error("⚠️ Subscription Anda sudah habis!")
    elif days_left <= 7:
        st.sidebar.warning(f"⏳ Subscription habis dalam **{days_left} hari** ({end_date.strftime('%d %b %Y')})")
    else:
        st.sidebar.info(f"✅ Aktif hingga **{end_date.strftime('%d %b %Y')}** ({days_left} hari lagi)")


def _show_summary_stats(all_dfs: list[pd.DataFrame]):
    """Show summary statistics from all parsed dataframes."""
    combined = pd.concat(all_dfs, ignore_index=True)

    total_rows = len(combined)

    # Cari kolom debit/kredit secara fleksibel (nama kolom bisa beda tiap bank)
    debit_col  = next((c for c in combined.columns if "debit"  in c.lower()), None)
    kredit_col = next((c for c in combined.columns if "kredit" in c.lower() or "credit" in c.lower()), None)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📄 Total Transaksi", f"{total_rows:,}")

    if debit_col:
        total_debit = pd.to_numeric(combined[debit_col], errors="coerce").sum()
        col2.metric("🔴 Total Debit", f"Rp {total_debit:,.0f}")

    if kredit_col:
        total_kredit = pd.to_numeric(combined[kredit_col], errors="coerce").sum()
        col3.metric("🟢 Total Kredit", f"Rp {total_kredit:,.0f}")

    if debit_col and kredit_col:
        net = total_kredit - total_debit
        delta_color = "normal" if net >= 0 else "inverse"
        col4.metric("💰 Net (Kredit - Debit)", f"Rp {net:,.0f}", delta_color=delta_color)


def _show_preview_table(data_by_month: dict):
    """Show a preview of the first month's data."""
    first_month = sorted(data_by_month.keys())[0]
    first_df    = pd.concat(data_by_month[first_month], ignore_index=True)

    with st.expander(f"🔍 Preview Data — {first_month} (5 baris pertama)", expanded=True):
        st.dataframe(first_df.head(5), use_container_width=True)
        st.caption(f"Total {len(first_df)} baris di sheet **{first_month}**")


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
    all_dfs: list          = []

    total_files = len(uploaded_files)

    # Progress bar
    progress_bar   = st.progress(0, text="⏳ Memulai proses...")
    status_text    = st.empty()

    for idx, uploaded in enumerate(uploaded_files):
        progress_pct  = int((idx / total_files) * 100)
        progress_bar.progress(progress_pct, text=f"📄 Memproses: **{uploaded.name}** ({idx + 1}/{total_files})")
        status_text.caption(f"File {idx + 1} dari {total_files}: `{uploaded.name}`")

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
        all_dfs.append(df_temp)

    # Progress selesai
    progress_bar.progress(100, text="✅ Semua file selesai diproses!")
    status_text.empty()

    if not data_by_month:
        st.error("❌ Tidak ada transaksi yang berhasil di-extract.")
        return

    # ── Summary stats ──────────────────────────────
    st.divider()
    st.subheader("📊 Ringkasan Transaksi")
    _show_summary_stats(all_dfs)

    # ── Preview tabel ──────────────────────────────
    _show_preview_table(data_by_month)

    # ── Build & download Excel ─────────────────────
    output     = _build_excel(data_by_month)
    filename   = _make_filename(excel_name, detected_bank, detected_account, year)
    bank_label = BANK_DISPLAY_NAME.get(detected_bank, detected_bank)

    st.divider()
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

    # ── Subscription days remaining ────────────────
    _show_subscription_banner(sub, plan)

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
