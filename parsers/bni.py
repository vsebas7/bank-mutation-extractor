import re
import pandas as pd
import pdfplumber
from datetime import datetime

_DATE_LINE  = re.compile(r"^(?P<date>\d{2}\s+[A-Za-z]{3}\s+\d{4})\s+(?P<title>.+)")
_MONEY_LINE = re.compile(r"^(?P<amount>[+-]?[\d,]+)\s+(?P<balance>[\d,]+)")
_TIME_LINE  = re.compile(r"^(?P<time>\d{2}:\d{2}:\d{2})\s+WIB\s+(?P<desc>.+)")

_SKIP = {
    "LAPORAN MUTASI", "PERIODE", "SALDO AWAL", "SALDO AKHIR", "TOTAL",
    "BANK NEGARA INDONESIA", "INFORMASI LAINNYA", "PESERTA PENJAMINAN",
    "PAGE", "HALAMAN",
}


def extract_bni_mutation(pdf_path: str, password: str = None) -> pd.DataFrame:
    rows  = []
    buf   = {}

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for raw in text.split("\n"):
                line = raw.strip()
                if not line:
                    continue
                if any(s in line.upper() for s in _SKIP):
                    continue

                m1 = _DATE_LINE.match(line)
                if m1:
                    buf = {
                        "date":  datetime.strptime(m1.group("date"), "%d %b %Y").strftime("%d/%m/%Y"),
                        "title": m1.group("title"),
                    }
                    continue

                m2 = _MONEY_LINE.match(line)
                if m2 and buf:
                    amt_raw = m2.group("amount")
                    amount  = float(amt_raw.replace(",", "").replace("+", ""))
                    buf["debit"]   = abs(amount) if amt_raw.startswith("-") else 0.0
                    buf["credit"]  = amount if not amt_raw.startswith("-") else 0.0
                    buf["balance"] = float(m2.group("balance").replace(",", ""))
                    continue

                m3 = _TIME_LINE.match(line)
                if m3 and buf:
                    rows.append({
                        "date":    buf["date"],
                        "remarks": f"{buf['title']} {m3.group('desc')}".strip(),
                        "debit":   buf.get("debit",   0.0),
                        "credit":  buf.get("credit",  0.0),
                        "balance": buf.get("balance"),
                    })
                    buf = {}

    df = pd.DataFrame(rows)
    if not df.empty:
        df["remarks"] = df["remarks"].str.replace(r"\s+", " ", regex=True).str.strip()
    return df
