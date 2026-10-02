# model1: does English document i transmit Chinese document j?

Frozen 2026-10-02. Part of [[Translation]]. Context: `Translation.em.md` (notes). Code: `src/transmission/`
(data layer `pairs.py`, model layer `model1.py`), `scripts/build_transmission_pairs.py`, `scripts/fit_model1.py`.

## Purpose

For each (English document i, Chinese document j) pair, estimate the probability that i transmits information from j. A hyperlink to j is a noisy prior. A direct copy of Chinese text from j is a high-precision signal. A few hand labels anchor the model.

## Variables

| Symbol | Type | Meaning |
|---|---|---|
| z_ij ∈ {0,1} | latent | 1 if English doc i transmits information from Chinese doc j |
| L_ij ∈ {0,1} | observed | 1 if i hyperlinks to j |
| c_ij ∈ {0,1} | observed | 1 if i copies at least one Chinese string (≥ 4 characters) that also appears in j |
| y_ij ∈ {0,1} or missing | partial label | hand label for z_ij (sparse) |

## Model

L is a covariate: the model is conditional on it and does not generate it.

- Prior from the link: p(z=1 | L=l) = π_l, for l ∈ {0,1}
- Copy given z: c | z ~ Bernoulli(γ_z)
- γ₀ is fixed at a small ε (default 0.001). Chance copying of a Chinese string of ≥ 4 characters is near zero.
- γ₁ is free: the share of true transmitters that copy.
- Parameters: **π₀, π₁, γ₁** (3 free parameters)

Pairs are independent given the parameters.

## Likelihood (the quantity EM increases)

Let θ = (π₀, π₁, γ₁), with ε fixed. For pair ij, write π_L = π₁ if L_ij = 1 and π₀ otherwise, and

- a_ij = γ₁^c (1 − γ₁)^(1−c) = p(c_ij | z=1)
- b_ij = ε^c (1 − ε)^(1−c) = p(c_ij | z=0)

**ℓ(θ) = Σ_{labelled, y=1} log( π_L a_ij ) + Σ_{labelled, y=0} log( (1 − π_L) b_ij ) + Σ_{unlabelled} log( π_L a_ij + (1 − π_L) b_ij )**

**Guarantee.** Each EM iteration satisfies ℓ(θ_{t+1}) ≥ ℓ(θ_t). The E-step sets r_ij = p(z=1 | L, c, θ_t) (or y_ij for labelled pairs) and builds Q(θ | θ_t) = Σ_ij [ r_ij log(π_L a_ij) + (1 − r_ij) log((1 − π_L) b_ij) ]; the M-step maximizes Q exactly. `fit()` records ℓ at every iteration. Convergence is to a local maximum or a saddle point.

## Algorithm (EM)

Initialize π₀ = 0.05, π₁ = 0.5, γ₁ = 0.2, or from the labelled pairs if there are enough (≥ 30 positives).

- **E-step.** r_ij = π_L a_c / [π_L a_c + (1 − π_L) b_c] for unlabelled pairs; r_ij = y_ij for labelled pairs.
- **M-step.** π_l = mean of r_ij over pairs with L_ij = l; γ₁ = Σ r_ij c_ij / Σ r_ij.

Iterate until the log-likelihood changes by less than 1e-8, or for at most 200 iterations.

## Identifiability

The data alone give only P(c=1 | L=l) = π_l γ₁ + (1−π_l) ε: two numbers for three parameters. **Hand-labelled pairs with y = 1 are required**: they pin γ₁, and π_l follow. Aim for at least 30 labelled positives and a handful of labelled negatives.

## Inputs

- A pair table `doc_en, doc_zh, L, c, y` (y blank when unlabelled).
- The pair universe: the linked documents plus each English document's nearest Chinese documents by embedding.
- c: Chinese character runs of ≥ 4 characters in the English text, tested for membership in the Chinese text.

## Outputs

- r_ij = P(i transmits j). A high r on an unlinked pair (L = 0) is a candidate missing link.
- π₁, π₀: transmission rate among linked and unlinked pairs.
- γ₁: share of true transmitters that copy Chinese text.

## Evaluation

- Hold out labelled pairs grouped by English document (or outlet), treat them as unlabelled, compare r to y: precision and recall at r > 0.5, plus calibration.
- Report the fraction of pairs with 0.1 < r < 0.9. If it is large, the features are too weak.

## Assumptions and limits

- A link is not transmission; π₁ is estimated.
- Copying is evidence for transmission but not necessary (γ₁ small: high precision, low recall).
- With ε fixed, a single false copy forces r near 1, so keep ε above 0; if false copies show up in the labelled negatives, raise ε.
- Only two observed signals: posteriors for pairs with L = 0 and c = 0 are driven by π₀.

## Deferred (not in model1)

- Date gap, bag-of-words cosine, shared anchors, LaBSE cosine as extra features
- Title copy vs. body copy
- Sentence- and provision-level alignment (z, a), quote vs. paraphrase
- Per-outlet rates
- The link as a noisy label, p(L | z), instead of a covariate
