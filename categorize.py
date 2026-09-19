"""Groups shopping-list ingredients into grocery-store-style categories.
Keyword-based, same philosophy as matching.py: approximate and local, no
AI calls. Anything that doesn't match a more specific category falls back
to Grains & Pantry (the general "everything else shelf-stable" bucket)
rather than being dropped from the list.
"""
from matching import normalize_name

CATEGORY_ORDER = ["Produce", "Proteins", "Dairy & Alternatives", "Grains & Pantry"]

_PRODUCE_WORDS = {
    "banana", "apple", "berry", "strawberry", "blueberry", "raspberry", "blackberry",
    "lemon", "lime", "orange", "mango", "pineapple", "grape", "melon", "watermelon",
    "peach", "pear", "plum", "cherry", "apricot", "kiwi", "pomegranate", "avocado",
    "tomato", "cucumber", "fruit",
    "spinach", "lettuce", "kale", "cabbage", "arugula", "chard", "carrot", "onion",
    "shallot", "leek", "scallion", "potato", "garlic", "ginger", "zucchini",
    "courgette", "eggplant", "aubergine", "broccoli", "cauliflower", "mushroom",
    "celery", "corn", "pea", "radish", "beet", "beetroot", "pumpkin", "squash",
    "chilli", "chili", "basil", "cilantro", "coriander", "parsley", "mint", "thyme",
    "rosemary", "dill", "chive", "capsicum", "sprout", "cos", "romaine", "iceberg",
    "vegetable", "greens", "herb", "bean",
}

_PROTEIN_WORDS = {
    "egg", "chicken", "beef", "pork", "lamb", "turkey", "duck", "fish", "salmon",
    "tuna", "cod", "shrimp", "prawn", "bacon", "sausage", "mince", "meatball",
    "tofu", "tempeh", "lentil", "chickpea", "seitan", "ham", "chorizo", "steak",
    "meat",
}

_DAIRY_WORDS = {
    "milk", "butter", "cheese", "yogurt", "yoghurt", "cream", "ghee", "buttermilk",
    "mozzarella", "parmesan", "cheddar", "feta", "ricotta", "mascarpone",
}

_PANTRY_WORDS = {
    "rice", "pasta", "spaghetti", "noodle", "oat", "flour", "bread", "breadcrumb",
    "panko", "oil", "vinegar", "salt", "sugar", "cumin", "paprika", "cinnamon",
    "oregano", "cayenne", "sauce", "stock", "broth", "honey", "cornstarch",
    "cornflour", "baking", "yeast", "cocoa", "chocolate", "spice", "seasoning",
    "vanilla", "nutmeg", "clove", "cardamom", "turmeric", "bouillon", "wine",
    "vermicelli", "couscous", "quinoa", "tortilla", "wrap", "pita", "bun",
    "nut", "peanut", "cashew", "almond", "walnut", "sesame", "seed", "coconut",
    "mirin", "sake", "gochujang", "miso", "curry", "powder", "extract", "bay",
    "mayonnaise", "mayo", "ketchup", "hummus", "tzatziki", "salsa", "pesto",
    "dressing", "marinade", "relish", "chutney", "jam", "syrup", "molasses",
}

# Checked before the single-word sets, for words that mean different
# things depending on what they're paired with.
_OVERRIDES = [
    ({"bell", "pepper"}, "Produce"),
    ({"red", "pepper"}, "Produce"),
    ({"green", "pepper"}, "Produce"),
    ({"black", "pepper"}, "Grains & Pantry"),
    ({"white", "pepper"}, "Grains & Pantry"),
    ({"black", "bean"}, "Proteins"),
    ({"kidney", "bean"}, "Proteins"),
    ({"pinto", "bean"}, "Proteins"),
    ({"cannellini", "bean"}, "Proteins"),
    ({"coconut", "milk"}, "Grains & Pantry"),
    ({"coconut", "cream"}, "Grains & Pantry"),
    # Stock/bouillon is a pantry staple regardless of "beef"/"chicken" flavour.
    ({"bouillon"}, "Grains & Pantry"),
    ({"stock"}, "Grains & Pantry"),
    ({"broth"}, "Grains & Pantry"),
]


def categorize(raw_name: str) -> str:
    words = set(normalize_name(raw_name).split())

    for required, category in _OVERRIDES:
        if required <= words:
            return category

    if words & _PROTEIN_WORDS:
        return "Proteins"
    if words & _DAIRY_WORDS:
        return "Dairy & Alternatives"
    if words & _PRODUCE_WORDS:
        return "Produce"
    return "Grains & Pantry"
