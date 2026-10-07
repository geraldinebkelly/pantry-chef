"""Finds ingredients that can stand in for each other, so a shopping list or
weekly plan can point out "you're buying both X and Y - these are
interchangeable, consider using just one." Same philosophy as matching.py
and categorize.py: curated, local, no AI calls.

Groups are taken from NYT Cooking's "How to Make Cooking Substitutions"
(https://cooking.nytimes.com/article/ingredient-substitutions-cooking-baking),
limited to the swaps it states plainly are interchangeable - dairy, alliums,
herbs, cheese tiers, oils/fats by smoke point, and spice flavor profiles.
Left out on purpose: meat, eggs, stock and alcohol substitutions, since the
article's advice there is conditional on the dish (cook time, role in the
recipe) rather than a clean "any member swaps for any other" group, and a
wrong guess there is more likely to mislead than help.
"""
from matching import normalize_name

SUBSTITUTION_GROUPS = [
    {
        "label": "creamy dairy",
        "members": [
            "crema", "creme fraiche", "mascarpone", "neufchatel", "quark",
            "queso fresco", "sour cream", "yogurt", "yoghurt",
        ],
    },
    {
        "label": "alliums",
        "members": ["leek", "onion", "scallion", "shallot", "spring onion"],
    },
    {
        "label": "tender herbs",
        "members": [
            "basil", "chervil", "chives", "cilantro", "coriander leaves",
            "dill", "mint", "parsley", "tarragon",
        ],
    },
    {
        "label": "woody herbs",
        "members": ["bay leaf", "marjoram", "oregano", "rosemary", "sage", "thyme"],
    },
    {
        "label": "fresh unripened cheese",
        "members": ["cottage cheese", "cream cheese", "fromage blanc", "ricotta"],
    },
    {
        "label": "soft-ripened cheese",
        "members": ["brie", "camembert", "pont l'eveque", "taleggio"],
    },
    {
        "label": "semifirm cheese",
        "members": [
            "cheddar", "colby", "edam", "fontina", "gouda", "havarti",
            "jarlsberg", "monterey jack", "mozzarella", "muenster",
            "pepper jack", "port-salut", "swiss cheese",
        ],
    },
    {
        "label": "hard aged cheese",
        "members": ["asiago", "comte", "gruyere", "manchego", "parmesan", "pecorino"],
    },
    {
        "label": "neutral oils",
        "members": [
            "canola oil", "coconut oil", "corn oil", "grapeseed oil",
            "peanut oil", "vegetable oil",
        ],
    },
    {
        "label": "flavored oils",
        "members": ["avocado oil", "nut oil", "olive oil", "sesame oil", "sunflower oil"],
    },
    {
        "label": "solid fats",
        "members": ["bacon fat", "butter", "chicken fat", "lard", "margarine", "shortening", "ghee"],
    },
    {
        "label": "earthy spices",
        "members": ["curry powder", "garlic powder", "onion powder", "turmeric", "vadouvan", "za'atar"],
    },
    {
        "label": "floral spices",
        "members": ["cardamom", "coriander", "fennel", "lavender", "nutmeg", "saffron", "star anise"],
    },
    {
        "label": "peppery spices",
        "members": ["allspice", "ground ginger", "peppercorn", "mustard powder", "sumac"],
    },
    {
        "label": "warm spices",
        "members": ["cinnamon", "dried chile", "chili powder", "cloves", "cumin", "nutmeg", "paprika"],
    },
]

# Precompute each member phrase's normalized word set once, so matching an
# ingredient name only needs a subset check, not re-normalizing every member
# on every lookup.
_GROUPS = [
    {
        "label": group["label"],
        "members": [set(normalize_name(m).split()) for m in group["members"]],
    }
    for group in SUBSTITUTION_GROUPS
]


def find_group(raw_name: str) -> str | None:
    """Return the label of the substitution group an ingredient belongs to,
    or None. A match requires every word of a member phrase to appear in the
    ingredient's normalized name (e.g. "cream cheese" matches "whipped cream
    cheese" but not bare "heavy cream"), to avoid single-word false matches.
    """
    words = set(normalize_name(raw_name).split())
    if not words:
        return None
    for group in _GROUPS:
        for member_words in group["members"]:
            if member_words <= words:
                return group["label"]
    return None


def find_swaps(named_items):
    """named_items: an iterable of (key, display_name) pairs for distinct
    things that would otherwise be bought separately (e.g. already deduped
    shopping-list entries). Returns a list of {"label", "items"} dicts, one
    per substitution group that two or more of the given items fall into,
    each listing the display names involved - the suggestion being that
    buying one and using it for all of them would work just as well.
    """
    by_group = {}
    for _key, name in named_items:
        label = find_group(name)
        if label:
            by_group.setdefault(label, set()).add(name)

    return [
        {"label": label, "items": sorted(names, key=str.lower)}
        for label, names in by_group.items()
        if len(names) >= 2
    ]
