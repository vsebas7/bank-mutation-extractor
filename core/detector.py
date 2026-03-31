import re
import pdfplumber


def detect_bank(pdf_path: str, pdf_password: str = None) -> str | None:
    """
    Baca halaman pertama PDF dan kembalikan kode bank yang terdeteksi,
    atau None jika tidak dikenali.
    """
    with pdfplumber.open(pdf_path, password=pdf_password) as pdf:
        text = pdf.pages[0].extract_text()
        if not text:
            return None

    t = text.upper()

    # Mandiri Rekening Koran harus dicek SEBELUM Mandiri biasa
    if "REKENING KORAN" in t and "STATEMENT OF ACCOUNT" in t and "MANDIRICARE" in t:
        return "MANDIRI_RK"

    checks = [
        ("MANDIRI",  lambda t: "MENARA MANDIRI" in t or "TABUNGAN NOW" in t or "MANDIRI CALL" in t),
        ("BNI",      lambda t: "BANK NEGARA INDONESIA" in t and "LAPORAN MUTASI REKENING" in t),
        ("BCA",      lambda t: "REKENING TAHAPAN" in t or "BCA" in t),
        ("BRI",      lambda t: "BANK BRI" in t or "BRIMO" in t or "STATEMENT OF FINANCIAL TRANSACTION" in t),
        ("CIMB_V2",  lambda t: "POST DATE" in t and "EFF DATE" in t),
        ("CIMB_V3",  lambda t: bool(re.search(r"\d{4}-\d{2}-\d{2}", t)) and "TRANSACTION AMOUNT BALANCE" in t),
        ("CIMB",     lambda t: "STATEMENT OF ACCOUNT" in t),
        ("DANAMON",  lambda t: "TABUNGAN DANAMON" in t or "DANAMON ONE" in t or "LAPORAN REKENING MCA" in t),
    ]

    for bank_code, condition in checks:
        if condition(t):
            return bank_code

    return None
