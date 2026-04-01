import pandas as pd
import pdfplumber
import re
from datetime import datetime


def month_key(df):
    # dayfirst=True tanpa hardcode format — robust untuk berbagai format tanggal
    dt = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    valid = dt.dropna()
    if valid.empty:
        return "UNKNOWN"
    return valid.dt.strftime("%Y-%m").iloc[0]


def detect_pdf_year(pdf_path: str, password: str = "") -> int | None:
    
    _YEAR_RE = re.compile(r"\b(20\d{2})\b")
    with pdfplumber.open(pdf_path, password=password) as pdf:
        text = ""
        for page in pdf.pages[:3]:
            t = page.extract_text()
            if t:
                text += t
    years = _YEAR_RE.findall(text)
    if not years:
        return None
        
    from collections import Counter
    return int(Counter(years).most_common(1)[0][0])


def extract_account_number(pdf_path, password):
    
    patterns = [
        r"NO\.?\s*REKENING\s*[:\-]?\s*(\d+)",
        r"NO\s*REK\s*[:\-]?\s*(\d+)",
        r"ACCOUNT\s*NUMBER\s*[:\-]?\s*(\d+)",
        # Mandiri Rekening Koran: "108-00-9700631-7"
        r"(\d{3}-\d{2}-\d{7}-\d)",
        # Mandiri e-Statement: "Nomor Rekening/Account Number : 1080097006317"
        r"Nomor Rekening/Account Number\s*:\s*(\d+)",
    ]
    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages[:3]:
            text = page.extract_text()
            if not text:
                continue
            for p in patterns:
                found = re.search(p, text, re.IGNORECASE)
                if found:
                    return found.group(1).replace("-", "")
    return ""


def to_float(v):
    return float(v.replace(".", "").replace(",", "."))


ID_MONTH_MAP = {
    "JAN": "JAN", "FEB": "FEB", "MAR": "MAR", "APR": "APR",
    "MEI": "MAY", "JUN": "JUN", "JUL": "JUL", "AGU": "AUG",
    "SEP": "SEP", "OKT": "OCT", "NOV": "NOV", "DES": "DEC",
}


def normalize_month(text: str) -> str:
    for k, v in ID_MONTH_MAP.items():
        text = re.sub(rf"\b{k}\b", v, text, flags=re.IGNORECASE)
    return text
