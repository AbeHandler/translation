# model1: does English document i transmit Chinese document j?

2026-10-02. Part of [[Translation]]. Context: `Translation.em.md` (notes).
Code: `src/features/` (candidates, features), `src/model/model1.py` (the model), `scripts/build_transmission_pairs.py`, `scripts/fit_model1.py`.

## Purpose

Discover transmission: for (English document i, Chinese document j), the probability that i transmits information from j. The main output is z, latent because we can't observe it; a high posterior on a pair without a link is a discovered link.

## Generative story (latent class / naive Bayes)

    z ~ Bernoulli(π)                                          i transmits j, or not
    x_k | z ~ Categorical(θ_k[z])    for each feature k       independent given z

Every feature is weak evidence of transmission:

| Feature | Codes | Status |
|---|---|---|
| link: i links to j | 0/1 | built |
| copy: i contains a run of ≥ 4 Chinese characters that also appears in j (runs in more than `max_df` Chinese documents don't count) | 0/1 | built |
| screenshot: i shows an image of j | 0/1 | not built |
| similarity: cosine of the documents' embeddings (LaBSE, title + start), binned at 0.3 / 0.4 / 0.5 / 0.6 | 0-4 | built (whole documents; parts of documents later) |
| date_gap: days from j's publication to i's, binned < 0, 0-3, 4-30, 31-365, > 365 | 0-4 | built |

-1 = missing: the feature is left out of that pair's likelihood. Hand labels y fix z where given.

## What EM gets us

Every feature describes the positive class. The negative class comes for free: nearly all pairs are non-transmissions, so θ_k[0] is close to the features' distribution over pairs. EM learns θ_k[1], what transmitters look like, from the excess of co-occurring signals, and the likelihood ratio θ_k[1]/θ_k[0] says how much each signal is worth. The posterior r = p(z=1 | x) combines them, so a pair with no link but a copy, close dates and high similarity can outrank a linked pair with nothing else.

With three or more features that are independent given z, a two-class latent model is identifiable without labels (latent class analysis); labels then check and anchor it.

## Candidates

A pair enters the feature matrix if any feature fires for it (a link, a copy, a screenshot, similar embeddings, close dates), each found without comparing all pairs (copy index, nearest-neighbour search, date blocking). **For now the candidates are the linked pairs only.** π is then the transmission rate among candidates, and link is constant until other candidate sources are added.

## Algorithm

- Initialize θ_k[0] uniform and θ_k[1] leaning towards the levels that suggest transmission (link = 1, copy = 1, top similarity, gap 0-3 days); this also names the positive class so the components can't swap.
- E-step: r = π ∏ θ_k[1][x_k] / (π ∏ θ_k[1][x_k] + (1 − π) ∏ θ_k[0][x_k]); r = y for labelled pairs.
- M-step: π = weighted mean of r; θ_k[z] = weighted counts of each level under r (z=1) and 1 − r (z=0), plus a small Dirichlet α = 0.01.
- Identical rows are fit once with a weight. Stop when the log-likelihood changes by < 1e-8 (at most 500 iterations); it never decreases (up to the tiny Dirichlet term).
- Any θ_k[z] can be fixed, e.g. copy under z = 0 at a small ε.

## Assumptions and limits

- Independence given z. Correlated features (copy and quotes, similarity and topical overlap) double-count evidence; merge them or model the dependence.
- With linked candidates only, the data are small and link is constant, so EM can fit odd clusters; it needs the other candidate sources and some labels.
- A link is not transmission; its rate among transmitters is estimated.

## Evaluation

Hold out labelled pairs grouped by English document or outlet; compare r with y (precision and recall at 0.5, calibration). Report the share of ambiguous pairs (0.1 < r < 0.9).

## Next

- Candidate sources beyond links: the copy index, embedding nearest neighbours, date blocking.
- Screenshots.
- Similarity of parts of documents (sentences, quotes).
- Labels from the annotator.
