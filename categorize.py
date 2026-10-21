"""Groups shopping-list ingredients into grocery-store-style categories.
Keyword-based, same philosophy as matching.py: approximate and local, no
AI calls. Anything that doesn't match a more specific category falls back
to Grains & Pantry (the general "everything else shelf-stable" bucket)
rather than being dropped from the list.
"""
from matching import normalize_name

CATEGORY_ORDER = [
    "Produce", "Proteins", "Dairy & Alternatives", "Bread and Cereals",
    "Canned and Jar Goods", "Beverages", "Grains & Pantry",
]

CATEGORY_EMOJI = {
    "Produce": "🥬",
    "Proteins": "🥩",
    "Dairy & Alternatives": "🥛",
    "Bread and Cereals": "🍞",
    "Canned and Jar Goods": "🥫",
    "Beverages": "🥤",
    "Grains & Pantry": "🧂",
}

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
    "beef", "pork", "lamb", "veal", "venison", "goat", "mutton",
    "chicken", "turkey", "duck",
    "fish", "salmon", "tuna", "cod", "shrimp", "prawn", "crab", "lobster",
    "scallop", "mussel", "oyster", "squid", "calamari", "anchovy", "mackerel",
    "trout", "snapper",
    "bacon", "sausage", "mince", "meatball", "ham", "chorizo", "steak", "meat",
    "egg", "tofu", "tempeh", "lentil", "chickpea", "seitan",
}

_DAIRY_WORDS = {
    "milk", "butter", "cheese", "yogurt", "yoghurt", "cream", "ghee", "buttermilk",
    "mozzarella", "parmesan", "cheddar", "feta", "ricotta", "mascarpone",
}

_PANTRY_WORDS = {
    "rice", "pasta", "spaghetti", "noodle", "flour", "oil", "vinegar", "salt",
    "sugar", "cumin", "paprika", "cinnamon", "oregano", "cayenne", "sauce",
    "stock", "broth", "cornstarch", "cornflour", "baking", "yeast", "cocoa",
    "chocolate", "spice", "seasoning", "vanilla", "nutmeg", "clove",
    "cardamom", "turmeric", "bouillon", "wine", "vermicelli", "couscous",
    "quinoa", "nut", "peanut", "cashew", "almond", "walnut", "sesame", "seed",
    "coconut", "mirin", "sake", "gochujang", "miso", "curry", "powder",
    "extract", "bay", "dressing", "marinade",
}

_BREAD_CEREAL_WORDS = {
    "bread", "breadcrumb", "panko", "bun", "roll", "bagel", "baguette",
    "tortilla", "wrap", "pita", "toast", "cereal", "oat", "oats", "oatmeal",
    "granola", "muesli", "cornflake",
}

_CANNED_JAR_WORDS = {
    "jam", "marmalade", "chutney", "relish", "pickle", "pickles", "olive",
    "caper", "mayonnaise", "mayo", "ketchup", "mustard", "salsa", "pesto",
    "hummus", "tzatziki", "canned", "tinned", "preserve", "honey", "syrup",
    "molasses", "nutella",
}

_BEVERAGE_WORDS = {
    "juice", "soda", "cola", "water", "coffee", "tea", "beer", "cider",
    "lemonade", "kombucha", "smoothie",
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
    # The dried/ground spice form is a pantry item, unlike the fresh herb/root.
    ({"ground", "coriander"}, "Grains & Pantry"),
    ({"ground", "ginger"}, "Grains & Pantry"),
    ({"ground", "chilli"}, "Grains & Pantry"),
    ({"ground", "chili"}, "Grains & Pantry"),
    # "butter" alone is dairy, but peanut butter is a jarred pantry good.
    ({"peanut", "butter"}, "Canned and Jar Goods"),
    # "oil"/"soda" alone would be fine as pantry, but they share a word with
    # a jar/beverage item ("olive", "soda water") that'd otherwise win.
    ({"olive", "oil"}, "Grains & Pantry"),
    ({"baking", "soda"}, "Grains & Pantry"),
    # Water chestnuts are a vegetable, not the "water" beverage word.
    ({"water", "chestnut"}, "Produce"),
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
    # Checked ahead of Produce: a jar/can/drink word (e.g. "strawberry jam",
    # "orange juice", "canned tomatoes") should win over a fruit/veg word
    # that's just along for the ride in the same ingredient name.
    if words & _BREAD_CEREAL_WORDS:
        return "Bread and Cereals"
    if words & _CANNED_JAR_WORDS:
        return "Canned and Jar Goods"
    if words & _BEVERAGE_WORDS:
        return "Beverages"
    if words & _PRODUCE_WORDS:
        return "Produce"
    return "Grains & Pantry"
