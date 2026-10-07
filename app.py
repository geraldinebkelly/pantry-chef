import os
import uuid
from urllib.parse import quote, urlencode

from flask import Flask, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from categorize import CATEGORY_ORDER, categorize
from db import DATA_DIR, PHOTOS_DIR, get_connection, init_db, insert_draft_recipe
from display_name import display_name
from emailer import send_shopping_list_email
from env_config import load_dotenv
from matching import normalize_name, rank_recipes, recipe_match, suggest_overlapping_plans
from quantities import combine_amounts
from substitutions import find_swaps
from pdf_import import extract_photos, import_pdf, parse_ingredient_line

load_dotenv()

UPLOAD_DIR = os.path.join(DATA_DIR, "pdf_uploads")

app = Flask(__name__)
app.jinja_env.filters["display_name"] = display_name
init_db()


def ingredient_line_from_row(row):
    parts = [row["quantity"], row["unit"], row["name"]]
    return " ".join(p for p in parts if p).strip()


def save_ingredient_lines(conn, recipe_id, lines):
    conn.execute("DELETE FROM ingredients WHERE recipe_id = ?", (recipe_id,))
    position = 0
    for raw_line in lines:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        quantity, unit, name = parse_ingredient_line(raw_line)
        if not name:
            name = raw_line
        conn.execute(
            "INSERT INTO ingredients (recipe_id, position, quantity, unit, name, normalized_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (recipe_id, position, quantity, unit, name, normalize_name(name)),
        )
        position += 1


def fetch_recipe_with_ingredients(conn, recipe_id):
    recipe = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if recipe is None:
        return None, [], []
    ingredients = conn.execute(
        "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY position", (recipe_id,)
    ).fetchall()
    photos = conn.execute(
        "SELECT * FROM recipe_photos WHERE recipe_id = ? ORDER BY position", (recipe_id,)
    ).fetchall()
    return recipe, ingredients, photos


@app.route("/")
def dashboard():
    conn = get_connection()
    try:
        recipe_count = conn.execute(
            "SELECT COUNT(*) c FROM recipes WHERE is_draft = 0"
        ).fetchone()["c"]
        draft_count = conn.execute(
            "SELECT COUNT(*) c FROM recipes WHERE is_draft = 1"
        ).fetchone()["c"]
        pantry_count = conn.execute("SELECT COUNT(*) c FROM pantry_items").fetchone()["c"]
    finally:
        conn.close()
    return render_template(
        "dashboard.html",
        recipe_count=recipe_count,
        draft_count=draft_count,
        pantry_count=pantry_count,
    )


@app.route("/import", methods=["GET", "POST"])
def import_recipe():
    if request.method == "POST":
        files = request.files.getlist("pdf_files")
        conn = get_connection()
        imported_ids = []
        try:
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            for f in files:
                if not f or not f.filename:
                    continue
                safe_name = secure_filename(f.filename)
                stored_name = f"{uuid.uuid4().hex}_{safe_name}"
                stored_path = os.path.join(UPLOAD_DIR, stored_name)
                f.save(stored_path)

                fallback_title = os.path.splitext(safe_name)[0].replace("_", " ").title()
                parsed = import_pdf(stored_path, fallback_title)
                parsed["photos"] = extract_photos(stored_path, PHOTOS_DIR, uuid.uuid4().hex)
                recipe_id = insert_draft_recipe(conn, parsed, safe_name)
                imported_ids.append(recipe_id)
            conn.commit()
        finally:
            conn.close()

        if len(imported_ids) == 1:
            return redirect(url_for("edit_recipe", recipe_id=imported_ids[0]))
        return redirect(url_for("list_recipes"))

    return render_template("import.html")


@app.route("/recipes")
def list_recipes():
    conn = get_connection()
    try:
        recipes = conn.execute(
            "SELECT * FROM recipes ORDER BY is_draft DESC, created_at DESC"
        ).fetchall()
        photo_rows = conn.execute(
            "SELECT recipe_id, file_name FROM recipe_photos ORDER BY recipe_id, position"
        ).fetchall()
    finally:
        conn.close()
    # First photo (by position) per recipe, used as the tile's cover image.
    cover_photos = {}
    for row in photo_rows:
        cover_photos.setdefault(row["recipe_id"], row["file_name"])
    return render_template("recipes.html", recipes=recipes, cover_photos=cover_photos)


@app.route("/recipes/new", methods=["GET", "POST"])
def new_recipe():
    if request.method == "POST":
        conn = get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO recipes (title, source_pdf, instructions, notes, nutrition, "
                "prep_time, cook_time, total_time, servings, is_draft) "
                "VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    request.form["title"].strip(),
                    request.form.get("instructions", "").strip(),
                    request.form.get("notes", "").strip(),
                    request.form.get("nutrition", "").strip(),
                    request.form.get("prep_time", "").strip(),
                    request.form.get("cook_time", "").strip(),
                    request.form.get("total_time", "").strip(),
                    request.form.get("servings", "").strip(),
                ),
            )
            recipe_id = cur.lastrowid
            lines = request.form.get("ingredients", "").splitlines()
            save_ingredient_lines(conn, recipe_id, lines)
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for("view_recipe", recipe_id=recipe_id))
    return render_template("recipe_form.html", recipe=None, ingredient_text="", photos=[], is_new=True)


@app.route("/recipes/<int:recipe_id>")
def view_recipe(recipe_id):
    conn = get_connection()
    try:
        recipe, ingredients, photos = fetch_recipe_with_ingredients(conn, recipe_id)
    finally:
        conn.close()
    if recipe is None:
        return redirect(url_for("list_recipes"))
    return render_template("recipe_detail.html", recipe=recipe, ingredients=ingredients, photos=photos)


@app.route("/photos/<path:file_name>")
def serve_photo(file_name):
    return send_from_directory(PHOTOS_DIR, file_name)


@app.route("/recipes/<int:recipe_id>/photos/<int:photo_id>/delete", methods=["POST"])
def delete_photo(recipe_id, photo_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM recipe_photos WHERE id = ? AND recipe_id = ?", (photo_id, recipe_id))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("edit_recipe", recipe_id=recipe_id))


@app.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
def edit_recipe(recipe_id):
    conn = get_connection()
    try:
        if request.method == "POST":
            conn.execute(
                "UPDATE recipes SET title = ?, instructions = ?, notes = ?, nutrition = ?, "
                "prep_time = ?, cook_time = ?, total_time = ?, servings = ?, is_draft = 0 "
                "WHERE id = ?",
                (
                    request.form["title"].strip(),
                    request.form.get("instructions", "").strip(),
                    request.form.get("notes", "").strip(),
                    request.form.get("nutrition", "").strip(),
                    request.form.get("prep_time", "").strip(),
                    request.form.get("cook_time", "").strip(),
                    request.form.get("total_time", "").strip(),
                    request.form.get("servings", "").strip(),
                    recipe_id,
                ),
            )
            lines = request.form.get("ingredients", "").splitlines()
            save_ingredient_lines(conn, recipe_id, lines)
            conn.commit()
            return redirect(url_for("view_recipe", recipe_id=recipe_id))

        recipe, ingredients, photos = fetch_recipe_with_ingredients(conn, recipe_id)
    finally:
        conn.close()

    if recipe is None:
        return redirect(url_for("list_recipes"))

    ingredient_text = "\n".join(ingredient_line_from_row(r) for r in ingredients)
    return render_template(
        "recipe_form.html", recipe=recipe, ingredient_text=ingredient_text, photos=photos, is_new=False
    )


@app.route("/recipes/<int:recipe_id>/delete", methods=["POST"])
def delete_recipe(recipe_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("list_recipes"))


@app.route("/pantry", methods=["GET", "POST"])
def pantry():
    conn = get_connection()
    try:
        if request.method == "POST":
            raw_items = request.form.get("items", "")
            for line in raw_items.splitlines():
                name = line.strip()
                if not name:
                    continue
                norm = normalize_name(name)
                if not norm:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO pantry_items (name, normalized_name) VALUES (?, ?)",
                    (name, norm),
                )
            conn.commit()
            return redirect(url_for("pantry"))

        items = conn.execute("SELECT * FROM pantry_items ORDER BY name").fetchall()
    finally:
        conn.close()
    return render_template("pantry.html", items=items)


@app.route("/pantry/<int:item_id>/delete", methods=["POST"])
def delete_pantry_item(item_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM pantry_items WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("pantry"))


@app.route("/matches")
def matches():
    conn = get_connection()
    try:
        pantry_rows = conn.execute("SELECT normalized_name FROM pantry_items").fetchall()
        pantry_set = {r["normalized_name"] for r in pantry_rows}

        recipes = conn.execute("SELECT * FROM recipes WHERE is_draft = 0").fetchall()
        recipes_with_ingredients = []
        for recipe in recipes:
            ingredients = conn.execute(
                "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY position", (recipe["id"],)
            ).fetchall()
            recipes_with_ingredients.append((recipe, ingredients))

        ranked = [r for r in rank_recipes(recipes_with_ingredients, pantry_set) if r["have"] > 0]
        total_recipes = len(recipes)
    finally:
        conn.close()
    return render_template(
        "matches.html", ranked=ranked, has_pantry=bool(pantry_set), total_recipes=total_recipes
    )


# Overlap suggestions only consider these food groups - "Grains & Pantry"
# covers condiments, sauces, oils, spices and other staples (cornstarch, soy
# sauce, oyster sauce, salt, sugar...) that either everyone has on hand or
# aren't meaningful to "plan a week" around.
PLAN_CATEGORIES = [c for c in CATEGORY_ORDER if c != "Grains & Pantry"]


@app.route("/plan")
def plan_week():
    conn = get_connection()
    try:
        pantry_rows = conn.execute("SELECT normalized_name FROM pantry_items").fetchall()
        pantry_set = {r["normalized_name"] for r in pantry_rows}

        recipes = conn.execute(
            "SELECT * FROM recipes WHERE is_draft = 0 ORDER BY title"
        ).fetchall()

        selected_ids = request.args.getlist("recipe_id", type=int)
        pool_ids = set(selected_ids) if selected_ids else {r["id"] for r in recipes}

        combo_size = request.args.get("combo_size", type=int) or 3
        combo_size = max(2, min(combo_size, 5))

        pool_recipes_with_ingredients = []
        for recipe in recipes:
            if recipe["id"] not in pool_ids:
                continue
            ingredients = conn.execute(
                "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY position", (recipe["id"],)
            ).fetchall()
            ingredients = [
                row for row in ingredients if categorize(row["name"]) in PLAN_CATEGORIES
            ]
            pool_recipes_with_ingredients.append((recipe, ingredients))

        suggestions = None
        too_many_combos = False
        if "find" in request.args:
            suggestions = suggest_overlapping_plans(
                pool_recipes_with_ingredients, pantry_set, combo_size=combo_size
            )
            if suggestions is None:
                too_many_combos = True
                suggestions = []
            else:
                for suggestion in suggestions:
                    suggestion["swaps"] = find_swaps(suggestion["items"])
                    grouped = {cat: [] for cat in PLAN_CATEGORIES}
                    for name in suggestion["shared_names"]:
                        grouped[categorize(name)].append(name)
                    suggestion["shared_by_category"] = {
                        cat: names for cat, names in grouped.items() if names
                    }
    finally:
        conn.close()

    return render_template(
        "plan.html",
        recipes=recipes,
        pool_ids=pool_ids,
        combo_size=combo_size,
        suggestions=suggestions,
        too_many_combos=too_many_combos,
        searched="find" in request.args,
    )


EMAIL_SUBJECT = "PantryChef Shopping List"


def build_shopping_list(recipe_ids):
    conn = get_connection()
    try:
        pantry_rows = conn.execute("SELECT normalized_name FROM pantry_items").fetchall()
        pantry_set = {r["normalized_name"] for r in pantry_rows}

        groups = []
        merged_items = {}
        for recipe_id in recipe_ids:
            recipe, ingredients, _photos = fetch_recipe_with_ingredients(conn, recipe_id)
            if recipe is None:
                continue
            _have, _total, missing = recipe_match(ingredients, pantry_set)
            groups.append({"recipe": recipe, "missing": missing})
            for item in missing:
                # Dedupe on the same singular/order-independent key used for
                # matching (item["normalized_name"]) so "cube" vs "cubes" or
                # reworded duplicates across recipes collapse into one line.
                key = item["normalized_name"]
                entry = merged_items.setdefault(
                    key, {"name": display_name(item["name"]), "amounts": [], "recipes": []}
                )
                if item["quantity"] or item["unit"]:
                    entry["amounts"].append((item["quantity"], item["unit"]))
                if recipe["title"] not in entry["recipes"]:
                    entry["recipes"].append(recipe["title"])
    finally:
        conn.close()

    categorized = {cat: [] for cat in CATEGORY_ORDER}
    for data in merged_items.values():
        category = categorize(data["name"])
        categorized[category].append({
            "name": data["name"],
            "amount": combine_amounts(data["amounts"]),
            "recipes": ", ".join(data["recipes"]),
        })
    categorized = {
        cat: sorted(items, key=lambda item: item["name"].lower())
        for cat, items in categorized.items() if items
    }
    total_count = sum(len(items) for items in categorized.values())
    swaps = find_swaps((key, data["name"]) for key, data in merged_items.items())

    body_lines = []
    for cat, items in categorized.items():
        body_lines.append(cat.upper())
        for item in items:
            line = f"- {item['name']}"
            if item["amount"]:
                line += f" ({item['amount']})"
            if item["recipes"]:
                line += f" [{item['recipes']}]"
            body_lines.append(line)
        body_lines.append("")
    body_text = "\r\n".join(body_lines).strip()

    return groups, categorized, total_count, body_text, swaps


@app.route("/shopping-list")
def shopping_list():
    recipe_ids = request.args.getlist("recipe_id", type=int)
    groups, categorized, total_count, body_text, swaps = build_shopping_list(recipe_ids)
    mailto_href = "mailto:?" + urlencode(
        {"subject": EMAIL_SUBJECT, "body": body_text}, quote_via=quote
    )

    return render_template(
        "shopping_list.html",
        groups=groups,
        total_count=total_count,
        categorized=categorized,
        mailto_href=mailto_href,
        recipe_ids=recipe_ids,
        swaps=swaps,
    )


@app.route("/shopping-list/send", methods=["POST"])
def send_shopping_list():
    recipe_ids = [int(v) for v in request.form.getlist("recipe_id")]
    to_address = request.form.get("email", "").strip()
    groups, categorized, total_count, body_text, swaps = build_shopping_list(recipe_ids)
    mailto_href = "mailto:?" + urlencode(
        {"subject": EMAIL_SUBJECT, "body": body_text}, quote_via=quote
    )

    email_status = None
    if not to_address:
        email_status = {"ok": False, "message": "Enter an email address first."}
    else:
        try:
            send_shopping_list_email(to_address, EMAIL_SUBJECT, body_text)
            email_status = {"ok": True, "message": f"Sent to {to_address}."}
        except Exception as exc:
            email_status = {"ok": False, "message": str(exc)}

    return render_template(
        "shopping_list.html",
        groups=groups,
        total_count=total_count,
        categorized=categorized,
        mailto_href=mailto_href,
        recipe_ids=recipe_ids,
        swaps=swaps,
        email_status=email_status,
        email_value=to_address,
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
