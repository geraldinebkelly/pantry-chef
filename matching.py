import re
from itertools import combinations
from math import comb

from display_name import display_name

# Words that end in these suffixes should NOT have a trailing 's' stripped
# when singularizing (stripping would turn them into a different word).
_NO_SINGULARIZE = {
    "molasses", "hummus", "asparagus", "swiss", "citrus", "couscous",
    "chives", "greens", "grits", "oats",
}

# "minced" always means "mince" (garlic, beef, whatever it's attached to).
# "ground" is ambiguous though - "ground beef" means mince, but "ground
# cumin"/"ground cardamom" is just a spice's form, not meat - so it's only
# folded into "mince" when a meat word is also present in the same name.
_SYNONYMS = {
    "minced": "mince",
}
_MEAT_NOUNS = {"beef", "pork", "lamb", "chicken", "turkey", "veal", "venison", "goat", "duck"}


_OR_SPLIT_RE = re.compile(r"\bor\b")


def _lower_no_parens(raw_name: str) -> str:
    # Strip "(...)" notes before splitting on comma, since a note can itself
    # contain a comma ("onion (brown, yellow, or white), cut into wedges") -
    # splitting first would cut the name off mid-parenthesis.
    return re.sub(r"\([^)]*\)", " ", raw_name.lower())


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
    raw_words = cleaned.split()
    has_meat_noun = any(w in _MEAT_NOUNS for w in raw_words)

    words = set()
    for w in raw_words:
        w = _SYNONYMS.get(w, w)
        if w == "ground" and has_meat_noun:
            w = "mince"
        words.add(_singularize(w))

    if "garlic" in words:
        # "clove(s)" is a counting unit only in the context of garlic ("2
        # cloves garlic") - drop it so "garlic" and "garlic cloves" match as
        # the same ingredient. Elsewhere (e.g. "ground cloves") it's kept,
        # since that's the spice itself.
        words.discard("clove")
    return " ".join(sorted(words))


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
    name = _lower_no_parens(raw_name).split(",")[0]  # drop trailing prep notes: "bacon, chopped" -> "bacon"
    return _normalize_words(name)


def normalize_name_alternatives(raw_name: str) -> list:
    """Some ingredients list acceptable alternatives with "or" - e.g.
    "ground beef or lamb (mince)", "canola or vegetable oil". Return one
    normalized key per alternative so having any one of them counts as
    having the ingredient.
    """
    name = _lower_no_parens(raw_name).split(",")[0]
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


# Above this many combinations, scanning them all gets slow enough that the
# caller should ask the user to narrow the recipe pool instead.
MAX_PLAN_COMBOS = 20000


def suggest_overlapping_plans(recipes_with_ingredients, pantry_set, combo_size=3, top_n=5):
    """Suggest which combinations of `combo_size` recipes share the most
    ingredients you'd still need to buy - the "build the week around
    overlap" strategy (pick recipes that use up a bunch of basil or a tub
    of cottage cheese together, rather than buying a little for each).

    Only ingredients missing from the pantry are considered, since an
    ingredient you already have doesn't affect what buying it once for
    several recipes would save you.

    Returns the top `top_n` combos as dicts with "recipes", "shared_names"
    (display names of ingredients used by 2+ recipes in the combo),
    "distinct_count" (total separate items you'd need to buy for the combo)
    and "items" ((key, display_name) pairs for every one of those items, for
    callers that want to look for substitution opportunities on top of the
    overlap found here), sorted by most shared ingredients first and then
    fewest total items to buy. Returns None if there are too many eligible
    recipes to scan every combination (caller should ask the user to narrow
    the pool), or [] if no combination of that size shares any ingredient.
    """
    eligible = [(r, rows) for r, rows in recipes_with_ingredients if rows]
    if len(eligible) < combo_size:
        return []
    if comb(len(eligible), combo_size) > MAX_PLAN_COMBOS:
        return None

    per_recipe = []
    for recipe, ingredient_rows in eligible:
        _have, _total, missing = recipe_match(ingredient_rows, pantry_set)
        keyed = {}
        for row in missing:
            cleaned = display_name(row["name"])
            for key in normalize_name_alternatives(row["name"]):
                if key:
                    keyed.setdefault(key, cleaned)
        per_recipe.append((recipe, keyed))

    results = []
    for combo in combinations(per_recipe, combo_size):
        titles = {recipe["title"].strip().lower() for recipe, _keyed in combo}
        if len(titles) < combo_size:
            # Two slots filled by what's really the same recipe (e.g. a
            # duplicate import) - not a meaningful "plan".
            continue
        key_sets = [set(keyed) for _recipe, keyed in combo]
        all_keys = set().union(*key_sets)
        shared_keys = {k for k in all_keys if sum(k in s for s in key_sets) >= 2}
        if not shared_keys:
            continue
        combined_items = {}
        for _recipe, keyed in combo:
            for key, name in keyed.items():
                combined_items.setdefault(key, name)
        shared_names = sorted(
            {combined_items[k] for k in shared_keys}, key=str.lower
        )
        results.append({
            "recipes": [recipe for recipe, _keyed in combo],
            "shared_count": len(shared_keys),
            "shared_names": shared_names,
            "distinct_count": len(all_keys),
            "items": list(combined_items.items()),
        })

    results.sort(key=lambda r: (-r["shared_count"], r["distinct_count"]))
    return results[:top_n]
