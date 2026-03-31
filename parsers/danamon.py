import re
import pandas as pd
import pdfplumber
from datetime import datetime

from core.constants import DEFAULT_YEAR

_DATE_V2  = re.compile(r"^\d{2}\s+[A-Za-z]{3,}\s+\d{4}")
_DATE_V1  = re.compile(r"^\d{2}/\d{2}")
_MONEY    = re.compile(r"-?[\d\.]+,\d{2}")

_SKIP = {
    "TABUNGAN DANAMON", "ACCOUNT SUMMARY", "RINGKASAN",
    "TANGGAL TRANSAKSI", "TRANSACTION DATE",
    "TOTAL", "PERINGATAN", "DO NOT SHARE", "_",
}

_MONTH_MAP = {
    "JANUARI": "Jan", "FEBRUARI": "Feb", "MARET": "Mar",
    "APRIL":   "Apr", "MEI":      "May", "JUNI":  "Jun",
    "JULI":    "Jul", "AGUSTUS":  "Aug", "SEPTEMBER": "Sep",
    "OKTOBER": "Oct", "NOVEMBER": "Nov", "DESEMBER":  "Dec",
}


def _normalize_month(text: str) -> str:
    for id_month, en_month in _MONTH_MAP.items():
        text = re.sub(id_month, en_month, text, flags=re.IGNORECASE)
    return text


def _to_float(v: str) -> float:
    return float(v.replace(".", "").replace(",", "."))


def extract_danamon_mutation(pdf_path: str, password: str = None, default_year: int = DEFAULT_YEAR) -> pd.DataFrame:
    rows, current = [], None

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in [l.strip() for l in text.split("\n") if l.strip()]:
                if any(x in line.upper() for x in _SKIP):
                    continue

                # Format V2: DD Mon YYYY
                if _DATE_V2.match(line):
                    if current:
                        rows.append(current)

                    norm = _normalize_month(line)
                    date = datetime.strptime(
                        _DATE_V2.match(norm).group(), "%d %b %Y"
                    ).strftime("%d/%m/%Y")

                    desc  = _DATE_V2.sub("", norm)
                    money = _MONEY.findall(norm)
                    debit = credit = balance = 0.0

                    if len(money) >= 2:
                        amt = money[-2]
                        bal = money[-1]
                        if amt.startswith("-"):
                            debit = abs(_to_float(amt))
                        else:
                            credit = _to_float(amt)
                        balance = _to_float(bal)
                        desc = _MONEY.sub("", desc)

                    current = {
                        "date":    date,
                        "remarks": re.sub(r"\s+", " ", desc).strip(),
                        "debit":   debit,
                        "credit":  credit,
                        "balance": balance,
                    }
                    continue

                # Lanjutan amount untuk V2 yang belum terisi
                if current and _MONEY.search(line) and current["balance"] == 0:
                    parts = _MONEY.findall(line)
                    if len(parts) >= 2:
                        amt = parts[-2]
                        bal = parts[-1]
                        if amt.startswith("-"):
                            current["debit"] = abs(_to_float(amt))
                        else:
                            current["credit"] = _to_float(amt)
                        current["balance"] = _to_float(bal)
                    continue

                # Format V1: DD/MM
                if _DATE_V1.match(line):
                    parts = _MONEY.findall(line)
                    if len(parts) < 2:
                        continue

                    amt = parts[-2]
                    bal = parts[-1]
                    debit = credit = 0.0
                    if amt.startswith("-"):
                        debit = abs(_to_float(amt))
                    else:
                        credit = _to_float(amt)

                    desc = re.sub(r"^\d{2}/\d{2}\s*", "", line[5:])
                    desc = _MONEY.sub("", desc)
                    desc = re.sub(r"\s+", " ", desc).strip()

                    rows.append({
                        "date":    datetime.strptime(f"{line[:5]}/{default_year}", "%d/%m/%Y").strftime("%d/%m/%Y"),
                        "remarks": desc,
                        "debit":   debit,
                        "credit":  credit,
                        "balance": _to_float(bal),
                    })
                    continue

                if current:
                    current["remarks"] += " " + line

    if current:
        rows.append(current)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["remarks"] = df["remarks"].str.replace(r"\s+", " ", regex=True).str.strip()
    return df
