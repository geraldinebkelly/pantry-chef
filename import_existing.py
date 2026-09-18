"""Import PDFs that were placed directly in data/pdf_uploads/ instead of
uploaded through the web form. Safe to re-run - files already recorded
against a recipe (by filename) are skipped.
"""
import os
import uuid

from db import PHOTOS_DIR, get_connection, init_db, insert_draft_recipe
from pdf_import import extract_photos, import_pdf

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pdf_uploads")


def main():
    init_db()
    conn = get_connection()
    try:
        already_imported = {
            row["source_pdf"]
            for row in conn.execute("SELECT source_pdf FROM recipes WHERE source_pdf IS NOT NULL")
        }
        imported = 0
        for filename in sorted(os.listdir(UPLOAD_DIR)):
            if not filename.lower().endswith(".pdf") or filename in already_imported:
                continue
            path = os.path.join(UPLOAD_DIR, filename)
            fallback_title = os.path.splitext(filename)[0].replace("_", " ").title()
            parsed = import_pdf(path, fallback_title)
            parsed["photos"] = extract_photos(path, PHOTOS_DIR, uuid.uuid4().hex)
            insert_draft_recipe(conn, parsed, filename)
            imported += 1
            print(
                f"Imported: {parsed['title']} "
                f"({len(parsed['ingredients'])} ingredients, {len(parsed['photos'])} photo(s))"
            )
        conn.commit()
        print(f"\nDone - {imported} new recipe(s) added as drafts, ready to review in the app.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
