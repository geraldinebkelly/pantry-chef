import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "recipes.db")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")

# Columns added after the initial schema - kept here so an existing
# database (created before a column existed) gets it added in place.
_RECIPE_COLUMN_ADDITIONS = {
    "notes": "TEXT DEFAULT ''",
    "nutrition": "TEXT DEFAULT ''",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_pdf TEXT,
    instructions TEXT,
    notes TEXT DEFAULT '',
    nutrition TEXT DEFAULT '',
    is_draft INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recipe_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    quantity TEXT DEFAULT '',
    unit TEXT DEFAULT '',
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pantry_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE
);
"""


def get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(recipes)")}
        for column, definition in _RECIPE_COLUMN_ADDITIONS.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE recipes ADD COLUMN {column} {definition}")
        conn.commit()
    finally:
        conn.close()


def insert_draft_recipe(conn, parsed: dict, source_pdf: str) -> int:
    """Insert a freshly-parsed PDF recipe as a draft, including any photos
    found in the PDF. Returns the new recipe id."""
    cur = conn.execute(
        "INSERT INTO recipes (title, source_pdf, instructions, notes, nutrition, is_draft) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (parsed["title"], source_pdf, parsed["instructions"], parsed.get("notes", ""), parsed.get("nutrition", "")),
    )
    recipe_id = cur.lastrowid
    for pos, ing in enumerate(parsed["ingredients"]):
        conn.execute(
            "INSERT INTO ingredients (recipe_id, position, quantity, unit, name, normalized_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (recipe_id, pos, ing["quantity"], ing["unit"], ing["name"], ing["normalized_name"]),
        )
    for pos, file_name in enumerate(parsed.get("photos", [])):
        conn.execute(
            "INSERT INTO recipe_photos (recipe_id, file_name, position) VALUES (?, ?, ?)",
            (recipe_id, file_name, pos),
        )
    return recipe_id
