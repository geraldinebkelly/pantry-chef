import re

import pdfplumber

from matching import normalize_name

UNIT_WORDS = {
    "cup": "cup", "cups": "cup",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbsp.": "tbsp",
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp", "tsp.": "tsp",
    "ounce": "oz", "ounces": "oz", "oz": "oz", "oz.": "oz",
    "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb", "lb.": "lb",
    "gram": "g", "grams": "g", "g": "g",
    "kilogram": "kg", "kilograms": "kg", "kg": "kg",
    "milliliter": "ml", "milliliters": "ml", "ml": "ml",
    "liter": "l", "liters": "l", "l": "l",
    "pinch": "pinch", "pinches": "pinch",
    "dash": "dash", "dashes": "dash",
    "clove": "clove", "cloves": "clove",
    "can": "can", "cans": "can",
    "package": "package", "packages": "package", "pkg": "package",
    "slice": "slice", "slices": "slice",
    "piece": "piece", "pieces": "piece",
    "stick": "stick", "sticks": "stick",
    "quart": "quart", "quarts": "quart",
    "pint": "pint", "pints": "pint",
    "gallon": "gallon", "gallons": "gallon",
    "bunch": "bunch", "bunches": "bunch",
}

_FRACTION_MAP = {
    "½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}

_QUANTITY_RE = re.compile(
    r"^\s*(\d+\s+\d+/\d+|\d+/\d+|\d+\.\d+|\d+)\s*(?:-\s*(\d+\s+\d+/\d+|\d+/\d+|\d+\.\d+|\d+))?\s*"
)

_INGREDIENTS_HEADER_RE = re.compile(r"^\s*ingredients\s*:?\s*$", re.IGNORECASE)
_INSTRUCTIONS_HEADER_RE = re.compile(
    r"^\s*(instructions|directions|method|steps|preparation)\s*:?\s*$", re.IGNORECASE
)


def extract_text(pdf_path: str) -> str:
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
    return "\n".join(pages_text)


def _replace_unicode_fractions(line: str) -> str:
    for char, replacement in _FRACTION_MAP.items():
        line = line.replace(char, replacement)
    return line


def parse_ingredient_line(line: str):
    """Split a raw ingredient line into (quantity, unit, name)."""
    line = _replace_unicode_fractions(line).strip()
    if not line:
        return "", "", ""

    quantity = ""
    match = _QUANTITY_RE.match(line)
    remainder = line
    if match:
        quantity = match.group(0).strip()
        remainder = line[match.end():].strip()

    unit = ""
    tokens = remainder.split(" ", 1)
    if tokens:
        first_token_key = tokens[0].lower()
        canonical = UNIT_WORDS.get(first_token_key)
        if canonical:
            unit = canonical
            remainder = tokens[1].strip() if len(tokens) > 1 else ""

    name = remainder.strip(" -–")
    return quantity, unit, name


def parse_recipe_text(text: str, fallback_title: str) -> dict:
    lines = [ln.rstrip() for ln in text.splitlines()]
    non_empty = [ln for ln in lines if ln.strip()]

    title = non_empty[0].strip() if non_empty else fallback_title
    if len(title) > 120 or not title:
        title = fallback_title

    ingredients_start = None
    instructions_start = None
    for idx, ln in enumerate(lines):
        if ingredients_start is None and _INGREDIENTS_HEADER_RE.match(ln):
            ingredients_start = idx + 1
            continue
        if ingredients_start is not None and instructions_start is None \
                and _INSTRUCTIONS_HEADER_RE.match(ln):
            instructions_start = idx + 1
            break

    ingredients = []
    if ingredients_start is not None:
        end = instructions_start - 1 if instructions_start else len(lines)
        for ln in lines[ingredients_start:end]:
            if not ln.strip():
                continue
            quantity, unit, name = parse_ingredient_line(ln.strip("-•* \t"))
            if not name:
                continue
            ingredients.append({
                "quantity": quantity,
                "unit": unit,
                "name": name,
                "normalized_name": normalize_name(name),
            })

    if instructions_start is not None:
        instructions = "\n".join(lines[instructions_start:]).strip()
    else:
        # No recognizable headers - dump everything into instructions so
        # nothing is lost; the user can re-split ingredients manually.
        instructions = text.strip()

    return {
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
    }


def import_pdf(pdf_path: str, fallback_title: str) -> dict:
    text = extract_text(pdf_path)
    return parse_recipe_text(text, fallback_title)
