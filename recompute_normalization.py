"""Recompute the derived normalized_name column for ingredients and pantry
items after a change to matching.normalize_name(). Safe to re-run any time
that function changes - it only touches normalized_name, never the actual
ingredient/pantry item names or any other recipe data.
"""
from db import get_connection
from matching import normalize_name


def main():
    conn = get_connection()
    try:
        ingredient_rows = conn.execute("SELECT id, name FROM ingredients").fetchall()
        for row in ingredient_rows:
            conn.execute(
                "UPDATE ingredients SET normalized_name = ? WHERE id = ?",
                (normalize_name(row["name"]), row["id"]),
            )
        print(f"Recomputed {len(ingredient_rows)} ingredient(s).")

        # pantry_items.normalized_name is UNIQUE - if two differently-worded
        # items now normalize to the same thing (e.g. "beef minced" and
        # "minced beef"), merge them into whichever was added first.
        pantry_rows = conn.execute("SELECT id, name FROM pantry_items ORDER BY id").fetchall()
        recomputed = 0
        merged = 0
        for row in pantry_rows:
            new_norm = normalize_name(row["name"])
            existing = conn.execute(
                "SELECT name FROM pantry_items WHERE normalized_name = ? AND id != ?",
                (new_norm, row["id"]),
            ).fetchone()
            if existing:
                print(f"Merging duplicate pantry item {row['name']!r} into {existing['name']!r}")
                conn.execute("DELETE FROM pantry_items WHERE id = ?", (row["id"],))
                merged += 1
                continue
            conn.execute(
                "UPDATE pantry_items SET normalized_name = ? WHERE id = ?",
                (new_norm, row["id"]),
            )
            recomputed += 1
        conn.commit()
        print(f"Recomputed {recomputed} pantry item(s), merged {merged} duplicate(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
