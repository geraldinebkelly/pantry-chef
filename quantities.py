"""Combines ingredient amounts across recipes so the shopping list can show
one summed quantity ("3 eggs") instead of a separate line per recipe, and
scales a single recipe's ingredients to a different serving count.

Parsing is best-effort and conservative: anything this can't confidently
sum or scale (a range like "1-2", a vague amount like "a pinch", mismatched
units) falls back to listing/showing the amount as-is rather than guessing.
"""
import re
from collections import Counter
from fractions import Fraction

_LEADING_INT_RE = re.compile(r"\d+")

# Units that pluralize normally in English. Abbreviations (tbsp, tsp, oz,
# lb, g, kg, ml, l) are the same whether the amount is 1 or 10, so they're
# left out here and used as-is.
_UNIT_PLURALS = {
    "cup": "cups", "clove": "cloves", "can": "cans", "package": "packages",
    "slice": "slices", "piece": "pieces", "stick": "sticks", "quart": "quarts",
    "pint": "pints", "gallon": "gallons", "bunch": "bunches", "pinch": "pinches",
    "dash": "dashes",
}


def parse_quantity(text: str):
    """Parse "2", "1/2", "1 1/2" or "2.5" into a float. Returns None for
    anything else (ranges, blank text, "a few", etc.) so callers can fall
    back instead of summing nonsense."""
    text = text.strip()
    if not text:
        return None
    try:
        if "/" in text:
            parts = text.split()
            if len(parts) == 2:
                whole, frac = parts
                return float(whole) + float(Fraction(frac))
            return float(Fraction(text))
        return float(text)
    except (ValueError, ZeroDivisionError):
        return None


_COOKING_DENOMINATORS = (2, 3, 4, 8)


def format_quantity(value: float) -> str:
    """Render a quantity back in recipe style: whole numbers as-is, common
    cooking fractions ("1 1/2") when the value is actually close to one,
    otherwise a plain decimal. Summing/scaling rarely lands exactly on an
    eighth - forcing everything into one (e.g. 0.3 as "2/7") would be more
    misleading than just showing "0.3"."""
    value = round(value, 6)
    whole = int(value)
    remainder = value - whole
    if remainder < 1e-9:
        return str(whole)
    for denom in _COOKING_DENOMINATORS:
        numerator = round(remainder * denom)
        if numerator == 0:
            continue
        if abs(remainder - numerator / denom) < 0.01:
            frac = Fraction(numerator, denom)
            extra_whole, frac = divmod(frac, 1)
            parts = [str(whole + extra_whole)] if (whole + extra_whole) else []
            if frac:
                parts.append(f"{frac.numerator}/{frac.denominator}")
            return " ".join(parts)
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text


def _pluralize(unit: str, value: float) -> str:
    if not unit or value == 1:
        return unit
    return _UNIT_PLURALS.get(unit, unit)


def combine_amounts(amounts) -> str:
    """amounts: an iterable of (quantity, unit) string pairs for the same
    ingredient, drawn from one or more recipes. Same-unit amounts that all
    parse as numbers are summed into one ("1 egg" + "2 eggs" -> "3");
    anything left over is joined with " + ", deduping identical repeats
    ("pinch" + "pinch" -> "pinch x2")."""
    groups = {}
    order = []
    for quantity, unit in amounts:
        if unit not in groups:
            groups[unit] = []
            order.append(unit)
        groups[unit].append(quantity)

    parts = []
    for unit in order:
        raw_quantities = groups[unit]
        if all(raw_quantities) and all(parse_quantity(q) is not None for q in raw_quantities):
            total = sum(parse_quantity(q) for q in raw_quantities)
            parts.append(f"{format_quantity(total)} {_pluralize(unit, total)}".strip())
        else:
            counts = Counter(
                (f"{q} {unit}".strip() if q else unit) for q in raw_quantities
            )
            for text, n in counts.items():
                if text:
                    parts.append(text if n == 1 else f"{text} x{n}")

    return " + ".join(parts)


def parse_base_servings(text: str):
    """Pull the base serving count out of a recipe's servings text ("4",
    "4-5 people", "6 people") for scaling math. Returns None if there's no
    number to anchor on."""
    match = _LEADING_INT_RE.search(text or "")
    return int(match.group(0)) if match else None


def scale_ingredients(ingredients, ratio: float):
    """Return ingredient rows with quantity scaled by `ratio`. Rows with no
    quantity, or one this can't parse (a range, "to taste"), pass through
    unchanged rather than being guessed at."""
    scaled = []
    for ing in ingredients:
        ing = dict(ing)
        parsed = parse_quantity(ing.get("quantity", ""))
        if parsed is not None:
            ing["quantity"] = format_quantity(parsed * ratio)
        scaled.append(ing)
    return scaled
