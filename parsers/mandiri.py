import re
import pandas as pd
import pdfplumber
from datetime import datetime

from core.constants import DEFAULT_YEAR


# ═══════════════════════════════════════════════════
# ══════════  MANDIRI e-Statement  ══════════════════
# ═══════════════════════════════════════════════════

_ES_SKIP = re.compile(
    r"e-Statement|Menara Mandiri|Nama/Name|Cabang/Branch|Tabungan Mandiri|"
    r"Nomor Rekening|Mata Uang|Saldo Awal|Dana Masuk|Dana Keluar|Saldo Akhir|"
    r"No Tanggal|No Date|Mandiri Call|serta merupakan|Bank Mandiri|"
    r"ini adalah batas|Disclaimer|Segala bentuk|Nasabah dapat|Nasabah tunduk|"
    r"Customer.s role|objections regarding|bound by the Livin|official signature|"
    r"All forms of usage|Customers can submit|Customers are subject|"
    r"information discrepancies|Lembaga Penjamin|Otoritas Jasa Keuangan|"
    r"\d+\s+dari\s+\d+|\d+\s+of\s+\d+"
)

_ES_DATE  = re.compile(
    r"^(\d{2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})",
    re.IGNORECASE,
)
_ES_TIME  = re.compile(r"^\d{2}:\d{2}:\d{2}\s+WIB")
_ES_TXN   = re.compile(
    r"^(\d+)\s+(.*?)\s*([+\-][\d.]+,\d{2})\s+([\d.]+,\d{2})\s*$"
)


def _parse_idr(s: str) -> float:
    return float(s.strip().replace(".", "").replace(",", "."))


def _is_junk(line: str) -> bool:
    return not line or line in ("-", "–", "--")


def _dedup_desc(text: str) -> str:
    """Hapus frasa duplikat akibat linearisasi kolom PDF."""
    tokens = text.split()
    if len(tokens) < 2:
        return text
    result, i = [], 0
    while i < len(tokens):
        found = False
        for win in range(min(7, len(tokens) - i), 1, -1):
            chunk = " ".join(tokens[i: i + win])
            if chunk in " ".join(result):
                i += win
                found = True
                break
        if not found:
            result.append(tokens[i])
            i += 1
    return " ".join(result)


def extract_mandiri_mutation(pdf_path: str, password: str = None) -> pd.DataFrame:
    all_lines = []
    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            all_lines.extend((page.extract_text() or "").split("\n"))

    clean = [ln.strip() for ln in all_lines if ln.strip() and not _ES_SKIP.search(ln)]

    txn_pos = [i for i, ln in enumerate(clean) if _ES_TXN.match(ln)]
    rows    = []

    for idx, pos in enumerate(txn_pos):
        m      = _ES_TXN.match(clean[pos])
        mid    = m.group(2).strip()
        amount = _parse_idr(m.group(3))
        saldo  = _parse_idr(m.group(4))

        prev_end   = txn_pos[idx - 1] if idx > 0 else -1
        next_start = txn_pos[idx + 1] if idx + 1 < len(txn_pos) else len(clean)

        before = clean[prev_end + 1: pos]
        after  = clean[pos + 1: next_start]

        # ── Tanggal & deskripsi dari baris sebelum transaksi ──────────────
        date_str, pre_descs = None, []
        last_date_idx = next((bi for bi in range(len(before) - 1, -1, -1) if _ES_DATE.match(before[bi])), -1)

        if last_date_idx >= 0:
            dm       = _ES_DATE.match(before[last_date_idx])
            try:
                date_str = datetime.strptime(dm.group(0), "%d %b %Y").strftime("%d/%m/%Y")
            except Exception:
                date_str = None

            date_suffix = before[last_date_idx][len(dm.group(0)):].strip()

            last_time_before = next(
                (bi for bi in range(last_date_idx - 1, -1, -1) if _ES_TIME.match(before[bi])), -1
            )
            pre_descs = [bl for bl in before[last_time_before + 1: last_date_idx] if not _is_junk(bl)]
            if date_suffix:
                pre_descs.append(date_suffix)

        # ── Deskripsi dari baris sesudah transaksi ────────────────────────
        post_descs, time_seen = [], False
        for bl in after:
            if _ES_DATE.match(bl):
                break
            if _ES_TIME.match(bl):
                time_seen = True
                tail = re.sub(r"^\d{2}:\d{2}:\d{2}\s+WIB\s*", "", bl).strip()
                if tail and not _is_junk(tail):
                    post_descs.append(tail)
                continue
            if time_seen and not _is_junk(bl):
                post_descs.append(bl)

        keterangan = _dedup_desc(" ".join(pre_descs + ([mid] if mid else []) + post_descs).strip())
        keterangan = re.sub(r"\s+", " ", keterangan).strip()

        rows.append({
            "date":    date_str,
            "remarks": keterangan,
            "debit":   abs(amount) if amount < 0 else 0.0,
            "credit":  amount      if amount > 0 else 0.0,
            "balance": saldo,
        })

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════
# ══════════  MANDIRI Rekening Koran  ═══════════════
# ═══════════════════════════════════════════════════

_RK_SKIP = re.compile(
    r"Rekening Koran|Statement of Account|"
    r"Hubungi Kami|Contact Us|mandiricare|bankmandiri|"
    r"Mandiri Call|mandiri call|Livin'poin|"
    r"Ringkasan Akun|At a glance|Summary of Accounts|"
    r"Tabungan / Savings|"
    r"No\. Rekening|Account Number|"
    r"Nama Produk|Product Name|"
    r"Tanggal\s+Tanggal|"
    r"Transaksi Valuta|Transaction\s+Valuta|"
    r"Rincian Transaksi|Transaction Details|"
    r"Debit / Kredit|Debit / Credit|"
    r"Date\s+Date|Mandiri Tabungan|"
    r"Saldo Awal / Previous|Mutasi Kredit|Mutasi Debit|Saldo Akhir / Current|"
    r"Total of Credit|Total of Debit|"
    r"Hal Page \d+|P age|"
    r"Kartu Kredit|Credit Card|Nomor Kartu|Card Number|Pagu Kredit|"
    r"Informasi / Information|Nilai Tukar|Exchange Rate|"
    r"^\s*\*"
)

# DD/MM  DD/MM  <desc>  <amount>  [D]  <balance>
_RK_TXN = re.compile(
    r"^(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(.*?)\s+"
    r"([\d,]+\.\d{2})\s+(D\s+|D$)?([\d,]+\.\d{2})\s*$"
)

_RK_SALDO_AWAL = re.compile(r"^(\d{2}/\d{2})\s+Saldo Awal\s+([\d,]+\.\d{2})\s*$")
_JUNK_LINES    = {"-  -", "-", "–", "--"}


def extract_mandiri_rek_koran(pdf_path: str, password: str = None) -> pd.DataFrame:
    all_lines = []
    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            all_lines.extend((page.extract_text() or "").split("\n"))

    # Ambil tahun dari header periode
    full_text = "\n".join(all_lines)
    year      = DEFAULT_YEAR
    m_year    = re.search(r"Periode / Period:\s*\d{1,2}/\d{2}/(\d{2})\s+s/d", full_text)
    if m_year:
        year = 2000 + int(m_year.group(1))

    rows, current = [], None

    for raw in all_lines:
        line = raw.strip()
        if not line:
            continue

        mt = _RK_TXN.match(line)
        if mt:
            if current:
                rows.append(current)
            day, mon = mt.group(1).split("/")
            current = {
                "date":    f"{day}/{mon}/{year}",
                "remarks": mt.group(3).strip(),
                "debit":   float(mt.group(4).replace(",", "")) if mt.group(5) else 0.0,
                "credit":  float(mt.group(4).replace(",", "")) if not mt.group(5) else 0.0,
                "balance": float(mt.group(6).replace(",", "")),
            }
            continue

        if _RK_SALDO_AWAL.match(line):
            if current:
                rows.append(current)
                current = None
            continue

        if _RK_SKIP.search(line) or line in _JUNK_LINES:
            continue

        if current:
            current["remarks"] = (current["remarks"] + " " + line).strip()

    if current:
        rows.append(current)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["remarks"] = df["remarks"].str.replace(r"\s+", " ", regex=True).str.strip()
    return df
