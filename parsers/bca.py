import re
import pandas as pd
import pdfplumber
from datetime import datetime

# ── Regex ─────────────────────────────────────────────────────────────────────
_DATE_RE        = re.compile(r"^(\d{2}/\d{2})\s+(.*)")
_AMOUNT_RE      = re.compile(r"([\d,]+\.\d{2})")
_SALDO_AWAL_RE  = re.compile(r"SALDO AWAL\s+([\d,]+\.\d{2})")
_TX_AMOUNT_RE   = re.compile(r"([\d,]+\.\d{2})\s+(?:DB|CR)\b")
_BUNGA_RE       = re.compile(r"\b(BUNGA|PAJAK BUNGA)\b\s+([\d,]+\.\d{2})")
_SETORAN_RE     = re.compile(r"\bSETORAN\b.*\b(CDM|TUNAI|PEMINDAHAN)\b", re.IGNORECASE)
_KOREKSI_RE     = re.compile(r"\b(KR|DR)\s+KOREKSI\s+BUNGA\b", re.IGNORECASE)
_KR_RE          = re.compile(r"\bKR\b", re.IGNORECASE)

_METADATA_KEYWORDS = [
    "REKENING TAHAPAN", "KCP ", "KCU ", "NO. REKENING", "PERIODE",
    "MATA UANG", "CATATAN", "HALAMAN", "TANGGAL KETERANGAN", "RT", "KEL "
    "RT ", "KEC ", "JL ", "PEKANBARU", "INDONESIA", "Apabila ",
    "Rekening ", "•", "telah ",
]

_STOP_PHRASES = [
    "Bersambung ke halaman berikut",
    "SALDO AWAL :", "SALDO AKHIR :",
    "MUTASI CR :", "MUTASI DB :",
]

_SKIP_LINES = {"SALDO AKHIR", "MUTASI CR", "MUTASI DB"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_tx_amount(line: str) -> float:
    m = _TX_AMOUNT_RE.search(line)
    if m:
        return float(m.group(1).replace(",", ""))
    amounts = _AMOUNT_RE.findall(line)
    return float(amounts[0].replace(",", "")) if amounts else 0.0


def _clean_remarks(text: str) -> str:
    for s in _STOP_PHRASES + _METADATA_KEYWORDS:
        if s in text:
            text = text.split(s)[0]
    return re.sub(r"\s+", " ", text).strip()


def _fmt_date(d: str, year: int) -> str:
    return datetime.strptime(f"{d}/{year}", "%d/%m/%Y").strftime("%d/%m/%Y")


def _new_tx(date: str, remarks: str, debit: float, credit: float, balance=None) -> dict:
    return {"date": date, "remarks": remarks, "debit": debit, "credit": credit, "balance": balance}


# ── Main extractor ────────────────────────────────────────────────────────────

def extract_bca_mutation(pdf_path: str, year: int, password: str = None) -> pd.DataFrame:
    rows, current, last_date = [], None, None
    saldo_awal = 0.0

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for raw in text.split("\n"):
                line = raw.strip()
                if not line:
                    continue
                if any(x in line for x in _SKIP_LINES):
                    continue

                # Koreksi bunga
                if _KOREKSI_RE.search(line) and last_date:
                    if current:
                        rows.append(current)
                    amount = _extract_tx_amount(line)
                    current = _new_tx(
                        _fmt_date(last_date, year),
                        "KOREKSI BUNGA",
                        amount if "DR" in line else 0,
                        amount if "KR" in line else 0,
                    )
                    continue

                # Bunga / pajak bunga
                if _BUNGA_RE.search(line) and last_date:
                    if current:
                        rows.append(current)
                    label, amt = _BUNGA_RE.search(line).groups()
                    amount = float(amt.replace(",", ""))
                    current = _new_tx(
                        _fmt_date(last_date, year),
                        label,
                        amount if label == "PAJAK BUNGA" else 0,
                        amount if label == "BUNGA" else 0,
                    )
                    continue

                # Baris dengan tanggal
                m = _DATE_RE.match(line)
                if m:
                    if current:
                        rows.append(current)
                    last_date = m.group(1)

                    sa = _SALDO_AWAL_RE.search(line)
                    if sa:
                        saldo_awal = float(sa.group(1).replace(",", ""))
                        current = _new_tx(_fmt_date(last_date, year), "SALDO AWAL", 0.0, 0.0, saldo_awal)
                        continue

                    desc   = _clean_remarks(m.group(2))
                    amount = _extract_tx_amount(line)
                    is_credit = " CR" in line or bool(_SETORAN_RE.search(line)) or bool(_KR_RE.search(line))
                    is_debit  = " DB" in line
                    current = _new_tx(
                        _fmt_date(last_date, year),
                        desc,
                        amount if is_debit  else 0,
                        amount if is_credit else 0,
                    )
                    continue

                # Baris lanjutan keterangan
                if current:
                    current["remarks"] += " " + _clean_remarks(line)

    if current:
        rows.append(current)

    df      = pd.DataFrame(rows)
    balance = saldo_awal
    balances = []

    for _, r in df.iterrows():
        if r["remarks"] == "SALDO AWAL":
            balances.append(round(balance, 2))
            continue
        balance += r["credit"] - r["debit"]
        balances.append(round(balance, 2))

    df["balance"] = balances
    return df
