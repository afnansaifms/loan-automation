import io

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image

MIN_CHARS_FOR_NATIVE = 50


def extract_native_text(file_path: str) -> str:
    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts).strip()


def extract_ocr_text(file_path: str) -> str:
    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text_parts.append(pytesseract.image_to_string(img))
    return "\n".join(text_parts).strip()


def parse_statement(file_path: str) -> dict:
    native_text = extract_native_text(file_path)
    if len(native_text) >= MIN_CHARS_FOR_NATIVE:
        return {"raw_text": native_text, "parse_method": "native_pdf"}
    ocr_text = extract_ocr_text(file_path)
    return {"raw_text": ocr_text, "parse_method": "ocr"}


def extract_tables_native(file_path: str) -> list:
    tables = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                tables.append(table)
    return tables