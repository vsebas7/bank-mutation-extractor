import re
import pandas as pd
import pdfplumber
from datetime import datetime

_TX_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<desc>.+?)\s+\S+\s+"
    r"(?P<debit>[\d,]+\.\d{2})\s+"
    r"(?P<credit>[\d,]+\.\d{2})\s+"
    r"(?P<balance>[\d,]+\.\d{2})$"
)


def extract_bri_mutation(pdf_path: str, password: str = None) -> pd.DataFrame:
    rows = []

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                line = line.strip()
                m = _TX_RE.match(line)
                if not m:
                    continue
                rows.append({
                    "date":    datetime.strptime(m.group("date"), "%d/%m/%y").strftime("%d/%m/%Y"),
                    "remarks": m.group("desc"),
                    "debit":   float(m.group("debit").replace(",", "")),
                    "credit":  float(m.group("credit").replace(",", "")),
                    "balance": float(m.group("balance").replace(",", "")),
                })

    return pd.DataFrame(rows)
