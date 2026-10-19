/* =========================================================
   SAFEBITE — BASE SCRIPT
   Provides safe fallbacks so the page still looks correct
   even when illustration/appy/footer-prop image files are
   missing, plus a couple of small always-on touches.
   ========================================================= */

(function () {
  "use strict";

  /* ---------- emoji fallback lookup ---------- */
  function fallbackEmoji(el) {
    var hint = ((el.id || "") + " " + (el.alt || "") + " " + (el.getAttribute("src") || "")).toLowerCase();
    var table = [
      ["vase", "💐"], ["wineglass", "🍷"], ["bottle", "🍾"], ["fork", "🍴"],
      ["knife", "🔪"], ["spoon", "🥄"], ["sausage", "🌭"], ["candle", "🕯️"],
      ["saltpepper", "🧂"], ["cheese", "🧀"], ["olives", "🫒"], ["jar", "🍯"],
      ["bread", "🍞"], ["charcuterie", "🍽️"], ["hat", "🎩"],
      ["think", "🤔"], ["read", "📖"], ["eat", "🍽️"], ["sit", "🪑"], ["meditate", "🧘"],
      ["dirty", "🚫"], ["appy", "👻"]
    ];
    for (var i = 0; i < table.length; i++) {
      if (hint.indexOf(table[i][0]) !== -1) return table[i][1];
    }
    return "🎨";
  }

  /* ---------- <img> fallback: swap broken images for a themed chip ---------- */
  function wireImgFallback(img) {
    if (img.dataset.fallbackWired) return;
    img.dataset.fallbackWired = "1";
    img.addEventListener("error", function onErr() {
      img.removeEventListener("error", onErr);
      img.classList.add("img-fallback");
      var chip = document.createElement("span");
      chip.className = "img-fallback-chip";
      chip.setAttribute("aria-hidden", "true");
      chip.textContent = fallbackEmoji(img);
      if (img.parentNode) img.parentNode.replaceChild(chip, img);
    });
  }

  document.querySelectorAll("img").forEach(wireImgFallback);
})();
