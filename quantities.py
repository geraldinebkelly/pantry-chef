"""Combines ingredient amounts across recipes so the shopping list can show
one summed quantity ("3 eggs") instead of a separate line per recipe.

Parsing is best-effort and conservative: anything this can't confidently
sum (a range like "1-2", a vague amount like "a pinch", mismatched units)
falls back to listing the amounts side by side rather than guessing.
"""
from collections import Counter
from fractions import Fraction

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


def format_quantity(value: float) -> str:
    """Render a summed quantity back in recipe style: whole numbers as-is,
    otherwise as a simple fraction ("1 1/2") instead of a decimal."""
    if value == int(value):
        return str(int(value))
    frac = Fraction(value).limit_denominator(8)
    whole, remainder = divmod(frac, 1)
    if remainder == 0:
        return str(whole)
    if whole == 0:
        return f"{remainder.numerator}/{remainder.denominator}"
    return f"{int(whole)} {remainder.numerator}/{remainder.denominator}"


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
