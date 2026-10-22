"""
SafeBite craving engine
=======================
Turns free text ("something crunchy but not too salty, dairy-free") into a
ranked list of SAFE swaps.

Pipeline (safety -> similarity -> usefulness, same promise the swaps page makes):
  1. parse()   text -> 12-axis taste vector, negations, diets, allergen exclusions
  2. filter    HARD-remove every catalog item that contains a profile/query allergen
               (or breaks a diet such as vegan / gluten-free)
  3. rank      cosine similarity over taste axes, penalty for avoided axes,
               small bonuses for food-name matches, meal type and diet prefs
  4. explain   match %, what it matched on, badges, ingredients, macros

Pure Python (no numpy / model weights needed), so it can't break on a missing
.npz file. Public API: search(), understand().
"""
from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

AXES = ["sweet", "salty", "savory", "spicy", "tangy", "crunchy",
        "creamy", "fizzy", "fruity", "chocolatey", "cold", "warm"]

NOTE = ("Allergen tags are curated for general guidance. Always check the label "
        "of the exact product you buy.")

# ---------------------------------------------------------------------------
# Allergen vocabulary
# ---------------------------------------------------------------------------
_CANON = {
    "milk": "dairy", "dairy": "dairy", "lactose": "dairy",
    "egg": "egg", "eggs": "egg",
    "fish": "fish",
    "shellfish": "shellfish", "crustacean": "shellfish", "shrimp": "shellfish",
    "tree-nut": "tree-nut", "tree nut": "tree-nut", "tree_nut": "tree-nut",
    "treenut": "tree-nut", "tree nuts": "tree-nut", "tree-nuts": "tree-nut",
    "peanut": "peanut", "peanuts": "peanut",
    "wheat": "wheat", "gluten": "wheat",
    "soy": "soy", "soya": "soy",
    "sesame": "sesame",
}
# words a user might type after "no / without / allergic to"
_QUERY_ALLERGENS = {
    "dairy": ["dairy"], "milk": ["dairy"], "lactose": ["dairy"],
    "egg": ["egg"], "eggs": ["egg"], "fish": ["fish"],
    "shellfish": ["shellfish"], "shrimp": ["shellfish"], "prawn": ["shellfish"],
    "nuts": ["tree-nut", "peanut"], "nut": ["tree-nut", "peanut"],
    "almond": ["tree-nut"], "almonds": ["tree-nut"], "cashew": ["tree-nut"],
    "cashews": ["tree-nut"], "walnut": ["tree-nut"], "walnuts": ["tree-nut"],
    "peanut": ["peanut"], "peanuts": ["peanut"],
    "gluten": ["wheat"], "wheat": ["wheat"],
    "soy": ["soy"], "soya": ["soy"], "sesame": ["sesame"],
}
_ALLERGEN_LABEL = {"dairy": "dairy", "egg": "egg", "fish": "fish",
                   "shellfish": "shellfish", "tree-nut": "tree nuts",
                   "peanut": "peanuts", "wheat": "gluten/wheat",
                   "soy": "soy", "sesame": "sesame"}


def normalize_allergens(tags: Optional[Iterable[str]]) -> Set[str]:
    out: Set[str] = set()
    for t in tags or []:
        k = str(t).strip().lower()
        out.add(_CANON.get(k, _CANON.get(k.replace("_", "-"), k)))
    return out


# ---------------------------------------------------------------------------
# Taste lexicon: word / phrase -> {axis: weight}
# ---------------------------------------------------------------------------
_LEX: Dict[str, Dict[str, float]] = {}


def _add(words: str, **axes: float) -> None:
    for w in words.split(","):
        w = w.strip().replace(" ", "_")
        if w:
            _LEX[w] = axes


# tastes
_add("sweet,sugary,sugar,syrupy,honeyed,candied,sugared", sweet=1)
_add("salty,salt,salted,briny", salty=1)
_add("savory,savoury,umami,meaty", savory=1)
_add("rich", savory=.4, creamy=.6)
_add("cheesy,cheese,nacho", savory=.8, creamy=.5, salty=.4)
_add("spicy,fiery,chili,chilli,peppery,jalapeno,sriracha,masala,peri,pepper,tikka", spicy=1)
_add("hot", warm=.6, spicy=.4)
_add("tangy,tart,sour,zesty,citrusy,lemony,limey,vinegary,pickle,pickled,tamarind", tangy=1)
_add("sweet and sour,sweet n sour", sweet=.6, tangy=.8)
_add("crunchy,crunch,crispy,crisp,crackly,snappy,crackers,cracker,crouton", crunchy=1)
_add("creamy,smooth,silky,velvety,custardy,custard,pudding,whipped,thick", creamy=1)
_add("fizzy,bubbly,sparkling,carbonated,fizz,seltzer", fizzy=1)
_add("soda,cola,coke,pop,sprite", fizzy=1, sweet=.7, cold=.5)
_add("fruity,fruit,fruits,berry,berries,mango,apple,orange,tropical,strawberry,grape,"
     "grapes,watermelon,banana,peach,pineapple,cherry,melon,citrus", fruity=1)
_add("lemon,lime", tangy=.8, fruity=.5)
_add("lemonade", tangy=.7, fruity=.4, cold=.4, sweet=.4)
_add("cold,icy,iced,frozen,chilled,cool,frosty,ice,freezing", cold=1)
_add("refreshing,refresh,thirsty,quench", cold=.7, tangy=.3)
_add("warm,warming,cozy,comforting,comfort,toasty,steaming,baked", warm=1)
_add("roasted", warm=.4, crunchy=.3)
_add("chocolate,chocolatey,cocoa,cacao,choco,mocha,nutella", chocolatey=1, sweet=.5)
_add("cinnamon,vanilla,maple", sweet=.4, warm=.4)
_add("nutty,peanut,peanuts,nut,nuts,peanut butter", savory=.4, creamy=.3, crunchy=.3, salty=.3)

# sweets & desserts
_add("dessert,desserts,treat,treats,pastry", sweet=1, creamy=.3)
_add("candy,candies,gummy,gummies,lollipop,jelly,marshmallow", sweet=1, fruity=.3)
_add("caramel,toffee", sweet=1, creamy=.3, warm=.2)
_add("cake,cupcake,muffin,donut,doughnut,waffle,pancake", sweet=.9, creamy=.3, warm=.3)
_add("cookie,cookies,biscuit,biscuits,wafer", sweet=.8, crunchy=.5)
_add("brownie,brownies,fudge", chocolatey=1, sweet=.7, creamy=.3, warm=.3)
_add("ice cream,icecream,gelato,sundae,kulfi,frozen yogurt,froyo", creamy=.9, sweet=.8, cold=1)
_add("milkshake,milk shake,shake,frappe", creamy=.9, sweet=.8, cold=.8)
_add("gulab jamun,jalebi,halwa,ladoo,laddu,barfi,rasgulla,payasam,kheer,mithai",
     sweet=1, creamy=.3, warm=.3)

# snacks & fast food
_add("chips,crisps", crunchy=1, salty=.9, savory=.3)
_add("popcorn", crunchy=.8, salty=.7)
_add("fries,fry,fried", crunchy=.7, salty=.8, savory=.5, warm=.5)
_add("nachos", crunchy=.8, salty=.7, savory=.6, creamy=.3, spicy=.3)
_add("pizza", savory=1, warm=.8, salty=.6, creamy=.4)
_add("burger,sandwich,wrap", savory=1, warm=.6, salty=.5)
_add("fried chicken,nuggets", crunchy=.9, savory=.9, salty=.6, warm=.6)
_add("mac and cheese,mac n cheese,macaroni", creamy=.9, savory=.8, warm=.9, salty=.4)

# meals & comfort food
_add("soup,stew,broth,porridge,oatmeal,khichdi,dal,curry,ramen,noodle,noodles,pasta,pulao,risotto",
     warm=.9, savory=.8)
_add("biryani", savory=.9, spicy=.8, warm=.9)
_add("dosa,idli,uttapam,upma", warm=.7, savory=.7)
_add("samosa,pakora,pakoda,bhaji,vada,kachori,bonda", crunchy=.8, savory=.8, spicy=.6, warm=.6)
_add("chaat,bhelpuri,panipuri,golgappa", tangy=.8, spicy=.6, crunchy=.7, savory=.6)

# drinks
_add("smoothie,lassi", creamy=.6, fruity=.5, cold=.7, sweet=.4)
_add("yogurt,yoghurt,curd,dahi", creamy=.7, tangy=.3, cold=.4)
_add("juice", fruity=.8, sweet=.6, cold=.5)
_add("tea,chai,coffee,latte,cappuccino", warm=.8)
_add("hot chocolate,hot cocoa", warm=1, chocolatey=1, creamy=.5, sweet=.6)

_PHRASES = sorted((k for k in _LEX if "_" in k), key=len, reverse=True)

_NEGATORS = {"not", "no", "never", "without", "less", "non", "isnt", "dont",
             "avoid", "low", "nothing", "hardly"}
_INTENS = {"very": 1.5, "extra": 1.5, "super": 1.5, "really": 1.4, "so": 1.3,
           "extremely": 1.7, "loads": 1.5, "lots": 1.4, "intensely": 1.6,
           "strongly": 1.5, "heavily": 1.4}
_DIM = {"slightly": .5, "bit": .5, "little": .5, "lightly": .5, "mildly": .5,
        "kinda": .6, "somewhat": .6, "subtly": .5, "hint": .5, "touch": .5}
_RESET = {"but", "and", "with", "plus", "or", "then"}
_CATEGORY_WORDS = {
    "drink": "drink", "drinks": "drink", "beverage": "drink", "sip": "drink", "sipping": "drink",
    "snack": "snack", "snacks": "snack", "munch": "snack", "munchies": "snack", "nibble": "snack",
    "dessert": "dessert", "desserts": "dessert", "pudding": "dessert",
    "meal": "meal", "dinner": "meal", "lunch": "meal", "breakfast": "meal", "main": "meal",
}
_DIET_PATTERNS = [
    (r"\bvegan\b", "vegan"),
    (r"\bvegetarian\b", "vegetarian"),
    (r"\bgluten[\s-]*free\b", "gluten_free"),
    (r"\b(?:dairy|lactose)[\s-]*free\b", "dairy_free"),
    (r"\bnut[\s-]*free\b", "nut_free"),
    (r"\bsugar[\s-]*free\b|\blow[\s-]*sugar\b|\bless sugar\b|\bno (?:added )?sugar\b|\bzero sugar\b|\bunsweetened\b", "low_sugar"),
    (r"\bhigh[\s-]*protein\b|\bprotein[\s-]*rich\b|\bmore protein\b", "high_protein"),
    (r"\blow[\s-]*cal(?:orie)?s?\b|\bfewer calories\b", "low_cal"),
    (r"\bhigh[\s-]*fib(?:er|re)\b|\bfib(?:er|re)[\s-]*rich\b", "high_fiber"),
]
_DIET_LABEL = {"vegan": "Vegan", "vegetarian": "Vegetarian", "gluten_free": "Gluten-free",
               "dairy_free": "Dairy-free", "nut_free": "Nut-free", "low_sugar": "Low sugar",
               "high_protein": "High protein", "low_cal": "Low calorie", "high_fiber": "High fiber"}
_EXCL_RE = re.compile(
    r"\b(?:no|without|free of|allergic to|avoid(?:ing)?|hold the|except|not)\s+(?:any\s+|the\s+)?([a-z]+)")
_ALLERGY_RE = re.compile(r"\b([a-z]+)\s+allerg(?:y|ies|ic)\b")


def _lookup(tok: str) -> Optional[Dict[str, float]]:
    if tok in _LEX:
        return _LEX[tok]
    if tok.endswith("es") and tok[:-2] in _LEX:
        return _LEX[tok[:-2]]
    if tok.endswith("s") and tok[:-1] in _LEX:
        return _LEX[tok[:-1]]
    return None


_STOP = {"something", "craving", "crave", "want", "need", "like", "anything", "food", "eat",
         "eating", "give", "make", "some", "that", "this", "just", "feel", "feeling", "mood",
         "the", "and", "for", "with", "but", "any", "can", "have", "get", "kind", "type",
         "thing", "stuff", "very", "too", "also", "instead", "maybe", "good", "nice", "best"}
_VOCAB = sorted(set(_LEX) | set(_CATEGORY_WORDS) | set(_QUERY_ALLERGENS) - {"nut"})


def _correct(tok: str) -> Optional[str]:
    if len(tok) < 4 or tok in _STOP or "_" in tok:
        return None
    m = difflib.get_close_matches(tok, _VOCAB, n=1, cutoff=0.84)
    return m[0] if m else None


def _singular(tok: str) -> str:
    return tok[:-1] if tok.endswith("s") and len(tok) > 3 else tok


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
@dataclass
class Parsed:
    vec: Dict[str, float] = field(default_factory=dict)
    exclusions: Set[str] = field(default_factory=set)
    diets: Set[str] = field(default_factory=set)
    categories: Set[str] = field(default_factory=set)
    tokens: List[str] = field(default_factory=list)
    recognized: int = 0
    corrected: Dict[str, str] = field(default_factory=dict)

    @property
    def has_signal(self) -> bool:
        return self.recognized > 0 or bool(self.categories)


def parse(query: str) -> Parsed:
    p = Parsed(vec={a: 0.0 for a in AXES})
    text = (query or "").lower().replace("&", " and ")

    for pat, name in _DIET_PATTERNS:
        if re.search(pat, text):
            p.diets.add(name)
            text = re.sub(pat, " ", text)
    if "nut_free" in p.diets:
        p.exclusions |= {"tree-nut", "peanut"}
    if "dairy_free" in p.diets:
        p.exclusions.add("dairy")
    if "gluten_free" in p.diets:
        p.exclusions.add("wheat")

    def _excl(m: "re.Match") -> str:
        word = m.group(1)
        if word in _QUERY_ALLERGENS:
            p.exclusions.update(_QUERY_ALLERGENS[word])
            return " "
        return m.group(0)

    text = _EXCL_RE.sub(_excl, text)

    def _allergy(m: "re.Match") -> str:
        word = m.group(1)
        if word in _QUERY_ALLERGENS:
            p.exclusions.update(_QUERY_ALLERGENS[word])
            return " "
        return m.group(0)

    text = _ALLERGY_RE.sub(_allergy, text)

    for ph in _PHRASES:
        text = text.replace(ph.replace("_", " "), ph)

    p.tokens = re.findall(r"[a-z_']+", text)
    neg, mult = 0, 1.0
    for tok in p.tokens:
        if tok in _RESET:
            neg, mult = 0, 1.0
            continue
        if tok in _NEGATORS:
            neg = 3
            continue
        if tok in _INTENS:
            mult = _INTENS[tok]
            continue
        if tok in _DIM:
            mult = _DIM[tok]
            continue
        if tok in _CATEGORY_WORDS:
            p.categories.add(_CATEGORY_WORDS[tok])
        axes = _lookup(tok)
        if axes is None and tok not in _STOP and tok not in _CATEGORY_WORDS:
            fix = _correct(tok)
            if fix:
                p.corrected[tok] = fix
                tok = fix
                axes = _lookup(tok)
                if tok in _CATEGORY_WORDS:
                    p.categories.add(_CATEGORY_WORDS[tok])
        if axes is None:
            neg = max(0, neg - 1)
            continue
        sign = -0.8 if neg else 1.0
        for a, w in axes.items():
            p.vec[a] += sign * w * mult
        p.recognized += 1
        mult = 1.0
    for a in AXES:
        p.vec[a] = max(-1.5, min(1.5, p.vec[a]))
    return p


def _labels(p: Parsed, extra_diets: Iterable[str] = ()) -> List[str]:
    out: List[str] = []
    for a in sorted(AXES, key=lambda x: -abs(p.vec[x])):
        v = p.vec[a]
        if v > 0.2:
            out.append(a.capitalize())
        elif v < -0.2:
            out.append("Not " + a)
    for c in sorted(p.categories):
        out.append(c.capitalize())
    for d in sorted(set(p.diets) | set(extra_diets)):
        out.append(_DIET_LABEL.get(d, d))
    for x in sorted(p.exclusions):
        out.append("No " + _ALLERGEN_LABEL.get(x, x))
    seen, uniq = set(), []
    for o in out:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    return uniq


# ---------------------------------------------------------------------------
# Catalog. Compact builder:
#   axes "sweet:.7,cold:.9" | allergens "soy,tree-nut" | d: v=vegan g=gluten-free
#   t=vegetarian (not vegan) | ingredients "a|b" | nutr "kcal/protein/sugar/fiber"
# ---------------------------------------------------------------------------
@dataclass
class Item:
    id: str
    name: str
    cat: str
    vec: List[float]
    allergens: Set[str]
    diets: Set[str]
    ingredients: List[str]
    kcal: int
    protein: float
    sugar: float
    fiber: float
    delta: str
    why: str
    kw: Set[str]


_ADJ_KW = {"fizzy", "spicy", "cheesy", "refreshing", "comfort", "iced", "drink", "fried", "dessert", "masala"}


def _i(id, name, cat, axes, allergens, d, ingredients, nutr, delta, why, kw="") -> Item:
    v = {a: 0.0 for a in AXES}
    for pair in axes.split(","):
        k, val = pair.split(":")
        v[k.strip()] = float(val)
    kcal, prot, sug, fib = (float(x) for x in nutr.split("/"))
    return Item(id, name, cat, [v[a] for a in AXES],
                {a for a in allergens.split(",") if a}, set(d),
                ingredients.split("|"), int(kcal), prot, sug, fib, delta, why,
                {w for w in kw.split() if w not in _ADJ_KW})


CATALOG: List[Item] = [
    # ---- original 12 (ids kept so existing links keep working)
    _i("sw1", "Sparkling Apple", "drink", "fizzy:.9,sweet:.6,fruity:.6,cold:.6", "", "vg",
       "sparkling water|apple juice", "45/0/9/0", "-12g sugar, same fizz",
       "Same carbonated snap as soda, without the added sugar.", "soda cola fizzy drink"),
    _i("sw2", "Coconut Yogurt Bark", "dessert", "sweet:.6,crunchy:.6,creamy:.8,fruity:.2,cold:.3", "", "vg",
       "coconut yogurt|freeze-dried berries|pumpkin seeds|maple syrup", "160/3/9/3", "0g dairy, +3g fiber",
       "Dairy-free but keeps the creamy-crunchy combo.", "chocolate bark yogurt"),
    _i("sw3", "Roasted Chickpeas", "snack", "salty:.8,crunchy:.9,savory:.5", "", "vg",
       "chickpeas|olive oil|sea salt|paprika", "130/6/1/5", "+4g protein, nut-free",
       "Same salty crunch as peanuts, without the allergen.", "peanuts chips namkeen"),
    _i("sw4", "Herb Rice Crackers", "snack", "salty:.6,crunchy:.85,savory:.7", "", "vg",
       "rice flour|herbs|sunflower oil|sea salt", "110/2/0/1", "0g gluten, same crunch",
       "Gluten-free swap that keeps the crunchy-savory profile.", "crackers biscuits"),
    _i("sw5", "Frozen Grapes", "dessert", "sweet:.8,fruity:.9,cold:.9", "", "vg",
       "grapes", "60/0/14/1", "-18g sugar vs candy",
       "Scratches the same sweet-cold itch as candy or ice cream.", "candy sweets"),
    _i("sw6", "Popped Sorghum", "snack", "salty:.5,crunchy:.8,savory:.3", "", "vg",
       "sorghum|olive oil|sea salt", "100/3/0/3", "+3g fiber, nut-free",
       "Light, airy crunch that scratches a popcorn craving.", "popcorn"),
    _i("sw7", "Mango Sorbet", "dessert", "sweet:.85,fruity:.9,cold:.9", "", "vg",
       "mango|lime|cane sugar", "110/1/22/2", "0g dairy, -8g fat",
       "Fruity and cold enough to replace ice cream cravings.", "ice_cream kulfi gelato"),
    _i("sw8", "Salted Roasted Edamame", "snack", "salty:.75,crunchy:.55,savory:.4", "soy", "vg",
       "edamame|sea salt", "130/12/2/5", "+8g protein, gluten-free",
       "Salty, poppable snacking without dairy, gluten or nuts.", "chips peanuts"),
    _i("sw9", "Kefir Smoothie", "drink", "sweet:.5,creamy:.9,fruity:.3,cold:.7", "dairy", "gt",
       "kefir|banana|berries", "140/7/14/2", "+6g protein, probiotic",
       "Creamy and cold, closer to a milkshake than a diet swap.", "milkshake lassi shake"),
    _i("sw10", "Tamari Almonds", "snack", "salty:.7,crunchy:.7,savory:.8", "tree-nut,soy", "v",
       "almonds|tamari", "170/6/1/3", "+5g protein",
       "Savory-salty crunch with a nutty depth, not just plain nuts.", "nuts namkeen"),
    _i("sw11", "Watermelon Ice Pops", "dessert", "sweet:.75,fruity:.85,cold:.95", "", "vg",
       "watermelon|lime", "40/1/8/0", "-14g sugar, all natural",
       "Cold and sweet without the syrup-heavy base of most ice pops.", "ice popsicle"),
    _i("sw12", "Miso Rice Crisps", "snack", "salty:.65,crunchy:.8,savory:.85", "soy", "v",
       "rice|miso|sunflower oil", "120/2/1/1", "0g gluten, umami-forward",
       "Savory, crunchy, and salty enough to replace chips.", "chips crisps"),
    # ---- crunchy / salty / savory snacks
    _i("sw13", "Baked Apple Chips", "snack", "sweet:.7,crunchy:.85,fruity:.7", "", "vg",
       "apples|cinnamon", "80/0/13/3", "-10g sugar vs candy",
       "Sweet crunch that replaces cookies and candy.", "cookies chips"),
    _i("sw14", "Seaweed Rice Crisps", "snack", "salty:.75,crunchy:.9,savory:.8", "sesame", "vg",
       "rice|nori|sunflower oil|sesame oil", "90/2/0/1", "-60 kcal vs chips",
       "Shatter-crisp and salty like chips, much lighter.", "chips crisps"),
    _i("sw15", "Spiced Lentil Chips", "snack", "salty:.7,crunchy:.85,savory:.8,spicy:.6", "", "vg",
       "lentil flour|paprika|chili|sunflower oil", "120/5/1/2", "+5g protein, nut-free",
       "Crispy, savory and bold, like a spicy chip.", "chips namkeen masala"),
    _i("sw16", "Nutritional-Yeast Popcorn", "snack", "salty:.6,crunchy:.8,savory:.75,creamy:.2", "", "vg",
       "popcorn|nutritional yeast|olive oil|sea salt", "100/4/0/4", "0g dairy, +4g fiber",
       "A cheesy-tasting popcorn with no cheese at all.", "popcorn cheesy nachos cheese"),
    _i("sw17", "Cassava Chips & Guacamole", "snack", "salty:.7,crunchy:.85,creamy:.5,savory:.6,tangy:.4", "", "vg",
       "cassava|avocado|lime|salt", "160/2/1/4", "0g gluten, nut-free",
       "Chips and a creamy dip, the same scoop-and-crunch fix.", "nachos chips dip"),
    _i("sw18", "Pumpkin Seed Trail Mix", "snack", "salty:.5,crunchy:.8,sweet:.4,savory:.4", "", "vg",
       "pumpkin seeds|sunflower seeds|dried cranberries", "170/7/6/3", "+7g protein, nut-free",
       "Sweet-salty crunch you can graze on, no nuts.", "nuts trail mix"),
    _i("sw19", "Seed & Yeast Crackers", "snack", "savory:.8,salty:.7,crunchy:.8,creamy:.2", "", "vg",
       "flax seeds|sunflower seeds|nutritional yeast|sea salt", "110/5/0/4", "0g dairy, +4g fiber",
       "Cheesy-savory crackers without cheese or gluten.", "cheese crackers cheesy"),
    _i("sw20", "Cheesy Kale Chips", "snack", "savory:.85,salty:.6,crunchy:.85", "", "vg",
       "kale|nutritional yeast|olive oil|garlic", "90/6/1/3", "+6g protein, 0g dairy",
       "Crunchy, cheesy-tasting greens that feel like a chip.", "chips cheesy"),
    _i("sw21", "Baked Falafel Bites", "snack", "savory:.8,crunchy:.6,warm:.5,spicy:.3", "", "vg",
       "chickpeas|parsley|cumin|garlic", "170/8/2/6", "+8g protein, baked not fried",
       "Warm, herby and crisp-edged, the baked answer to pakoras.", "pakora vada fried"),
    _i("sw22", "Jalapeno Kettle Chips", "snack", "crunchy:.95,salty:.85,spicy:.8,savory:.6", "", "vg",
       "potatoes|sunflower oil|jalapeno|salt", "150/2/1/1", "0g dairy, simple 4 ingredients",
       "The real chip crunch with a spicy kick.", "chips spicy"),
    # ---- spicy / bold / street food
    _i("sw23", "Chili-Lime Mango Strips", "snack", "spicy:.7,sweet:.6,tangy:.8,fruity:.8", "", "vg",
       "dried mango|chili|lime", "90/1/16/2", "-8g sugar vs candy",
       "Sweet, sour and spicy, a chaat-style hit without frying.", "chaat candy"),
    _i("sw24", "Sriracha Roasted Chickpeas", "snack", "spicy:.9,crunchy:.85,salty:.7,savory:.6", "", "vg",
       "chickpeas|sriracha|olive oil|salt", "135/6/1/5", "+6g protein, baked",
       "Crispy, hot and snackable.", "spicy chips wings"),
    _i("sw25", "Chickpea Chaat Bowl", "meal", "tangy:.85,spicy:.6,crunchy:.6,savory:.7,salty:.4", "", "vg",
       "chickpeas|onion|tomato|tamarind|chaat masala|cucumber", "190/9/6/7", "+9g protein, no frying",
       "All the tang and crunch of street chaat, no deep-fryer.", "chaat bhel panipuri samosa"),
    _i("sw26", "Veggie Fried Rice, Chili Crisp", "meal", "warm:.9,savory:.85,spicy:.7,salty:.6", "soy,sesame", "v",
       "rice|mixed vegetables|soy sauce|chili crisp|garlic", "280/7/4/3", "+3g fiber",
       "Hot, savory and spicy in a bowl.", "biryani noodles fried rice"),
    _i("sw27", "Veggie Biryani Bowl", "meal", "savory:.85,spicy:.7,warm:.9,salty:.4", "", "vg",
       "basmati rice|mixed vegetables|biryani spices|onion|mint", "290/7/4/4", "-20% fat vs restaurant",
       "Fragrant, spiced and warm like the real thing, lighter on oil.", "biryani pulao"),
    # ---- warm & comforting
    _i("sw28", "Warm Oat Porridge", "meal", "sweet:.4,creamy:.8,warm:.95", "", "v",
       "oats|water|banana|cinnamon", "150/5/6/4", "+4g fiber, 0g dairy",
       "Warm, creamy and soothing.", "porridge oatmeal comfort"),
    _i("sw29", "Roasted Tomato Soup", "meal", "savory:.8,warm:.95,tangy:.5,creamy:.5", "", "vg",
       "tomatoes|olive oil|onion|garlic|basil", "110/3/8/3", "-60 kcal vs cream soup",
       "A warm, savory bowl that feels like comfort food.", "soup comfort"),
    _i("sw30", "Cinnamon Sweet Potato Mash", "meal", "sweet:.6,creamy:.8,warm:.9", "", "vg",
       "sweet potato|cinnamon|olive oil", "130/2/7/4", "0g dairy, +4g fiber",
       "Creamy, sweet and cozy, like mashed potato for dessert.", "mash comfort"),
    _i("sw31", "Coconut Lentil Dal", "meal", "warm:.95,savory:.8,spicy:.5,creamy:.7", "", "vg",
       "red lentils|coconut milk|turmeric|cumin|tomato", "210/12/3/8", "+12g protein, 0g dairy",
       "Warm, creamy, gently spiced comfort in a bowl.", "dal curry khichdi comfort"),
    _i("sw32", "Chicken & Rice Soup", "meal", "warm:.95,savory:.85,salty:.5", "", "g",
       "chicken|rice|carrot|celery|broth", "180/14/3/2", "+14g protein",
       "The classic warm, savory comfort bowl.", "soup comfort"),
    _i("sw33", "Pumpkin Rice Pasta", "meal", "creamy:.8,savory:.7,warm:.9", "", "vg",
       "rice pasta|pumpkin|olive oil|nutritional yeast|sage", "280/7/5/4", "0g gluten, 0g dairy",
       "Creamy, cheesy-feeling pasta with no dairy or gluten.", "mac_and_cheese pasta macaroni"),
    _i("sw34", "Baked Cinnamon Apple", "dessert", "warm:.9,sweet:.7,fruity:.7", "", "vg",
       "apple|cinnamon|maple syrup", "110/0/22/4", "-15g sugar vs pie",
       "Warm, sweet and spiced like apple pie.", "pie cake dessert"),
    # ---- chocolate & sweet
    _i("sw35", "Dark Chocolate Strawberries", "dessert", "sweet:.8,chocolatey:.9,fruity:.8", "", "vg",
       "dark chocolate 70%|strawberries", "120/2/12/3", "-8g sugar vs milk chocolate",
       "Chocolatey and fruity for a dessert fix.", "chocolate candy"),
    _i("sw36", "Avocado Chocolate Pudding", "dessert", "chocolatey:.9,creamy:.95,sweet:.7,cold:.6", "", "vg",
       "avocado|cacao|maple syrup|coconut milk", "150/3/10/6", "0g dairy, +6g fiber",
       "Thick, creamy and chocolatey without milk.", "pudding mousse chocolate"),
    _i("sw37", "Cacao Banana Nice Cream", "dessert", "chocolatey:.8,sweet:.8,cold:.95,creamy:.8", "", "vg",
       "frozen banana|cacao", "110/2/16/3", "0g dairy, 2 ingredients",
       "Tastes like chocolate ice cream, made of fruit.", "ice_cream chocolate"),
    _i("sw38", "Date & Cacao Bites", "dessert", "chocolatey:.8,sweet:.8,creamy:.3", "", "vg",
       "dates|sunflower seed butter|cacao|coconut", "120/3/12/3", "nut-free, no refined sugar",
       "Chewy and chocolatey like a truffle.", "brownie truffle candy chocolate"),
    _i("sw39", "Oat Banana Cookies", "dessert", "sweet:.6,crunchy:.3,warm:.4,chocolatey:.4", "", "v",
       "banana|oats|dairy-free chocolate chips|cinnamon", "120/3/9/3", "0g dairy, 4 ingredients",
       "Soft, lightly sweet and cookie-like.", "cookies biscuits"),
    _i("sw40", "Coconut Chia Pudding", "dessert", "creamy:.85,sweet:.5,cold:.7", "", "vg",
       "chia seeds|coconut milk|vanilla|berries", "180/4/6/8", "0g dairy, +8g fiber",
       "Cold, creamy and spoonable.", "pudding custard"),
    _i("sw41", "Frozen Yogurt Bites", "dessert", "creamy:.8,sweet:.6,cold:.9,fruity:.5", "dairy", "gt",
       "greek yogurt|berries|honey", "70/4/7/1", "+4g protein, -10g sugar",
       "Cold, creamy and sweet like ice cream.", "ice_cream froyo"),
    # ---- drinks
    _i("sw42", "Kombucha Spritz", "drink", "fizzy:.9,tangy:.7,fruity:.5,cold:.6,sweet:.3", "", "vg",
       "kombucha|sparkling water|lemon", "30/0/3/0", "-15g sugar, probiotic",
       "Fizzy and tangy with a fraction of the sugar of soda.", "soda cola fizzy"),
    _i("sw43", "Cucumber Lime Cooler", "drink", "cold:.9,fruity:.6,tangy:.6,fizzy:.4", "", "vg",
       "cucumber|lime|mint|sparkling water", "15/0/1/0", "-20g sugar",
       "Cold, fruity and refreshing without the sugar.", "refreshing juice lemonade"),
    _i("sw44", "Iced Hibiscus Tea", "drink", "tangy:.7,fruity:.6,cold:.9,sweet:.3", "", "vg",
       "hibiscus|water|lime|honey-free sweetener", "10/0/2/0", "-25g sugar vs juice",
       "Tart, ruby-red and refreshing.", "juice iced tea refreshing"),
    _i("sw45", "Hot Cacao with Coconut Milk", "drink", "warm:.95,chocolatey:.9,creamy:.7,sweet:.6", "", "vg",
       "cacao|coconut milk|maple syrup", "130/2/9/2", "0g dairy",
       "Hot chocolate comfort without milk.", "hot_chocolate cocoa"),
    _i("sw46", "Ginger Lemon Tea", "drink", "warm:.9,tangy:.6,sweet:.3,spicy:.3", "", "vg",
       "ginger|lemon|hot water|honey-free sweetener", "15/0/3/0", "-20g sugar vs chai latte",
       "Warm, zesty and soothing.", "chai tea coffee"),
    _i("sw47", "Mango Lassi", "drink", "creamy:.85,sweet:.7,fruity:.8,cold:.8", "dairy", "gt",
       "yogurt|mango|cardamom", "150/6/20/1", "+6g protein",
       "Creamy, cold and fruity.", "smoothie milkshake lassi"),
    _i("sw48", "Sparkling Lemonade", "drink", "fizzy:.9,tangy:.9,sweet:.5,cold:.7,fruity:.6", "", "vg",
       "sparkling water|lemon juice|stevia", "20/0/2/0", "-24g sugar vs soda",
       "Fizzy, zesty and cold.", "soda lemonade sprite"),
]
_BY_ID = {it.id: it for it in CATALOG}


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: List[float]) -> float:
    return math.sqrt(_dot(a, a))


def _diets_from_prefs(prefs) -> Set[str]:
    out: Set[str] = set()
    if not isinstance(prefs, dict):
        return out
    raw = prefs.get("diets") or prefs.get("diet") or prefs.get("dietary") or []
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, (list, tuple, set)):
        for r in raw:
            k = str(r).lower().replace("-", "_").replace(" ", "_")
            if k in {"vegan", "vegetarian", "gluten_free", "dairy_free"}:
                out.add(k)
    return out


def _item_ok_for_diets(it: Item, diets: Set[str]) -> bool:
    if "vegan" in diets and "v" not in it.diets:
        return False
    if "vegetarian" in diets and not ({"v", "t"} & it.diets):
        return False
    if "gluten_free" in diets and "g" not in it.diets:
        return False
    if "dairy_free" in diets and "dairy" in it.allergens:
        return False
    return True


def _badges(it: Item) -> List[str]:
    b = []
    if "v" in it.diets:
        b.append("Vegan")
    elif "t" in it.diets:
        b.append("Vegetarian")
    if "g" in it.diets:
        b.append("Gluten-free")
    if "dairy" not in it.allergens:
        b.append("Dairy-free")
    if it.protein >= 6:
        b.append("High protein")
    if it.sugar <= 3:
        b.append("Low sugar")
    if it.fiber >= 4:
        b.append("High fiber")
    return b


def _simple(it: Item) -> bool:
    return len(it.ingredients) <= 4


def _macro_friendly(it: Item) -> bool:
    return (it.sugar <= 6 and (it.protein >= 4 or it.fiber >= 3)) or it.kcal <= 90


def _serialize(it: Item, score: float, matched: List[str]) -> dict:
    badges = _badges(it)
    return {
        "id": it.id, "name": it.name, "category": it.cat,
        "macroDelta": it.delta, "why": it.why,
        "ingredients": it.ingredients,
        "macros": {"kcal": it.kcal, "protein": it.protein,
                   "sugar": it.sugar, "fiber": it.fiber},
        "allergens": sorted(it.allergens),
        "badges": badges, "tags": badges,
        "match": max(1, min(99, round(score * 100))),
        "matchedOn": matched,
        "simple": _simple(it), "macroFriendly": _macro_friendly(it),
    }


def understand(query: str) -> dict:
    """Light endpoint for the live 'we heard...' preview. No allergen data used."""
    p = parse(query)
    return {"understood": _labels(p), "recognized": p.has_signal}


def search(query: str, allergens: Optional[Iterable[str]] = None,
           prefs: Optional[dict] = None, limit: int = 12) -> dict:
    p = parse(query)
    blocked = normalize_allergens(allergens) | p.exclusions
    diets = p.diets | _diets_from_prefs(prefs)

    # 1. SAFETY: hard filter ------------------------------------------------
    eligible: List[Item] = []
    excluded_count, excluded_by = 0, set()
    for it in CATALOG:
        hit = it.allergens & blocked
        if hit:
            excluded_count += 1
            excluded_by |= hit
            continue
        if not _item_ok_for_diets(it, diets):
            continue
        eligible.append(it)

    # 2. SIMILARITY ---------------------------------------------------------
    pos = [max(0.0, p.vec[a]) for a in AXES]
    neg = [max(0.0, -p.vec[a]) for a in AXES]
    pos_n, neg_sum = _norm(pos), sum(neg)
    toks = [p.corrected.get(t, t) for t in p.tokens]
    qtok = {_singular(t) for t in toks} | set(toks)

    ranked = []
    for it in eligible:
        sim = _dot(pos, it.vec) / (pos_n * _norm(it.vec)) if pos_n else 0.5
        pen = _dot(neg, it.vec) / neg_sum if neg_sum else 0.0
        score = sim * (1 - 0.6 * min(1.0, pen))
        matched = [a.capitalize() for a, w, iv in zip(AXES, pos, it.vec) if w >= .3 and iv >= .5]
        kw_hit = sorted(qtok & it.kw)
        if kw_hit:
            score += 0.15
            matched = [f"Replaces {kw_hit[0].replace('_', ' ')}"] + matched
        if it.cat in p.categories:
            score += 0.12
        if "low_sugar" in p.diets and it.sugar <= 5:
            score += 0.08
            matched.append("Low sugar")
        if "high_protein" in p.diets and it.protein >= 6:
            score += 0.08
            matched.append("High protein")
        if "low_cal" in p.diets and it.kcal <= 120:
            score += 0.08
        if "high_fiber" in p.diets and it.fiber >= 4:
            score += 0.08
        ranked.append((min(score, 0.99), it, matched))
    ranked.sort(key=lambda r: (-r[0], r[1].name))

    # 3. fallback when nothing was understood --------------------------------
    fallback = None
    if not p.has_signal and not any(it.kw & qtok for it in eligible):
        fallback = ("We didn't recognise that craving, so here are popular safe picks. "
                    "Try a taste (sweet, salty, spicy), a texture (crunchy, creamy) or a food (chips, ice cream).")
        ranked = [(0.4, it, []) for it in sorted(eligible, key=lambda i: (not _simple(i), i.name))]

    pool = [r for r in ranked if r[0] >= 0.2] or ranked[:3]
    if len(pool) < 3:
        pool = ranked[:3]
    results = [_serialize(it, s, m) for s, it, m in pool[:limit]]

    return {
        "query": query,
        "understood": _labels(p, diets - p.diets),
        "excluded": {"count": excluded_count,
                     "by": sorted(_ALLERGEN_LABEL.get(x, x) for x in excluded_by)},
        "fallback": fallback,
        "didYouMean": ({w: c for w, c in p.corrected.items()} or None),
        "note": NOTE,
        "results": results,
    }