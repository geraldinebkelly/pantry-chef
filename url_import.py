"""Import a recipe from its web page, via the schema.org/Recipe JSON-LD
block almost every recipe site embeds for Google's rich-snippet results
(the same structured data commercial recipe clippers like Paprika rely
on). No site-specific scraping - if a page doesn't publish this block,
the import just fails with a clear error asking for a different source.
"""
import gzip
import json
import os
import re
import urllib.request
import zlib
from html import unescape
from urllib.parse import urlparse

from matching import normalize_name
from pdf_import import parse_ingredient_line
from tags import COURSES, CUISINES

_USER_AGENT = "Mozilla/5.0 (compatible; PantryChefRecipeImporter/1.0)"
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024  # generous for a recipe page; stops a pathological download
_REQUEST_TIMEOUT = 15

_LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_DURATION_RE = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", re.IGNORECASE)

_CUISINE_LOOKUP = {c.lower(): c for c in CUISINES}
_COURSE_LOOKUP = {c.lower(): c for c in COURSES}

_NUTRITION_FIELDS = [
    ("servingSize", "Serving"),
    ("calories", "Calories"),
    ("fatContent", "Fat"),
    ("saturatedFatContent", "Saturated Fat"),
    ("cholesterolContent", "Cholesterol"),
    ("sodiumContent", "Sodium"),
    ("carbohydrateContent", "Carbohydrates"),
    ("fiberContent", "Fiber"),
    ("sugarContent", "Sugar"),
    ("proteinContent", "Protein"),
]


class RecipeImportError(Exception):
    """Raised when a page can't be fetched or has no recognizable recipe data."""


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", text))).strip()


def _fetch(url: str, accept: str = "text/html") -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise RecipeImportError("Only http:// and https:// URLs are supported.")
    # Some sites/CDNs (e.g. NYT Cooking) serve gzip even without an
    # Accept-Encoding request header - ask for it explicitly and always
    # decompress, rather than silently getting raw gzip bytes back.
    req = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": accept, "Accept-Encoding": "gzip, deflate"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            body = resp.read(_MAX_RESPONSE_BYTES)
            encoding = (resp.headers.get("Content-Encoding") or "").lower()
    except RecipeImportError:
        raise
    except Exception as exc:
        raise RecipeImportError(f"Couldn't fetch that page: {exc}") from exc

    try:
        if encoding == "gzip":
            body = gzip.decompress(body)
        elif encoding == "deflate":
            body = zlib.decompress(body)
    except (OSError, zlib.error) as exc:
        raise RecipeImportError(f"Couldn't decompress that page's response: {exc}") from exc
    return body


def _find_recipe_node(data):
    """schema.org data can be a single object, a list, or wrapped in an
    @graph array - dig through all of those shapes for a node whose @type
    is (or includes) "Recipe"."""
    if isinstance(data, dict):
        if "@graph" in data:
            found = _find_recipe_node(data["@graph"])
            if found:
                return found
        types = data.get("@type")
        type_list = types if isinstance(types, list) else [types]
        if any(isinstance(t, str) and t.lower() == "recipe" for t in type_list):
            return data
        return None
    if isinstance(data, list):
        for item in data:
            found = _find_recipe_node(item)
            if found:
                return found
    return None


def _repair_json(text: str) -> str:
    """Some sites' recipe plugins emit JSON-LD with a literal, un-escaped
    '"' inside a string value - most often an inch mark in an ingredient
    like `25cm/10" long` - which breaks strict parsing. Walk the text
    tracking string state, and treat a quote as literal content (escaping
    it) rather than a string terminator unless it's actually followed by
    a JSON delimiter, so the rest of the document still parses."""
    out = []
    in_string = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                out.append(text[i:i + 2])
                i += 2
                continue
            if ch == '"':
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if j < n and text[j] in ",:}]":
                    out.append(ch)
                    in_string = False
                else:
                    out.append('\\"')
                i += 1
                continue
            out.append(ch)
            i += 1
        else:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
    return "".join(out)


def _extract_recipe_json(html: str) -> dict:
    for match in _LD_JSON_RE.finditer(html):
        raw = unescape(match.group(1).strip())
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                data = json.loads(_repair_json(raw))
            except json.JSONDecodeError:
                continue
        node = _find_recipe_node(data)
        if node:
            return node
    raise RecipeImportError(
        "No recipe data found on that page - it may not publish the structured "
        "recipe markup this importer relies on. Try the PDF import or add it by hand instead."
    )


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _first_str(value) -> str:
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            return item.strip()
    return ""


def _format_duration(iso: str) -> str:
    if not iso:
        return ""
    match = _DURATION_RE.match(iso.strip())
    if not match:
        return iso
    days, hours, minutes = match.groups()
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != '1' else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != '1' else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != '1' else ''}")
    return " ".join(parts) if parts else iso


def _format_yield(value) -> str:
    text = _first_str(value) or (str(value) if isinstance(value, (int, float)) else "")
    return text.strip()


def _format_tags(value, lookup) -> str:
    tags = []
    for raw in _as_list(value):
        if not isinstance(raw, str):
            continue
        for tag in raw.split(","):
            tag = tag.strip()
            if not tag:
                continue
            canonical = lookup.get(tag.lower(), tag)
            if canonical not in tags:
                tags.append(canonical)
    return ", ".join(tags)


def _flatten_instructions(value) -> str:
    """recipeInstructions is one of: a single string, a list of strings, a
    list of HowToStep objects, or a list of HowToSection objects each
    containing their own nested HowToSteps."""
    steps = []

    def walk(node):
        if isinstance(node, str):
            text = _strip_html(node)
            if text:
                steps.append(text)
        elif isinstance(node, dict):
            node_type = str(node.get("@type", "")).lower()
            if node_type == "howtosection":
                name = node.get("name")
                if name:
                    steps.append(f"-- {_strip_html(name)} --")
                for item in _as_list(node.get("itemListElement")):
                    walk(item)
            else:
                text = node.get("text") or node.get("name") or ""
                text = _strip_html(text)
                if text:
                    steps.append(text)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return "\n".join(f"{i}. {s}" if not s.startswith("--") else s for i, s in enumerate(steps, 1))


def _format_nutrition(value) -> str:
    if not isinstance(value, dict):
        return ""
    lines = []
    for key, label in _NUTRITION_FIELDS:
        raw = value.get(key)
        if raw:
            lines.append(f"{label}: {_strip_html(str(raw))}")
    return "\n".join(lines)


def _image_url(value) -> str:
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict) and item.get("url"):
            return item["url"].strip()
    return ""


def parse_recipe_json(node: dict, fallback_title: str) -> dict:
    ingredients = []
    for raw_line in _as_list(node.get("recipeIngredient") or node.get("ingredients")):
        if not isinstance(raw_line, str):
            continue
        quantity, unit, name = parse_ingredient_line(_strip_html(raw_line))
        if not name:
            continue
        ingredients.append({
            "quantity": quantity,
            "unit": unit,
            "name": name,
            "normalized_name": normalize_name(name),
        })

    return {
        "title": _strip_html(node.get("name", "")) or fallback_title,
        "ingredients": ingredients,
        "instructions": _flatten_instructions(node.get("recipeInstructions")),
        "notes": _strip_html(node.get("description", "")),
        "nutrition": _format_nutrition(node.get("nutrition")),
        "prep_time": _format_duration(node.get("prepTime", "")),
        "cook_time": _format_duration(node.get("cookTime", "")),
        "total_time": _format_duration(node.get("totalTime", "")),
        "servings": _format_yield(node.get("recipeYield")),
        "cuisine": _format_tags(node.get("recipeCuisine"), _CUISINE_LOOKUP),
        "course": _format_tags(node.get("recipeCategory"), _COURSE_LOOKUP),
        "image_url": _image_url(node.get("image")),
    }


def import_url(url: str, fallback_title: str) -> dict:
    """Fetch a recipe page and parse its schema.org/Recipe JSON-LD into the
    same shape pdf_import.import_pdf() returns (plus an "image_url" the
    caller can pass to download_photo())."""
    html = _fetch(url).decode("utf-8", errors="replace")
    node = _extract_recipe_json(html)
    return parse_recipe_json(node, fallback_title)


def download_photo(image_url: str, output_dir: str, filename_prefix: str) -> list:
    """Best-effort download of the recipe's lead photo. Returns a list (0
    or 1 entries) so it drops straight into parsed["photos"], same as
    pdf_import.extract_photos()."""
    if not image_url:
        return []
    try:
        data = _fetch(image_url, accept="image/*")
    except RecipeImportError:
        return []
    if not data:
        return []
    ext = os.path.splitext(urlparse(image_url).path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    os.makedirs(output_dir, exist_ok=True)
    file_name = f"{filename_prefix}_url{ext}"
    with open(os.path.join(output_dir, file_name), "wb") as f:
        f.write(data)
    return [file_name]
