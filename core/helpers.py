import pandas as pd
import pdfplumber
import re
from datetime import datetime

def month_key(df):
    dt = pd.to_datetime(df["date"], format="%d/%m/%Y")
    return dt.dt.strftime("%Y-%m").iloc[0]

def extract_account_number(pdf_path,password):
    """
    Ambil nomor rekening dari halaman pertama PDF.
    Fallback ke '' kalau tidak ketemu.
    """
    patterns = [
        r"NO\.?\s*REKENING\s*[:\-]?\s*(\d+)",
        r"NO\s*REK\s*[:\-]?\s*(\d+)",
        r"ACCOUNT\s*NUMBER\s*[:\-]?\s*(\d+)",
        # Mandiri Rekening Koran: "108-00-9700631-7"
        r"(\d{3}-\d{2}-\d{7}-\d)",
        # Mandiri e-Statement: "Nomor Rekening/Account Number : 1080097006317"
        r"Nomor Rekening/Account Number\s*:\s*(\d+)",
    ]

    with pdfplumber.open(pdf_path,password=password) as pdf:
        # Cek halaman 1 dan 2 (Rekening Koran menyimpan nomor rek di halaman 2-3)
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