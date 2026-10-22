// =========================================================
// MOCK DATA — stand-in for the real backend (OCR/detector/
// VAE) until it's wired up. Shape matches what Person C's
// swap pages and the real API will eventually return, so
// swapping this out later is a drop-in replacement, not a
// rewrite:
//
// scan object: { scanId, productName, date, verdict, flaggedIngredients: [{id, name}] }
// verdict is one of: "safe" | "flagged" | "unclear"
// =========================================================

const MOCK_SCANS = [
  {
    scanId: "s1",
    productName: "Neon Soda",
    date: "Aug 1",
    verdict: "flagged",
    flaggedIngredients: [
      { id: "red40", name: "Red 40" },
      { id: "hfcs", name: "High Fructose Corn Syrup" }
    ]
  },
  {
    scanId: "s2",
    productName: "Sparkling Apple",
    date: "Jul 30",
    verdict: "safe",
    flaggedIngredients: []
  },
  {
    scanId: "s3",
    productName: "Mystery Granola Bar",
    date: "Jul 28",
    verdict: "unclear",
    flaggedIngredients: [
      { id: "natural-flavor", name: "Natural Flavor" }
    ]
  },
  {
    scanId: "s4",
    productName: "Herb Crackers",
    date: "Jul 26",
    verdict: "safe",
    flaggedIngredients: []
  }
];

const MOCK_INGREDIENTS = {
  "red40": {
    name: "Red 40",
    plainLanguage: "A synthetic dye made from petroleum, used to make foods look redder than the ingredients actually would on their own.",
    aliases: ["FD&C Red No. 40", "Allura Red AC", "E129"],
    whyForYou: "Flagged because it's on your allergen/sensitivity list — some people react to synthetic dyes even without a formal allergy."
  },
  "hfcs": {
    name: "High Fructose Corn Syrup",
    plainLanguage: "A corn-derived sweetener that's cheaper than sugar and shows up in sodas, sauces, and most packaged snacks.",
    aliases: ["HFCS", "Corn Sugar", "Glucose-Fructose Syrup"],
    whyForYou: "Flagged because it matches the 'added sugar' preference in your profile, not because it's inherently unsafe."
  },
  "natural-flavor": {
    name: "Natural Flavor",
    plainLanguage: "A catch-all term for flavor compounds derived from real plant or animal sources — the actual recipe behind it is proprietary and not disclosed on the label.",
    aliases: ["Natural Flavoring", "Natural Flavor Blend"],
    whyForYou: "Flagged as 'unclear' because the exact source can't be determined from the label alone — it could contain trace allergens without saying so."
  }
};

// Look up a scan by id, falling back to the first mock scan
// so every page still renders something sensible even with
// no/garbage query params.
function getScanById(id){
  return MOCK_SCANS.find(s => s.scanId === id) || MOCK_SCANS[0];
}

function getIngredientById(id){
  return MOCK_INGREDIENTS[id] || null;
}