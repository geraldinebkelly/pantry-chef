# AI Recipe Generator

A local web app for tracking your recipes, seeing which ones you can make
with what's already in your kitchen, and generating a shopping list for
what's missing.

## Features

- **Import recipes from PDF.** Upload your saved recipe PDFs; they're
  parsed automatically (title, ingredients, instructions) and saved as
  drafts for you to review and correct before they're kept for good.
- **Pantry tracking.** Keep a simple list of what you currently have.
- **"What can I make?"** Ranks your saved recipes by how many ingredients
  you already have, and shows what's missing for each.
- **Shopping lists.** Select one or more recipes and get a combined,
  deduplicated list of everything you need to buy.

No AI/LLM calls are used — matching is done with local text normalization
(lowercasing, singularizing, stripping notes like "(diced)"). PDF parsing
is heuristic, which is why every import goes through a review step before
being saved.

## Setup

This machine didn't have `pip`/`venv` fully installed, so the venv here
was bootstrapped without `ensurepip` and pip was installed manually via
`get-pip.py`. If you're setting this up fresh somewhere with a normal
Python install, the standard steps work fine:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
source venv/bin/activate
python app.py
```

Then open http://127.0.0.1:5000

## Typical workflow

1. Go to **Import PDF** and upload your saved recipe PDFs (one at a time
   or several at once).
2. Each import lands on a review screen — check the parsed ingredients
   list (one ingredient per line, e.g. `2 cups flour`) and instructions,
   fix anything the parser missed, and save.
3. Go to **Pantry** and list what you currently have, one item per line.
4. Go to **What can I make?** to see your recipes ranked by how much of
   each you already have on hand.
5. Tick the recipes you want to cook and click **Generate shopping list**
   to get a combined list of what to buy.

## Notes on ingredient matching

Matching is name-based and approximate: "Tomatoes (diced)" and "tomato"
both normalize to `tomato`, but it won't know that "scallion" and "green
onion" are the same thing. If a pantry item and a recipe ingredient don't
match, it's usually easiest to just edit the recipe's ingredient name (via
**Edit** on the recipe) to match how you write it in your pantry.

## Project layout

```
app.py            Flask routes
db.py             SQLite schema + connection helper
matching.py       Ingredient name normalization + recipe ranking
pdf_import.py     PDF text extraction + heuristic recipe parsing
templates/        Jinja2 templates
static/style.css  Styling
data/             SQLite DB + uploaded PDFs (gitignored)
```
