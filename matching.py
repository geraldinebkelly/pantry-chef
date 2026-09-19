import re

# Words that end in these suffixes should NOT have a trailing 's' stripped
# when singularizing (stripping would turn them into a different word).
_NO_SINGULARIZE = {
    "molasses", "hummus", "asparagus", "swiss", "citrus", "couscous",
    "chives", "greens", "grits", "oats",
}

# Different words for the same thing that a simple singular/word-order
# normalization can't unify on its own - e.g. "beef mince" (AU/UK) and
# "ground beef" (US) are the same ingredient, as are "mince" and "minced".
_SYNONYMS = {
    "minced": "mince",
    "ground": "mince",
}


_OR_SPLIT_RE = re.compile(r"\bor\b")


def _singularize(word: str) -> str:
    if word in _NO_SINGULARIZE:
        return word
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes", "zes", "ses", "oes")) and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 1:
        return word[:-1]
    return word


def _normalize_words(text: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", " ", text)  # drop "(diced)" style notes
    cleaned = re.sub(r"[^a-z\s]", " ", cleaned)
    words = {_SYNONYMS.get(w, w) for w in cleaned.split()}
    return " ".join(sorted(_singularize(w) for w in words))


def normalize_name(raw_name: str) -> str:
    """Reduce an ingredient name to a form that's stable for matching:
    lowercase, no parenthetical notes, no punctuation, singular-ish, and
    with words sorted so word order doesn't matter - "beef mince" and
    "mince beef" both normalize to the same thing. This is the ingredient's
    primary/first form; see normalize_name_alternatives() for ingredients
    phrased as "X or Y".
    Matching is intentionally approximate - the UI lets you edit names
    so pantry items and recipe ingredients line up.
    """
    name = raw_name.lower().split(",")[0]  # drop trailing prep notes: "bacon, chopped" -> "bacon"
    return _normalize_words(name)


def normalize_name_alternatives(raw_name: str) -> list:
    """Some ingredients list acceptable alternatives with "or" - e.g.
    "ground beef or lamb (mince)", "canola or vegetable oil". Return one
    normalized key per alternative so having any one of them counts as
    having the ingredient.
    """
    name = raw_name.lower().split(",")[0]
    keys = [_normalize_words(branch) for branch in _OR_SPLIT_RE.split(name)]
    return [k for k in keys if k] or [""]


def recipe_match(ingredient_rows, pantry_set):
    """Given a recipe's ingredient rows and a set of normalized pantry
    names, return (have_count, total_count, missing_rows)."""
    have = 0
    missing = []
    for row in ingredient_rows:
        alternatives = normalize_name_alternatives(row["name"])
        if pantry_set.intersection(alternatives):
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
