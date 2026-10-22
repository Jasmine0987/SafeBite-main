import pytest
from app.ai import craving_engine as ce

ALLERGEN_SETS = [["dairy"], ["tree-nut"], ["peanut"], ["soy"], ["sesame"], ["wheat"],
                 ["dairy", "soy", "tree-nut", "sesame"], ["milk", "tree_nut", "gluten"]]
QUERIES = ["crunchy", "sweet", "cold", "warm", "chips", "soda", "chocolate", "spicy", "creamy",
           "snack", "drink", "pizza", "choclate", "no nuts crunchy", "gluten free pasta",
           "ice cream", "samosa", "asdf qwer"]


@pytest.mark.parametrize("allergens", ALLERGEN_SETS)
def test_no_swap_ever_contains_a_blocked_allergen(allergens):
    for q in QUERIES:
        blocked = ce.normalize_allergens(allergens) | ce.parse(q).exclusions
        for r in ce.search(q, allergens)["results"]:
            assert not (set(r["allergens"]) & blocked), (q, allergens, r["name"])


def test_understands_negation_and_diets():
    p = ce.parse("fizzy but not too sweet, dairy-free")
    assert p.vec["fizzy"] > 0.5 and p.vec["sweet"] < 0 and "dairy" in p.exclusions


def test_typo_correction_and_food_names():
    assert ce.search("choclate")["didYouMean"] == {"choclate": "chocolate"}
    assert ce.search("ice cream")["results"][0]["category"] == "dessert"


def test_long_or_empty_queries_do_not_crash():
    assert ce.search("")["results"]
    assert ce.search("x" * 5000)["results"]
