import os
import re

import pdfplumber

from matching import normalize_name
from tags import CUISINES

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


# A PDF saved via a browser's own "Print to PDF" dialog (rather than a
# site's dedicated recipe-PDF export) stamps a date/time + page-title
# header and a URL + page-number footer on every single page. Left in,
# the header's timestamp becomes the recipe's "title" (it's the first
# line of text), and on a multi-page recipe these lines can turn up
# mid-ingredient-list too - so they're stripped before anything else
# parses the text.
_PRINT_HEADER_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*[AP]M\b.*$", re.MULTILINE)
_PRINT_FOOTER_RE = re.compile(r"^https?://\S+\s+\d+/\d+\s*$", re.MULTILINE)


def _strip_browser_print_chrome(text: str) -> str:
    text = _PRINT_HEADER_RE.sub("", text)
    text = _PRINT_FOOTER_RE.sub("", text)
    return text


def extract_text(pdf_path: str) -> str:
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
    return _strip_browser_print_chrome("\n".join(pages_text))


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


# Recipe-plugin exports (WP Recipe Maker, used by RecipeTin Eats and many
# other recipe blogs) render the Prep/Cook/Total time and servings as
# separate on-page elements (a number, the unit word, and an abbreviated
# unit tooltip) that pdfplumber flattens into a run like
# "Prep: 20\nminutes\nmins Cook: 55\nminutes\nmins ... Total: 1\nday\nd 1\n
# hour\nhr 15\nminutes\nmins" - this reassembles that into "20 minutes",
# "1 day 1 hour 15 minutes", etc.
_DURATION_TOKEN_RE = re.compile(r"(\d+)\s*(day|hour|minute)s?\s*(?:d|hr|hrs|mins)?\s*")

# Servings is similarly scrambled - a number lands before the word
# "Servings", and an optional range ("– 5") or qualifier ("people", "as a
# side") lands after it, right before the "Tap or hover to scale" control.
_SERVINGS_RE = re.compile(
    r"(\d+)\s*Servings\s*(?:[-–]\s*(\d+))?\s*([a-zA-Z](?:[a-zA-Z ]*[a-zA-Z])?)?\s*Tap or hover to scale"
)

# Between the time block and the star rating, these exports print the
# recipe's course and cuisine tags run together with no delimiter telling
# them apart ("Mains, Stir Fries Chinese, Sichuan" - "Mains, Stir Fries" is
# the course, "Chinese, Sichuan" the cuisine). Rather than guess the split,
# pull out any known cuisine name found in that block. A couple of the
# site's own tag spellings are folded into the closest standard cuisine.
_CUISINE_SYNONYMS = {"korean fusion": "Korean", "mexican-esque": "Mexican", "szechuan": "Sichuan"}
_CUISINE_LOOKUP = {c.lower(): c for c in CUISINES}
_CUISINE_LOOKUP.update(_CUISINE_SYNONYMS)
_CUISINE_RE = re.compile(
    "|".join(re.escape(phrase) for phrase in sorted(_CUISINE_LOOKUP, key=len, reverse=True)),
    re.IGNORECASE,
)

_RATING_RE = re.compile(r"\d+(?:\.\d+)?\s*from\s*\d+\s*votes", re.IGNORECASE)

# Whatever's left in the block after the cuisine names are stripped out is
# the course/meal-type tags (e.g. "Mains", "Side Dish", "Salad"). The site
# spells the same course inconsistently ("Main" vs "Mains" vs "Meals" all
# mean the same slot in a meal) - fold those down to one canonical tag so
# filtering isn't fragmented across near-duplicates.
_COURSE_SYNONYMS = {"main": "Mains", "meals": "Mains", "stir fries": "Stir Fry"}


def _extract_duration(text: str, start: int):
    """Returns (formatted duration, index just past the consumed tokens)."""
    parts = []
    pos = start
    while True:
        match = _DURATION_TOKEN_RE.match(text, pos)
        if not match:
            break
        num, unit = match.group(1), match.group(2)
        parts.append(f"{num} {unit}{'s' if num != '1' else ''}")
        pos = match.end()
    return " ".join(parts), pos


def extract_recipe_meta(text: str) -> dict:
    """Best-effort extraction of prep/cook/total time, servings and cuisine
    from a WP Recipe Maker-style export. Any field not found is left as ""."""
    meta = {"prep_time": "", "cook_time": "", "total_time": "", "servings": "", "cuisine": "", "course": ""}
    duration_end = 0
    # "Marinating:" (sometimes "Marinating time:", sometimes with a typo'd
    # double colon) isn't a field we keep, but it still occupies duration
    # tokens right before the course/cuisine block on recipes with no
    # "Total:" - skip over it too so it doesn't leak into the course text.
    label_patterns = (
        (r"Prep:", "prep_time"),
        (r"Cook:", "cook_time"),
        (r"Marinating(?:\s+time)?:+", None),
        (r"Total:", "total_time"),
    )
    for pattern, key in label_patterns:
        label_match = re.search(pattern + r"\s*", text)
        if label_match:
            value, end_pos = _extract_duration(text, label_match.end())
            if key:
                meta[key] = value
            # The course/cuisine block always follows whichever of these
            # labels appears last - not necessarily "Total:", since some
            # recipes omit it (e.g. a salad with no cook time).
            duration_end = max(duration_end, end_pos)

    rating_match = _RATING_RE.search(text)
    if duration_end and rating_match and rating_match.start() > duration_end:
        block = text[duration_end:rating_match.start()]
        found = []
        for match in _CUISINE_RE.finditer(block):
            canonical = _CUISINE_LOOKUP[match.group(0).lower()]
            if canonical not in found:
                found.append(canonical)
        meta["cuisine"] = ", ".join(found)

        courses = []
        for tag in _CUISINE_RE.sub("", block).split(","):
            tag = tag.strip()
            if not tag:
                continue
            canonical = _COURSE_SYNONYMS.get(tag.lower(), tag)
            if canonical not in courses:
                courses.append(canonical)
        meta["course"] = ", ".join(courses)

    match = _SERVINGS_RE.search(text)
    if match:
        low, high, suffix = match.groups()
        servings = f"{low}-{high}" if high else low
        if suffix and suffix.strip():
            servings += f" {suffix.strip()}"
        meta["servings"] = servings

    return meta


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

    meta = extract_recipe_meta(text)

    return {
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
        "notes": notes,
        "nutrition": nutrition,
        "prep_time": meta["prep_time"],
        "cook_time": meta["cook_time"],
        "total_time": meta["total_time"],
        "servings": meta["servings"],
        "cuisine": meta["cuisine"],
        "course": meta["course"],
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
