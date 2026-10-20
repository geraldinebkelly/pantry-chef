"""Canonical cuisine/course tags.

Used both to parse site exports (pdf_import.py) and to suggest options
on the recipe form (app.py), so manual entry and imports don't drift
into near-duplicate tags ("Main" vs "Mains" vs "Main Course").
"""

CUISINES = [
    "African", "American", "Arabic", "Asian", "British", "Cajun", "Cantonese",
    "Caribbean", "Chinese", "Cuban", "English", "European", "French", "German",
    "Greek", "Hawaiian", "Indian", "Indonesian", "Italian", "Jamaican",
    "Japanese", "Korean", "Lebanese", "Malaysian", "Mediterranean", "Mexican",
    "Middle Eastern", "Moroccan", "Persian", "Peruvian", "Polish",
    "Portuguese", "Russian", "Sichuan", "Singaporean", "Spanish", "Szechuan",
    "Thai", "Turkish", "Vietnamese", "Western",
]

COURSES = [
    "Breakfast", "Brunch", "Starter", "Side Dish", "Salad", "Soup", "Mains",
    "Dessert", "Snack", "Baking", "Drinks",
]
