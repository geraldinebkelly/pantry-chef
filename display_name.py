"""Cleans up an ingredient name for display: strips preparation
adjectives/adverbs ("crushed garlic" -> "garlic") without touching words
that change what you'd actually buy ("coriander leaves" stays as-is, since
leaves vs. seed is a different product).

Deliberately separate from matching.normalize_name(), which needs to keep
words like "mince" to tell products apart for matching purposes - this
module only affects what's shown to you, never how ingredients are matched.
"""
import re

# Words describing how an ingredient is prepared, not what it is - safe to
# drop everywhere since they never change what you'd buy at the store.
_PREP_WORDS = {
    "crushed", "minced", "chopped", "diced", "grated", "sliced", "shredded",
    "julienned", "peeled", "trimmed", "mashed", "halved", "quartered",
    "cubed", "coarsely", "finely", "roughly", "thinly", "freshly", "lightly",
}

# Counting/unit words that leak into the name (e.g. "garlic cloves") -
# dropped only if another word remains, so a bare "cloves" (the spice)
# isn't wiped out to nothing.
_UNIT_LIKE_WORDS = {"clove", "cloves"}


def display_name(raw_name: str) -> str:
    text = raw_name.split(",")[0]  # drop trailing prep clause: "bacon, chopped" -> "bacon"
    text = re.sub(r"\([^)]*\)", " ", text)  # drop "(diced)" style notes

    tokens = [t for t in text.split() if t.lower().strip(".") not in _PREP_WORDS]

    # "clove(s)" is a counting unit only in the context of garlic ("2 cloves
    # garlic") - elsewhere (e.g. "ground cloves") it's the spice itself.
    if "garlic" in {t.lower() for t in tokens}:
        tokens = [t for t in tokens if t.lower() not in _UNIT_LIKE_WORDS]

    cleaned = " ".join(tokens).strip(" -–,")
    return cleaned or raw_name.split(",")[0].strip()
