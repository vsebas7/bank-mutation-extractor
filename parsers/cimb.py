import re
import pandas as pd
import pdfplumber
from datetime import datetime


# ── Shared helpers ────────────────────────────────────────────────────────────

def _to_df_clean(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if not df.empty:
        df["remarks"] = df["remarks"].str.replace(r"\s+", " ", regex=True).str.strip()
    return df


# ── CIMB V1 ───────────────────────────────────────────────────────────────────

_V1_TX_RE = re.compile(
    r"^(?P<date>\d{2}\s+[A-Za-z]{3}\s+\d{4})\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<trx>-?[\d,]+\.\d{2})\s+"
    r"(?P<saldo>[\d,]+\.\d{2})$"
)

_V1_SKIP = {
    "LAPORAN REKENING", "STATEMENT OF ACCOUNT",
    "TANGGAL DESKRIPSI", "Saldo Awal",
    "Total Kredit", "Total Debit",
    "Saldo Akhir", "Page ", "alasan",
}

_V1_STOP_REMARKS = {
    "IMPORTANT", "USER ID", "PASSWORD", "OTP",
    "CONFIDENTIAL", "JANGAN MEMBAGIKANNYA", "DON'T SHARE",
}


def extract_cimb_mutation(pdf_path: str, password: str = None) -> pd.DataFrame:
    rows, current = [], None

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for raw in text.split("\n"):
                line = raw.strip()
                if not line:
                    continue
                if any(x in line for x in _V1_SKIP):
                    continue

                m = _V1_TX_RE.match(line)
                if m:
                    if current:
                        rows.append(current)
                    trx   = float(m.group("trx").replace(",", ""))
                    saldo = float(m.group("saldo").replace(",", ""))
                    current = {
                        "date":    datetime.strptime(m.group("date"), "%d %b %Y").strftime("%d/%m/%Y"),
                        "remarks": m.group("desc"),
                        "debit":   abs(trx) if trx < 0 else 0,
                        "credit":  trx if trx > 0 else 0,
                        "balance": saldo,
                    }
                    continue

                if current:
                    if re.fullmatch(r"\d{2}:\d{2}:\d{2}", line):
                        continue
                    if any(x in line.upper() for x in _V1_STOP_REMARKS):
                        continue
                    current["remarks"] += " " + line

    if current:
        rows.append(current)

    return _to_df_clean(rows)


# ── CIMB V2 ───────────────────────────────────────────────────────────────────

_V2_TX_START = re.compile(
    r"^\d+\s+"
    r"(?P<post_date>\d{2}/\d{2}/\d{2})\s+(?P<post_time>\d{2}:\d{2})\s+"
    r"(?P<eff_date>\d{2}/\d{2}/\d{2})\s+(?P<eff_time>\d{2}:\d{2})\s+"
)
_V2_MONEY    = re.compile(r"[\d,]+\.\d{2}")
_V2_CHEQUE   = re.compile(r"\b\d{6,}\b")

_V2_STOP_LINES = {
    "TOTAL DEBIT", "TOTAL CREDIT", "ACCOUNT NUMBER",
    "ACCOUNT NAME", "PERIOD", "CURRENCY",
}


def _v2_remark_priority(remark: str) -> int:
    r = remark.upper()
    if "CREDIT INTEREST" in r:
        return 1
    if "WITHHOLDING TAX" in r:
        return 3
    return 2


def extract_cimb_v2_mutation(pdf_path: str, password: str = None) -> pd.DataFrame:
    rows, current = [], None

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for raw in text.split("\n"):
                line = raw.strip()
                if not line:
                    continue

                m = _V2_TX_START.match(line)
                if m:
                    if current:
                        rows.append(current)

                    money   = _V2_MONEY.findall(line)
                    debit   = float(money[-3].replace(",", "")) if len(money) >= 3 else 0.0
                    credit  = float(money[-2].replace(",", "")) if len(money) >= 2 else 0.0
                    balance = float(money[-1].replace(",", "")) if len(money) >= 1 else None

                    desc = _V2_TX_START.sub("", line)
                    desc = _V2_MONEY.sub("", desc)
                    desc = _V2_CHEQUE.sub("", desc)
                    desc = re.sub(r"\s+", " ", desc).strip()

                    dt = datetime.strptime(
                        f"{m.group('post_date')} {m.group('post_time')}", "%m/%d/%y %H:%M"
                    )
                    current = {
                        "date":     dt.strftime("%d/%m/%Y"),
                        "datetime": dt,
                        "remarks":  desc,
                        "debit":    debit,
                        "credit":   credit,
                        "balance":  balance,
                    }
                    continue

                if current:
                    if any(x in line.upper() for x in _V2_STOP_LINES):
                        continue
                    clean = _V2_CHEQUE.sub("", line)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    current["remarks"] += " " + clean

    if current:
        rows.append(current)

    df = _to_df_clean(rows)
    if df.empty:
        return df

    df["priority"] = df["remarks"].apply(_v2_remark_priority)
    df = (
        df.sort_values(["datetime", "priority"], ascending=[True, True])
        .reset_index(drop=True)
        .drop(columns=["datetime", "priority"])
    )
    return df


# ── CIMB V3 ───────────────────────────────────────────────────────────────────

_V3_TX_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<sign>[+-])\s*"
    r"(?P<amount>[\d,]+\.\d{2})\s+"
    r"(?P<balance>[\d,]+\.\d{2})$"
)

_V3_SKIP = {
    "DATE TRANSACTION DESCRIPTION", "BEGINING BALANCE", "ENDING BALANCE",
    "TOTAL CREDIT", "TOTAL DEBIT", "IMPORTANT!",
    "ACCOUNT NUMBER", "TYPE OF PRODUCT", "CURRENCY", "NAME :",
}


def extract_cimb_v3_mutation(pdf_path: str, password: str = None) -> pd.DataFrame:
    rows, current = [], None

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for raw in text.split("\n"):
                line = raw.strip()
                if not line:
                    continue
                if any(x in line.upper() for x in _V3_SKIP):
                    continue

                m = _V3_TX_RE.match(line)
                if m:
                    if current:
                        rows.append(current)
                    amount  = float(m.group("amount").replace(",", ""))
                    balance = float(m.group("balance").replace(",", ""))
                    current = {
                        "date":    datetime.strptime(m.group("date"), "%Y-%m-%d").strftime("%d/%m/%Y"),
                        "remarks": m.group("desc").strip(),
                        "debit":   amount if m.group("sign") == "-" else 0.0,
                        "credit":  amount if m.group("sign") == "+" else 0.0,
                        "balance": balance,
                    }
                    continue

                if current:
                    current["remarks"] += " " + line

    if current:
        rows.append(current)

    df = _to_df_clean(rows)
    if df.empty:
        return df

    df["__date"] = pd.to_datetime(df["date"], format="%d/%m/%Y")
    df = df.sort_values("__date").drop(columns="__date").reset_index(drop=True)
    return df
