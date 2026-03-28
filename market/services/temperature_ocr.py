import re
import tempfile

import pytesseract
from PIL import Image


def extract_temperature_from_uploaded_file(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        temp_path = tmp.name

    image = Image.open(temp_path)
    text = pytesseract.image_to_string(image, lang="spa+eng")

    cleaned = text.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)

    temperature = None
    if match:
        try:
            temperature = float(match.group(0))
        except ValueError:
            temperature = None

    return {
        "temperature": temperature,
        "raw_text": text.strip(),
    }
