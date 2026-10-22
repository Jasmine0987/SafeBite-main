"""
Craving-Signature VAE
======================
This is the ONE model in the backend that's actually trained end-to-end
right now (see the note at the bottom of this file for why this one was
picked over the others described in the report).

What it replaces: the old `rank_swaps()` in main.py scored candidates by
literal tag-string overlap between the query and each swap item — not
learned, not really "deep learning," just set intersection.

What this does instead:
  1. Each swap candidate is described by a small structured
     "craving-signature" vector — continuous scores (0-1) across sensory
     axes: sweet, salty, crunchy, fizzy, creamy, fruity, cold, savory.
  2. A tiny VAE (numpy, no torch/tensorflow dependency — deliberately
     lightweight so it trains in under a second on this laptop-class
     dataset and has zero extra install burden) is trained to encode
     those vectors into a low-dimensional latent space and reconstruct
     them.
  3. At inference time, both a user's craving text and every candidate
     item are mapped into that learned latent space, and ranking is done
     by distance in the *learned* space rather than raw tag overlap.

Honesty note: this is a genuinely trained generative model (encoder,
reparameterization trick, decoder, reconstruction + KL loss, gradient
descent), but the dataset is small and hand-authored (12 items), so treat
the *ranking quality* as illustrative of the technique, not as a validated
recommendation engine. The report should describe it exactly this way.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

import numpy as np

WEIGHTS_PATH = Path(__file__).parent / "craving_vae_weights.npz"

# ---------------------------------------------------------------------------
# Craving-signature axes and the swap catalog
# ---------------------------------------------------------------------------
AXES = ["sweet", "salty", "crunchy", "fizzy", "creamy", "fruity", "cold", "savory"]

# id, name, macroDelta, why, and a hand-authored craving-signature vector
# over AXES (0-1 continuous, not one-hot — this is what makes it worth
# learning a continuous embedding instead of just matching tags).
SWAP_CATALOG = [
    {"id": "sw1", "name": "Sparkling Apple", "macroDelta": "-12g sugar, same fizz",
     "why": "Same carbonated snap as soda, without the added sugar.",
     "vec": [0.7, 0.05, 0.1, 0.9, 0.0, 0.6, 0.6, 0.0]},
    {"id": "sw2", "name": "Coconut Yogurt Bark", "macroDelta": "0g dairy, +3g fiber",
     "why": "Dairy-free but keeps the creamy-crunchy combo.",
     "vec": [0.6, 0.1, 0.6, 0.0, 0.8, 0.2, 0.3, 0.1]},
    {"id": "sw3", "name": "Roasted Chickpeas", "macroDelta": "+4g protein, nut-free",
     "why": "Same salty crunch as peanuts, without the allergen.",
     "vec": [0.05, 0.8, 0.9, 0.0, 0.0, 0.0, 0.0, 0.5]},
    {"id": "sw4", "name": "Herb Rice Crackers", "macroDelta": "0g gluten, same crunch",
     "why": "Gluten-free swap that keeps the crunchy-savory profile.",
     "vec": [0.0, 0.6, 0.85, 0.0, 0.05, 0.0, 0.0, 0.7]},
    {"id": "sw5", "name": "Frozen Grapes", "macroDelta": "-18g sugar, all natural",
     "why": "Scratches the same sweet-cold itch as candy or ice cream.",
     "vec": [0.8, 0.0, 0.1, 0.0, 0.0, 0.9, 0.9, 0.0]},
    {"id": "sw6", "name": "Popped Sorghum", "macroDelta": "+3g fiber, nut-free",
     "why": "Light, airy crunch that scratches a popcorn craving.",
     "vec": [0.1, 0.5, 0.8, 0.0, 0.1, 0.0, 0.0, 0.3]},
    {"id": "sw7", "name": "Mango Sorbet", "macroDelta": "0g dairy, -8g fat",
     "why": "Fruity and cold enough to replace ice cream cravings.",
     "vec": [0.85, 0.0, 0.0, 0.1, 0.1, 0.9, 0.9, 0.0]},
    {"id": "sw8", "name": "Salted Roasted Edamame", "macroDelta": "+8g protein, gluten-free",
     "why": "Salty, poppable snacking without the common allergens.",
     "vec": [0.0, 0.75, 0.55, 0.0, 0.0, 0.0, 0.1, 0.4]},
    {"id": "sw9", "name": "Kefir Smoothie", "macroDelta": "+6g protein, probiotic",
     "why": "Creamy and cold, closer to a milkshake than a diet swap.",
     "vec": [0.5, 0.0, 0.0, 0.0, 0.9, 0.3, 0.7, 0.0]},
    {"id": "sw10", "name": "Tamari Almonds", "macroDelta": "+5g protein, gluten-free",
     "why": "Savory-salty crunch with a nutty depth, not just 'plain nuts.'",
     "vec": [0.0, 0.7, 0.7, 0.0, 0.0, 0.0, 0.0, 0.8]},
    {"id": "sw11", "name": "Watermelon Ice Pops", "macroDelta": "-14g sugar, all natural",
     "why": "Cold and sweet without the syrup-heavy base of most ice pops.",
     "vec": [0.75, 0.0, 0.0, 0.05, 0.0, 0.85, 0.95, 0.0]},
    {"id": "sw12", "name": "Miso Rice Crisps", "macroDelta": "0g gluten, umami-forward",
     "why": "Savory, crunchy, and salty enough to replace chips.",
     "vec": [0.0, 0.65, 0.8, 0.0, 0.0, 0.0, 0.0, 0.85]},
]

# Very small keyword -> axis lexicon used only to turn free-text craving
# queries into the same 8-dim signature space. This bridge stays
# rule-based on purpose (mapping arbitrary English text to a structured
# vector is its own NLP problem); the part that's learned is what happens
# to that vector once it's produced — the embedding space itself.
_KEYWORD_TO_AXIS = {
    "sweet": "sweet", "sugary": "sweet", "candy": "sweet", "dessert": "sweet",
    "salty": "salty", "salt": "salty", "savory": "savory", "savoury": "savory",
    "umami": "savory",
    "crunchy": "crunchy", "crunch": "crunchy", "crispy": "crunchy",
    "fizzy": "fizzy", "soda": "fizzy", "carbonated": "fizzy", "sparkling": "fizzy",
    "creamy": "creamy", "milkshake": "creamy", "smooth": "creamy",
    "fruity": "fruity", "fruit": "fruity", "citrus": "fruity",
    "cold": "cold", "icy": "cold", "frozen": "cold", "ice": "cold",
    "warm": "savory", "comforting": "creamy", "cozy": "creamy", "hearty": "savory",
}


def craving_text_to_vector(text: str) -> np.ndarray:
    """Rule-based bridge from free text to an 8-dim craving-signature vector."""
    words = re.findall(r"[a-z]+", text.lower())
    vec = np.zeros(len(AXES), dtype=np.float32)
    hit = False
    for w in words:
        axis = _KEYWORD_TO_AXIS.get(w)
        if axis:
            vec[AXES.index(axis)] = 1.0
            hit = True
    if not hit:
        # No recognizable craving words — return a neutral vector rather
        # than an all-zero one, so latent distance still behaves sensibly.
        vec[:] = 0.3
    return vec


def flagged_item_to_vector(item_name: str) -> np.ndarray:
    """
    Best-effort craving vector for a flagged *original* product (used on
    the 'scan' entry point, where we don't have a hand-authored vector).
    Reuses the same keyword bridge as free-text queries.
    """
    return craving_text_to_vector(item_name)


# ---------------------------------------------------------------------------
# Tiny VAE, implemented directly in numpy (no autograd framework — this is
# a small enough model that manual forward/backward is genuinely simpler
# than pulling in torch as a dependency for a laptop-class demo).
# ---------------------------------------------------------------------------
INPUT_DIM = len(AXES)
HIDDEN_DIM = 6
LATENT_DIM = 2


class CravingVAE:
    def __init__(self, seed: int = 42):
        rng = np.random.default_rng(seed)

        def init(shape):
            return rng.normal(0, 0.3, size=shape).astype(np.float32)

        # Encoder: input -> hidden -> (mu, logvar)
        self.W1 = init((INPUT_DIM, HIDDEN_DIM))
        self.b1 = np.zeros(HIDDEN_DIM, dtype=np.float32)
        self.W_mu = init((HIDDEN_DIM, LATENT_DIM))
        self.b_mu = np.zeros(LATENT_DIM, dtype=np.float32)
        self.W_logvar = init((HIDDEN_DIM, LATENT_DIM))
        self.b_logvar = np.zeros(LATENT_DIM, dtype=np.float32)

        # Decoder: latent -> hidden -> reconstruction
        self.W2 = init((LATENT_DIM, HIDDEN_DIM))
        self.b2 = np.zeros(HIDDEN_DIM, dtype=np.float32)
        self.W3 = init((HIDDEN_DIM, INPUT_DIM))
        self.b3 = np.zeros(INPUT_DIM, dtype=np.float32)

    @staticmethod
    def _sigmoid(x):
        return 1.0 / (1.0 + np.exp(-x))

    def encode(self, x: np.ndarray):
        h = np.tanh(x @ self.W1 + self.b1)
        mu = h @ self.W_mu + self.b_mu
        logvar = h @ self.W_logvar + self.b_logvar
        return h, mu, logvar

    def decode(self, z: np.ndarray):
        h2 = np.tanh(z @ self.W2 + self.b2)
        recon = self._sigmoid(h2 @ self.W3 + self.b3)
        return h2, recon

    def embed(self, x: np.ndarray) -> np.ndarray:
        """Deterministic embedding for inference: just the mean, no sampling noise."""
        _, mu, _ = self.encode(x)
        return mu

    def train(self, data: np.ndarray, epochs: int = 4000, lr: float = 0.05, beta: float = 0.1, seed: int = 0):
        """
        Full-batch gradient descent with manually-derived gradients for a
        single-hidden-layer VAE. Small dataset, so full-batch is fine —
        this trains in well under a second.
        """
        rng = np.random.default_rng(seed)
        n = data.shape[0]

        for epoch in range(epochs):
            h, mu, logvar = self.encode(data)
            std = np.exp(0.5 * logvar)
            eps = rng.normal(size=std.shape).astype(np.float32)
            z = mu + eps * std

            h2, recon = self.decode(z)

            # Reconstruction loss: binary cross-entropy (inputs are in [0,1])
            eps_num = 1e-7
            recon_c = np.clip(recon, eps_num, 1 - eps_num)
            bce = -(data * np.log(recon_c) + (1 - data) * np.log(1 - recon_c))
            recon_loss = bce.sum() / n

            # KL divergence to N(0, I)
            kl = -0.5 * np.sum(1 + logvar - mu**2 - np.exp(logvar)) / n

            # ---- backward pass ----
            d_recon = (recon_c - data) / n  # d(BCE)/d(pre-sigmoid) simplifies to (recon - target)
            dW3 = h2.T @ d_recon
            db3 = d_recon.sum(axis=0)
            dh2 = d_recon @ self.W3.T
            dh2_pre = dh2 * (1 - h2**2)  # tanh'
            dW2 = z.T @ dh2_pre
            db2 = dh2_pre.sum(axis=0)
            dz = dh2_pre @ self.W2.T

            # KL gradients w.r.t mu, logvar
            dmu_kl = mu / n
            dlogvar_kl = 0.5 * (np.exp(logvar) - 1) / n

            # Reparameterization: z = mu + eps*std, std = exp(0.5*logvar)
            dmu = dz + beta * dmu_kl
            dlogvar = dz * eps * 0.5 * std + beta * dlogvar_kl

            dW_mu = h.T @ dmu
            db_mu = dmu.sum(axis=0)
            dW_logvar = h.T @ dlogvar
            db_logvar = dlogvar.sum(axis=0)

            dh = dmu @ self.W_mu.T + dlogvar @ self.W_logvar.T
            dh_pre = dh * (1 - h**2)
            dW1 = data.T @ dh_pre
            db1 = dh_pre.sum(axis=0)

            for param, grad in [
                (self.W1, dW1), (self.b1, db1),
                (self.W_mu, dW_mu), (self.b_mu, db_mu),
                (self.W_logvar, dW_logvar), (self.b_logvar, db_logvar),
                (self.W2, dW2), (self.b2, db2),
                (self.W3, dW3), (self.b3, db3),
            ]:
                param -= lr * grad

        return recon_loss, kl

    def save(self, path: Path = WEIGHTS_PATH):
        np.savez(
            path,
            W1=self.W1, b1=self.b1, W_mu=self.W_mu, b_mu=self.b_mu,
            W_logvar=self.W_logvar, b_logvar=self.b_logvar,
            W2=self.W2, b2=self.b2, W3=self.W3, b3=self.b3,
        )

    def load(self, path: Path = WEIGHTS_PATH):
        d = np.load(path)
        self.W1, self.b1 = d["W1"], d["b1"]
        self.W_mu, self.b_mu = d["W_mu"], d["b_mu"]
        self.W_logvar, self.b_logvar = d["W_logvar"], d["b_logvar"]
        self.W2, self.b2 = d["W2"], d["b2"]
        self.W3, self.b3 = d["W3"], d["b3"]


# ---------------------------------------------------------------------------
# Module-level singleton — trained once (or loaded from disk) at import time
# ---------------------------------------------------------------------------
_vae = CravingVAE()
_catalog_matrix = np.array([item["vec"] for item in SWAP_CATALOG], dtype=np.float32)

if WEIGHTS_PATH.exists():
    _vae.load()
else:
    _vae.train(_catalog_matrix)
    _vae.save()

_catalog_embeddings = _vae.embed(_catalog_matrix)  # (n_items, LATENT_DIM)


def rank_swaps_vae(query_vec: np.ndarray, limit: int = 12) -> List[dict]:
    """
    Ranks SWAP_CATALOG by Euclidean distance in the learned latent space
    between the query's embedding and each item's embedding — this is the
    line that replaces the old tag-overlap set intersection.
    """
    q_embed = _vae.embed(query_vec.reshape(1, -1).astype(np.float32))[0]
    dists = np.linalg.norm(_catalog_embeddings - q_embed, axis=1)
    order = np.argsort(dists)[:limit]
    return [
        {
            "id": SWAP_CATALOG[i]["id"],
            "name": SWAP_CATALOG[i]["name"],
            "macroDelta": SWAP_CATALOG[i]["macroDelta"],
            "why": SWAP_CATALOG[i]["why"],
        }
        for i in order
    ]


# ---------------------------------------------------------------------------
# Why this model and not YOLO/CNN-OCR/attention-captioner/BiLSTM/GAN:
#
# The report (Positioning of SafeBite-DL section) already identifies the
# craving-signature VAE as the one piece of the pipeline that's genuinely
# unclaimed in the competitive landscape — the allergen-matching half is a
# mature, well-served category, but no competitor grounds swap
# recommendations in a learned embedding over structured sensory
# attributes. That makes it the highest-value thing to actually finish
# training for a review, versus spending the same hours getting a YOLO
# panel detector or a CNN/CRNN OCR model to a *usable* accuracy on a
# from-scratch photographed-label dataset that doesn't exist yet.
#
# Everything else described in the report (YOLO panel detection,
# CNN/CRNN OCR, attention-based captioner, BiLSTM next-flag predictor,
# conditional GAN for label augmentation) should be presented as
# architected — with a defined input/output shape, a named evaluation
# metric, and a place in the pipeline — but NOT YET TRAINED. Say that
# plainly in the report rather than letting the prose imply they're all
# live. A reviewer who asks "show me the OCR model's confusion matrix"
# should get "that one's architected, here's the plan and here's why it
# wasn't feasible to train in this pass" — not silence or a bluff.
# ---------------------------------------------------------------------------
SWAP_ALLERGENS = {  # verify these against real products
    "sw2": ["tree-nut"], "sw8": ["soy"], "sw9": ["dairy"],
    "sw10": ["tree-nut", "soy"], "sw12": ["soy"],
}

LEXICON = {
  "ice cream": {"sweet":.8,"creamy":.9,"cold":1}, "milkshake": {"sweet":.7,"creamy":1,"cold":.8},
  "chocolate": {"sweet":.8,"creamy":.5}, "candy": {"sweet":1,"fruity":.3}, "dessert": {"sweet":1,"creamy":.4},
  "cookie": {"sweet":.9,"crunchy":.5}, "cake": {"sweet":1,"creamy":.4}, "sugary": {"sweet":1}, "sweet": {"sweet":1},
  "chips": {"salty":.9,"crunchy":1,"savory":.5}, "crisps": {"salty":.9,"crunchy":1}, "popcorn": {"salty":.6,"crunchy":.8},
  "nachos": {"salty":.8,"crunchy":.9,"savory":.6}, "fries": {"salty":.9,"crunchy":.6,"savory":.6},
  "cheesy": {"savory":.8,"creamy":.5,"salty":.6}, "cheese": {"savory":.8,"creamy":.5,"salty":.6},
  "spicy": {"savory":.7,"salty":.3}, "tangy": {"fruity":.6,"savory":.3},
  "salty": {"salty":1}, "salt": {"salty":1}, "savory": {"savory":1}, "savoury": {"savory":1}, "umami": {"savory":1},
  "crunchy": {"crunchy":1}, "crunch": {"crunchy":1}, "crispy": {"crunchy":1}, "crisp": {"crunchy":1},
  "fizzy": {"fizzy":1}, "soda": {"fizzy":1,"sweet":.7,"cold":.5}, "cola": {"fizzy":1,"sweet":.8,"cold":.5},
  "carbonated": {"fizzy":1}, "sparkling": {"fizzy":1}, "bubbly": {"fizzy":1},
  "creamy": {"creamy":1}, "smooth": {"creamy":.8}, "milky": {"creamy":.8},
  "fruity": {"fruity":1}, "fruit": {"fruity":1}, "citrus": {"fruity":.9}, "berry": {"fruity":.9,"sweet":.5},
  "cold": {"cold":1}, "icy": {"cold":1}, "frozen": {"cold":1}, "chilled": {"cold":.8}, "refreshing": {"cold":.7,"fruity":.4},
}
_PHRASES = sorted(LEXICON, key=len, reverse=True)
_NEG = {"not", "no", "without", "less", "non", "isnt", "dont", "never"}


def parse_craving(text: str):
    t = " " + re.sub(r"[^a-z ]", " ", text.lower()) + " "
    target = np.zeros(len(AXES), dtype=np.float32)
    weight = np.full(len(AXES), 0.15, dtype=np.float32)  # unmentioned axes barely matter
    hit = False
    for p in _PHRASES:
        for m in re.finditer(r"\b" + p + r"\b", t):
            hit = True
            negated = any(w in _NEG for w in t[:m.start()].split()[-3:])
            for ax, s in LEXICON[p].items():
                i = AXES.index(ax)
                if negated:
                    target[i], weight[i] = 0.0, 1.0   # "not too sweet" => want LOW sweet
                else:
                    target[i] = max(target[i], s); weight[i] = 1.0
            t = t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]
    return target, weight, hit


def rank_craving(text: str, allergens: List[str], limit: int = 12) -> dict:
    target, weight, hit = parse_craving(text)
    if not hit:
        return {"query": text, "results": [],
                "message": "Try describing taste or texture, e.g. crunchy, salty, creamy, cold, fizzy."}
    raw = (weight * (_catalog_matrix - target) ** 2).sum(axis=1)
    lat = np.linalg.norm(_catalog_embeddings - _vae.embed(target.reshape(1, -1))[0], axis=1)
    score = raw + 0.15 * lat            # sensory distance first, VAE latent as tie-breaker
    out = []
    for i in np.argsort(score):
        item = SWAP_CATALOG[i]
        if raw[i] > 0.8:
            continue                    # too far from the craving, show fewer results instead of bad ones
        if any(a in allergens for a in SWAP_ALLERGENS.get(item["id"], [])):
            continue                    # safety first: drop anything that hits the user's allergens
        top_axes = np.argsort(-np.array(item["vec"]))[:2]
        out.append({"id": item["id"], "name": item["name"], "macroDelta": item["macroDelta"],
                    "why": item["why"], "tags": [AXES[j] for j in top_axes]})
        if len(out) == limit:
            break
    return {"query": text, "results": out}