"""
Allergen / ingredient knowledge base (single source of truth).

main.py used to hold this inline with ~60 aliases. It now lives here with
~230 aliases (UK/Indian label terms, hidden sources such as whey, maida,
worcestershire) and an EXCLUDE_FOR table that stops false alarms such as
"cocoa butter" -> dairy or "coconut milk" -> dairy.

Shape of each entry is unchanged, so GET /api/ingredient/{id} still works.
"""


def _entry(name, aliases, tags, plain, why):
    return {
        "name": name,
        "aliases": aliases,
        "allergen_tags": tags,
        "plainLanguage": plain,
        "whyForYouTemplate": why,
    }


INGREDIENT_KB = {
    "red40": _entry(
        "Red 40",
        ["red 40", "fd&c red no. 40", "allura red ac", "allura red", "e129", "ins 129"],
        [],
        "A synthetic dye made from petroleum, used to make foods look redder than the ingredients actually would on their own.",
        "Flagged because it's a synthetic dye — some people react to it even without a formal allergy.",
    ),
    "natural-flavor": _entry(
        "Natural Flavor",
        ["natural flavor", "natural flavors", "natural flavoring", "natural flavour",
         "natural flavours", "natural flavouring", "natural flavouring substances",
         "nature identical flavouring", "nature identical flavoring"],
        [],
        "A catch-all term for flavor compounds from real plant/animal sources — the exact recipe isn't disclosed.",
        "Flagged as 'unclear' because the exact source can't be confirmed from the label alone.",
    ),
    "milk": _entry(
        "Milk / Dairy",
        ["milk", "dairy", "whey", "whey powder", "whey protein", "casein", "caseinate",
         "sodium caseinate", "lactose", "lactalbumin", "lactoglobulin", "ghee", "butter",
         "buttermilk", "cream", "cheese", "yogurt", "yoghurt", "curd", "dahi", "paneer",
         "khoa", "khoya", "milk solids", "milk powder", "skim milk", "skimmed milk",
         "skimmed milk powder", "milk protein", "milk fat", "condensed milk",
         "evaporated milk", "sour cream", "ice cream", "kefir", "lassi"],
        ["dairy", "milk"],
        "Derived from cow's milk. Includes whey, casein and ghee even when 'milk' isn't listed directly.",
        "Flagged because dairy is on your allergen profile.",
    ),
    "egg": _entry(
        "Egg",
        ["egg", "eggs", "egg white", "egg yolk", "egg powder", "dried egg", "albumin",
         "albumen", "ovalbumin", "ovomucoid", "lysozyme", "mayonnaise", "meringue"],
        ["egg"],
        "Whole egg or egg-derived proteins such as albumin.",
        "Flagged because egg is on your allergen profile.",
    ),
    "fish": _entry(
        "Fish",
        ["fish", "salmon", "tuna", "cod", "anchovy", "anchovies", "tilapia", "sardine",
         "haddock", "mackerel", "pollock", "fish sauce", "fish oil", "surimi",
         "worcestershire", "worcestershire sauce"],
        ["fish"],
        "Finned fish and fish-derived ingredients.",
        "Flagged because fish is on your allergen profile.",
    ),
    "shellfish": _entry(
        "Shellfish",
        ["shellfish", "shrimp", "prawn", "prawns", "crab", "lobster", "crayfish", "krill",
         "clam", "mussel", "oyster", "oyster sauce", "scallop", "squid", "octopus",
         "cuttlefish", "shrimp paste"],
        ["shellfish"],
        "Crustaceans and molluscs.",
        "Flagged because shellfish is on your allergen profile.",
    ),
    "tree-nut": _entry(
        "Tree Nuts",
        ["almond", "almonds", "cashew", "cashews", "cashew nut", "cashew nuts", "walnut",
         "walnuts", "pecan", "pecans", "pistachio", "pistachios", "hazelnut", "hazelnuts",
         "macadamia", "brazil nut", "brazil nuts", "pine nut", "pine nuts", "chestnut",
         "chestnuts", "praline", "marzipan", "nougat", "gianduja", "nut paste",
         "kaju", "badam", "akhrot", "pista"],
        ["tree-nut", "tree nut", "tree_nut"],
        "Nuts that grow on trees, such as almonds, cashews and walnuts.",
        "Flagged because tree nuts are on your allergen profile.",
    ),
    "peanut": _entry(
        "Peanut",
        ["peanut", "peanuts", "groundnut", "groundnuts", "ground nut", "monkey nut",
         "peanut butter", "peanut flour", "peanut oil", "arachis oil", "arachis"],
        ["peanut"],
        "A legume, one of the most common food allergens.",
        "Flagged because peanut is on your allergen profile.",
    ),
    "wheat": _entry(
        "Wheat",
        ["wheat", "wheat flour", "wheat starch", "wheat gluten", "wheat protein",
         "semolina", "durum", "spelt", "farina", "einkorn", "kamut", "bulgur", "couscous",
         "seitan", "maida", "atta", "suji", "sooji", "rava", "refined flour",
         "all purpose flour", "all-purpose flour", "plain flour", "breadcrumbs",
         "bread crumbs"],
        ["wheat", "gluten"],
        "A cereal grain containing gluten, found in many flours and baked goods.",
        "Flagged because wheat is on your allergen profile.",
    ),
    "gluten": _entry(
        "Gluten grains",
        ["gluten", "barley", "rye", "malt", "malt extract", "malted barley",
         "barley malt", "barley malt extract", "triticale"],
        ["gluten"],
        "Barley, rye and malt contain gluten even though they are not wheat.",
        "Flagged because gluten is on your allergen profile.",
    ),
    "soy": _entry(
        "Soy",
        ["soy", "soya", "soybean", "soybeans", "soy lecithin", "soya lecithin", "soy protein",
         "soy sauce", "tamari", "shoyu", "tofu", "edamame", "miso", "tempeh",
         "textured vegetable protein"],
        ["soy"],
        "A legume used whole or as protein, oil and lecithin.",
        "Flagged because soy is on your allergen profile.",
    ),
    "sesame": _entry(
        "Sesame",
        ["sesame", "tahini", "sesame oil", "sesame seeds", "gingelly", "benne"],
        ["sesame"],
        "Seeds and oil from the sesame plant.",
        "Flagged because sesame is on your allergen profile.",
    ),
}

# Phrases that contain an allergen word but are NOT that allergen.
# Occurrences inside these phrases are ignored for the listed ingredient id.
EXCLUDE_FOR = {
    "milk": ["cocoa butter", "shea butter", "peanut butter", "almond butter", "nut butter",
             "cashew butter", "butter bean", "coconut milk", "almond milk", "soy milk",
             "soya milk", "oat milk", "rice milk", "coconut cream", "cream of tartar",
             "milk thistle"],
}
