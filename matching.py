import re

# Words that end in these suffixes should NOT have a trailing 's' stripped
# when singularizing (stripping would turn them into a different word).
_NO_SINGULARIZE = {
    "molasses", "hummus", "asparagus", "swiss", "citrus", "couscous",
    "chives", "greens", "grits", "oats",
}


def normalize_name(raw_name: str) -> str:
    """Reduce an ingredient name to a form that's stable for matching:
    lowercase, no parenthetical notes, no punctuation, singular-ish.
    Matching is intentionally approximate - the UI lets you edit names
    so pantry items and recipe ingredients line up.
    """
    name = raw_name.lower()
    name = re.sub(r"\([^)]*\)", " ", name)  # drop "(diced)" style notes
    name = re.sub(r"[^a-z\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    words = name.split(" ")
    if words:
        last = words[-1]
        if last not in _NO_SINGULARIZE:
            if last.endswith("ies") and len(last) > 3:
                last = last[:-3] + "y"
            elif last.endswith(("ches", "shes", "xes", "zes", "ses", "oes")) and len(last) > 4:
                last = last[:-2]
            elif last.endswith("s") and not last.endswith("ss") and len(last) > 1:
                last = last[:-1]
        words[-1] = last
    return " ".join(words).strip()


def recipe_match(ingredient_rows, pantry_set):
    """Given a recipe's ingredient rows and a set of normalized pantry
    names, return (have_count, total_count, missing_rows)."""
    have = 0
    missing = []
    for row in ingredient_rows:
        if row["normalized_name"] in pantry_set:
            have += 1
        else:
            missing.append(row)
    return have, len(ingredient_rows), missing


def rank_recipes(recipes_with_ingredients, pantry_set):
    """recipes_with_ingredients: list of (recipe_row, [ingredient_rows]).
    Returns list of dicts sorted by best match first, recipes with zero
    ingredients are skipped.
    """
    ranked = []
    for recipe, ingredient_rows in recipes_with_ingredients:
        if not ingredient_rows:
            continue
        have, total, missing = recipe_match(ingredient_rows, pantry_set)
        ranked.append({
            "recipe": recipe,
            "have": have,
            "total": total,
            "missing": missing,
            "fraction": have / total,
        })
    ranked.sort(key=lambda r: (-r["fraction"], len(r["missing"])))
    return ranked
