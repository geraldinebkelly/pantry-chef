import os
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

# Blog recipes often give a second unit conversion inline, e.g.
# "300 g / 10oz bacon" or "1 tbsp / 15 g butter" - strip the "/ 10oz" part
# once the primary quantity/unit has already been captured.
_ALT_UNIT_RE = re.compile(r"^/\s*[\d.]+\s*[a-zA-Z]*\.?\s*")

_INGREDIENTS_HEADER_RE = re.compile(r"^\s*ingredients\s*:?\s*$", re.IGNORECASE)
_INSTRUCTIONS_HEADER_RE = re.compile(
    r"^\s*(instructions|directions|method|steps|preparation)\s*:?\s*$", re.IGNORECASE
)
_NOTES_HEADER_RE = re.compile(r"^\s*(recipe notes|notes)\s*:?\s*$", re.IGNORECASE)
_NUTRITION_HEADER_RE = re.compile(
    r"^\s*(nutrition facts|nutrition information|nutrition)\s*:?\s*$", re.IGNORECASE
)

MIN_PHOTO_DIM = 120  # px - filters out any stray icon/button images

# Recipe-plugin PDF exports (WP Recipe Maker and similar) commonly render each
# ingredient as a standalone checkbox glyph line followed by the text, and
# separate sub-groups ("Garnish (optional):", "For the sauce:") with a bare
# label line. Neither is an ingredient on its own.
_BULLET_CHARS = "-•*▢●✓ \t"
# Deliberately not an allow-list of specific punctuation (e.g. "Bulgogi
# sauce (don't skip the onion & apple!):" has "!" and "&", "Red Curry
# Paste – choose ONE:" has an en-dash) - any short line ending in a colon
# within the ingredients section is reliably a group label, never a real
# ingredient.
_SUBHEADING_RE = re.compile(r"^.{1,60}:$")
_PLUGIN_CHROME_RE = re.compile(r"cook mode|prevent.{0,10}screen", re.IGNORECASE)

# Sub-recipe group labels ("Filling", "Bechamel Sauce", "Sauce Option 1")
# that split a multi-component recipe's ingredients into sections - not
# ingredients themselves. Unlike _SUBHEADING_RE these never end with a
# colon, so they're only recognized once quantity/unit parsing has come up
# empty AND every word is capitalized (a real ingredient without a measured
# quantity, like "Black pepper" or "Tomato slices", is always sentence-cased
# - only the first word capitalized - so this doesn't catch those).
_SECTION_LABEL_RE = re.compile(r"^(?:[A-Z][a-zA-Z'-]*|\d+)(?:\s+(?:[A-Z][a-zA-Z'-]*|\d+)){0,3}$")


def _is_ingredient_noise(cleaned_line: str) -> bool:
    if not cleaned_line:
        return True
    if _SUBHEADING_RE.match(cleaned_line):
        return True
    if _PLUGIN_CHROME_RE.search(cleaned_line):
        return True
    return False


def _is_section_label(name: str, quantity: str, unit: str) -> bool:
    return not quantity and not unit and bool(_SECTION_LABEL_RE.match(name.strip()))


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

    if remainder.startswith("/"):
        remainder = _ALT_UNIT_RE.sub("", remainder, count=1)

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
    notes_start = None
    nutrition_start = None
    for idx, ln in enumerate(lines):
        if ingredients_start is None and _INGREDIENTS_HEADER_RE.match(ln):
            ingredients_start = idx + 1
            continue
        if ingredients_start is not None and instructions_start is None \
                and _INSTRUCTIONS_HEADER_RE.match(ln):
            instructions_start = idx + 1
            continue
        if instructions_start is not None and notes_start is None and nutrition_start is None \
                and _NOTES_HEADER_RE.match(ln):
            notes_start = idx + 1
            continue
        if instructions_start is not None and nutrition_start is None and _NUTRITION_HEADER_RE.match(ln):
            nutrition_start = idx + 1
            break

    ingredients = []
    if ingredients_start is not None:
        end = instructions_start - 1 if instructions_start else len(lines)
        for ln in lines[ingredients_start:end]:
            cleaned = ln.strip(_BULLET_CHARS)
            if _is_ingredient_noise(cleaned):
                continue
            quantity, unit, name = parse_ingredient_line(cleaned)
            if not name:
                continue
            if _is_section_label(name, quantity, unit):
                continue
            ingredients.append({
                "quantity": quantity,
                "unit": unit,
                "name": name,
                "normalized_name": normalize_name(name),
            })

    if instructions_start is not None:
        instr_end = notes_start - 1 if notes_start else (nutrition_start - 1 if nutrition_start else len(lines))
        instructions = "\n".join(lines[instructions_start:instr_end]).strip()
    else:
        # No recognizable headers - dump everything into instructions so
        # nothing is lost; the user can re-split ingredients manually.
        instructions = text.strip()

    notes = ""
    if notes_start is not None:
        notes_end = nutrition_start - 1 if nutrition_start else len(lines)
        notes = "\n".join(lines[notes_start:notes_end]).strip()

    nutrition = ""
    if nutrition_start is not None:
        nutrition = "\n".join(lines[nutrition_start:]).strip()

    return {
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
        "notes": notes,
        "nutrition": nutrition,
    }


def extract_photos(pdf_path: str, output_dir: str, filename_prefix: str) -> list:
    """Extract embedded images above MIN_PHOTO_DIM (filters out any stray
    icon/button graphics) and save them as PNGs. Returns the saved
    filenames (relative to output_dir), in page order."""
    os.makedirs(output_dir, exist_ok=True)
    saved = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            for img_idx, img in enumerate(page.images):
                src_w, src_h = img.get("srcsize", (0, 0))
                if src_w < MIN_PHOTO_DIM or src_h < MIN_PHOTO_DIM:
                    continue
                try:
                    bbox = (img["x0"], img["top"], img["x1"], img["bottom"])
                    pil_image = page.crop(bbox).to_image(resolution=150).original
                except Exception:
                    continue
                file_name = f"{filename_prefix}_p{page_num}_{img_idx}.png"
                pil_image.save(os.path.join(output_dir, file_name))
                saved.append(file_name)
    return saved


def import_pdf(pdf_path: str, fallback_title: str) -> dict:
    text = extract_text(pdf_path)
    return parse_recipe_text(text, fallback_title)
