import pytest
from app.core.label_analysis import compute_verdict, compute_verdict_with_database, edit_distance

MIN = 8


def v(text, profile):
    return compute_verdict(text, profile, MIN)


# ---- core behaviour --------------------------------------------------------
def test_definite_ingredient_is_flagged():
    verdict, flagged, _ = v("ingredients: wheat flour, sugar, skimmed milk powder, salt", ["dairy"])
    assert verdict == "flagged" and flagged[0]["id"] == "milk"


def test_clean_label_is_safe():
    verdict, flagged, note = v("ingredients: rice flour, sunflower oil, salt, turmeric", ["dairy", "peanut"])
    assert (verdict, flagged, note) == ("safe", [], None)


def test_hidden_sources_are_caught():
    assert v("ingredients: sugar, whey powder, cocoa mass", ["dairy"])[0] == "flagged"
    assert v("ingredients: maida, palm oil, salt", ["wheat"])[0] == "flagged"
    assert v("ingredients: soya lecithin, sugar, cocoa", ["soy"])[0] == "flagged"
    assert v("ingredients: barley malt extract, sugar", ["gluten"])[0] == "flagged"
    assert v("ingredients: sugar, worcestershire sauce, salt", ["fish"])[0] == "flagged"


def test_profile_tag_variants_match():
    assert v("ingredients: cashew nuts, salt, oil", ["tree_nut"])[0] == "flagged"
    assert v("ingredients: cashew nuts, salt, oil", ["tree nut"])[0] == "flagged"
    assert v("ingredients: whey, sugar, oil", ["milk"])[0] == "flagged"


# ---- precautionary labelling ----------------------------------------------
def test_may_contain_is_unclear_not_safe():
    verdict, flagged, note = v("ingredients: rice flour, salt, oil. may contain traces of peanuts and milk.", ["peanut"])
    assert verdict == "unclear" and flagged == [] and "may contain" in note.lower()


def test_facility_statement_is_unclear():
    verdict, _, note = v("ingredients: oats, sugar, salt. produced in a facility that also handles tree nuts and sesame.", ["sesame"])
    assert verdict == "unclear" and "Sesame" in note


def test_definite_beats_precautionary():
    verdict, flagged, _ = v("ingredients: peanut butter, sugar. may contain peanuts.", ["peanut"])
    assert verdict == "flagged" and flagged[0]["id"] == "peanut"


def test_precaution_clause_does_not_swallow_ingredients():
    # no punctuation after "may contain nuts": milk in the NEXT section must still be flagged
    text = "may contain nuts ingredients: sugar, skimmed milk powder, salt"
    assert v(text, ["dairy"])[0] == "flagged"


def test_made_in_country_is_not_a_precaution_trigger():
    verdict, flagged, _ = v("made in india. ingredients: whey powder, sugar, salt", ["dairy"])
    assert verdict == "flagged"


# ---- free-from claims and false-alarm exclusions ---------------------------
def test_free_from_claim_alone_does_not_flag():
    assert v("dairy free! ingredients: rice flour, coconut oil, salt, sugar", ["dairy"])[0] == "safe"
    assert v("ingredients: oats, sugar, salt. gluten-free. no milk, no soy.", ["gluten", "dairy", "soy"])[0] == "safe"


def test_claim_does_not_hide_real_ingredient():
    verdict, _, _ = v("dairy free ingredients: sugar, milk powder, cocoa", ["dairy"])
    assert verdict == "flagged"


@pytest.mark.parametrize("text", [
    "ingredients: cocoa butter, sugar, cocoa mass",
    "ingredients: coconut milk, rice, salt",
    "ingredients: shea butter, sugar, salt",
])
def test_non_dairy_butter_and_milk(text):
    assert v(text, ["dairy"])[0] == "safe"


def test_substring_words_do_not_match():
    assert v("ingredients: buckwheat flour, eggplant, nutmeg, salt", ["wheat", "egg", "tree-nut"])[0] == "safe"


def test_peanut_butter_flags_peanut_not_dairy():
    assert v("ingredients: peanut butter, salt", ["peanut"])[0] == "flagged"
    assert v("ingredients: peanut butter, salt", ["dairy"])[0] == "safe"


# ---- fail-safe gating ------------------------------------------------------
def test_unreadable_text_is_never_safe():
    assert v("", ["dairy"])[0] == "unclear"
    assert v("xx", ["dairy"])[0] == "unclear"


def test_no_ingredient_heading_is_unclear():
    verdict, _, note = v("nutrition facts energy 250 kcal fat 10 g protein 4 g", ["dairy"])
    assert verdict == "unclear" and "ingredients" in note.lower()


def test_ocr_garbled_heading_still_accepted():
    assert v("ingrcdients: sugar, milk powder, salt", ["dairy"])[0] == "flagged"


def test_one_typo_allergen_is_unclear():
    verdict, _, note = v("ingredients: sugar, salt, peanuk flour mix", ["peanut"])
    assert verdict == "unclear" and "Possible" in note


def test_natural_flavour_is_unclear_for_any_profile():
    assert v("ingredients: sugar, natural flavouring, water", [])[0] == "unclear"


# ---- database cross-check: escalate only ----------------------------------
def prod(**kw):
    base = {"allergen_ids": [], "trace_ids": [], "ingredients_text": None}
    base.update(kw)
    return base


def test_db_escalates_missed_allergen():
    verdict, flagged, note = compute_verdict_with_database(
        "ingredients: sugar, cocoa mass, vanilla", ["dairy"], MIN, prod(allergen_ids=["milk"]))
    assert verdict == "flagged" and flagged[0]["id"] == "milk" and "Open Food Facts" in note


def test_db_traces_escalate_safe_to_unclear():
    verdict, _, _ = compute_verdict_with_database(
        "ingredients: sugar, cocoa mass", ["peanut"], MIN, prod(trace_ids=["peanut"]))
    assert verdict == "unclear"


def test_db_never_downgrades_flagged():
    verdict, flagged, _ = compute_verdict_with_database(
        "ingredients: whey powder, sugar", ["dairy"], MIN, prod())
    assert verdict == "flagged" and flagged


def test_db_can_not_rescue_unreadable_photo_to_safe():
    verdict, _, note = compute_verdict_with_database("", ["dairy"], MIN, prod(ingredients_text="rice, salt"))
    assert verdict == "unclear" and "verify" in note.lower()


def test_db_text_used_when_photo_unreadable():
    verdict, flagged, note = compute_verdict_with_database(
        "", ["dairy"], MIN, prod(ingredients_text="sugar, skimmed milk powder"))
    assert verdict == "flagged" and "not your photo" in note


def test_edit_distance():
    assert edit_distance("peanut", "peanuk") == 1 and edit_distance("abc", "abc") == 0

# ---- OCR digit/letter confusions inside short allergen words ----
def test_ocr_confusable_short_word_is_not_safe():
    from app.core.label_analysis import compute_verdict
    v, flagged, note = compute_verdict("ingredients: wheat flour, m1lk powder, salt", ["milk"])
    assert v != "safe" and note


def test_ocr_rn_for_m_is_not_safe():
    from app.core.label_analysis import compute_verdict
    v, _, _ = compute_verdict("ingredients: sugar, rnilk solids, salt", ["milk"])
    assert v != "safe"


def test_confusable_rule_leaves_e_numbers_and_vitamins_alone():
    from app.core.label_analysis import compute_verdict
    v, _, _ = compute_verdict("ingredients: water, sugar, colour e150d, vitamin b12, e102", ["milk", "egg", "soy"])
    assert v == "safe"