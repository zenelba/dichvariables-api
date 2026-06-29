# Similarity and distance calculations

This document describes how the DichVariables API computes similarities and distances for cases, variables, and items (brands).

## Notation

| Symbol | Meaning |
|--------|---------|
| \(n\) | Number of cases (rows) |
| \(p\) | Number of entity columns in the response matrix |
| \(X\) | \(n \times p\) binary response matrix (0/1) |
| \(w_i\) | Case weight for row \(i\) |
| \(X_{i\cdot}\) | Binary profile of case \(i\) (row \(i\)) |
| \(X_{\cdot j}\) | Binary profile of column \(j\) across cases |

All non-zero cell values are converted to 1 before analysis.

## Distance metrics — overview

Two similarity metrics are available in the payload (`"distance": "jaccard"` or `"simpson"`).  
The API always returns **distance** = **1 − similarity** (0 = identical profiles, 1 = no overlap).

Both metrics:

- Work on **binary** 0/1 profiles (presence/absence)
- Support **case weights** on each position
- Apply to cases, variables, and items — the formula is the same; only the profile being compared changes

---

## When to use Jaccard vs Simpson

### Jaccard — symmetric “how alike are they overall?”

**Use Jaccard when:**

- You want a **balanced, symmetric** measure — A vs B gives the same result as B vs A
- **Both** unique presences **and** unique absences should reduce similarity
- Profiles have **similar size** (similar number of 1s)
- You are comparing **respondent segments**, **brand maps**, or **trait structures** where neither side is expected to be a subset of the other

**Typical use cases in this API:**

| Output | Why Jaccard |
|--------|-------------|
| **Segmentation** (cases) | Find respondent groups with broadly similar overall response patterns |
| **Graph** (cases) | Explore pairwise case similarity without subset bias |
| **Dendrogram** (brands) | Cluster brands that share traits *and* lack traits together |
| **Dendrogram** (variables) | Cluster traits with similar brand association patterns |

**Intuition:** Jaccard answers *“What share of all positions where either profile is active do they share?”*

---

### Simpson — “how much does the smaller profile fit inside the larger?”

**Use Simpson when:**

- One profile is often a **subset** of another (fewer 1s, narrower trait set, smaller brand footprint)
- You care about **coverage of the smaller profile**, not penalizing the larger one for extra 1s
- You want to detect **containment** or **nested** structure (e.g. “Brand A’s associations are mostly included in Brand B’s”)

**Typical use cases:**

| Output | Why Simpson |
|--------|-------------|
| **Dendrogram** (brands) | A niche brand looks similar to a large brand if the niche’s traits are mostly a subset |
| **Dendrogram** (variables) | A narrow trait is “close to” a broad trait if it co-occurs wherever the narrow one does |
| **Segmentation / graph** | When cases differ strongly in how many attributes they activate, and subset-like groups are meaningful |

**Intuition:** Simpson answers *“What share of the **smaller** profile is shared?”*  
Extra 1s on the larger profile alone do **not** reduce similarity.

**Note:** Simpson is **asymmetric in meaning** (though the API computes one number per unordered pair using the smaller profile as denominator for both). Interpret results as “overlap relative to the sparser entity.”

---

### Quick decision guide

```
Do profiles often differ in how many 1s they have?
├── No, similar “density”        → prefer Jaccard
└── Yes, one often ⊆ the other   → prefer Simpson

Is symmetric comparison important?
├── Yes                          → Jaccard
└── No, subset/containment OK    → Simpson

Default when unsure               → Jaccard (most common for market-structure maps)
```

---

## How Jaccard and Simpson are calculated

### Setup

Compare two binary vectors \(a\) and \(b\) (same length), with optional non-negative weight \(u_k\) on each position \(k\).

**Weighted size** (total weighted mass of 1s):

\[
|a| = \sum_k u_k \cdot a_k, \quad |b| = \sum_k u_k \cdot b_k
\]

**Weighted intersection** (mass where both are 1):

\[
|a \cap b| = \sum_k u_k \cdot a_k \cdot b_k
\]

**Weighted union** (Jaccard only):

\[
|a \cup b| = |a| + |b| - |a \cap b|
\]

Without case weights, set \(u_k = 1\) everywhere.

### Jaccard

\[
\text{sim}_\text{Jaccard} = \frac{|a \cap b|}{|a \cup b|}
\quad\text{(0 if union = 0)}
\]

\[
d_\text{Jaccard} = 1 - \text{sim}_\text{Jaccard}
\]

### Simpson

\[
\text{sim}_\text{Simpson} = \frac{|a \cap b|}{\min(|a|, |b|)}
\quad\text{(1 if both sizes = 0; 0 if exactly one size = 0)}
\]

\[
d_\text{Simpson} = 1 - \text{sim}_\text{Simpson}
\]

### Numeric example (unweighted)

Profiles over 10 positions:

| | Positions with 1 |
|---|------------------|
| Brand A | `{1,2,3,4,5}` → size 5 |
| Brand B | `{1,2,3,6,7}` → size 5 |
| Brand C | `{1,2,3}` → size 3 (subset of A) |

**A vs B:** intersection = 3, union = 7  
- Jaccard sim = 3/7 ≈ **0.43** → distance **0.57**  
- Simpson sim = 3/5 = **0.60** → distance **0.40** (same min size)

**A vs C:** intersection = 3, union = 5  
- Jaccard sim = 3/5 = **0.60** → distance **0.40**  
- Simpson sim = 3/3 = **1.00** → distance **0.00** (C is fully contained in A)

Here Simpson treats C as perfectly similar to A (subset), while Jaccard still penalizes A’s extra 1s `{4,5}`.

### Numeric example (with case weights)

Two cases, one variable each (simplified item comparison):

| Position | \(a\) | \(b\) | weight \(u\) |
|----------|-------|-------|----------------|
| case 1 | 1 | 1 | 1.0 |
| case 2 | 1 | 0 | 2.0 |

\(|a| = 1\cdot1 + 2\cdot1 = 3\), \(|b| = 1\cdot1 + 2\cdot0 = 1\), \(|a \cap b| = 1\)

- Jaccard: union = 3 + 1 − 1 = 3 → sim = 1/3 → **distance 0.67**
- Simpson: min size = 1 → sim = 1/1 = 1 → **distance 0.00**

The heavy-weight case where only \(a\) is 1 drives Jaccard down; Simpson only asks whether the smaller profile (\(b\)) is covered.

---

## Case weights

Case weights \(w_i\) are applied differently depending on what is being compared:

| Analysis | How weights enter |
|----------|-------------------|
| Cases (segmentation, graph) | Each case’s profile is multiplied by its weight: \(\tilde{X}_{ik} = w_i \cdot X_{ik}\) |
| Column clustering (single mode) | Weights are axis weights on case positions when comparing column vectors |
| Item/variable clustering (multiple mode) | Case weights are repeated for each trait (items) or each brand (variables) in the flattened profile |

## 1. Case-to-case distances (segmentation & graph)

**Used by:** `segmentation`, `graph`  
**Compares:** Rows of the response matrix (respondents / cases)

For cases \(i\) and \(j\), define weighted row vectors:

- \(\tilde{a}_k = w_i \cdot X_{ik}\)
- \(\tilde{b}_k = w_j \cdot X_{jk}\)

Apply Jaccard or Simpson to \((\tilde{a}, \tilde{b})\) using unit weight on each position (weights are already embedded in the vectors).

**Segmentation** builds a condensed distance matrix over all case pairs, runs hierarchical clustering with **average** linkage, and cuts into `num_segments` flat clusters.

**Graph** returns all pairwise case distances as edges (same distance formula).

In **multiple mode**, each case’s profile is the full vector of all `{item × variable}` columns — typically length \(|\text{items}| \times |\text{variables}|\).

## 2. Variable-to-variable distances (single mode dendrogram)

**Used by:** `dendrogram` when `mode = "single"`  
**Compares:** Variables (columns)

The response matrix is transposed so each **variable** is a row of length \(n\) (one value per case):

- Row \(j\): \(X_{\cdot j}\) across all cases
- Axis weights: case weights \(w_1, \ldots, w_n\)

Jaccard or Simpson is computed between every pair of variable rows using those case weights on the \(n\) positions.

**Dendrogram:** condensed distances → hierarchical linkage (`ward`, `complete`, or `average`) → flat clusters (`num_groups`) → PNG with variable labels.

## 3. Item-to-item distances (multiple mode — brand dendrogram)

**Used by:** `dendrogram` when `mode = "multiple"`  
**Compares:** Items (brands / subjects)

Each item (brand) gets one long binary profile across **all variables and all cases**.

For item \(b\) with \(V\) variables and \(n\) cases:

1. Collect columns where `item_id = b` (one column per variable).
2. Flatten the \(n \times V\) block row-wise into a vector of length \(n \cdot V\).
3. Build expanded weights: repeat each case weight \(V\) times → length \(n \cdot V\).

Pairwise Jaccard/Simpson is computed between item rows using those expanded weights.

**Interpretation:** Two brands are similar if their 0/1 patterns agree across traits and cases, with case weights applied at each case×trait position.

**Dendrogram output:** `cluster_assignments` keys are **item IDs**; PNG title says “items”.

## 4. Variable-to-variable distances (multiple mode — trait dendrogram)

**Used by:** `dendrogram_variables` when `mode = "multiple"`  
**Compares:** Variables (traits)

Symmetric to item clustering, but grouped by **variable** instead of item.

For variable \(v\) with \(B\) items (brands) and \(n\) cases:

1. Collect columns where `variable_id = v` (one column per brand).
2. Flatten the \(n \times B\) block into a vector of length \(n \cdot B\).
3. Expanded weights: repeat each case weight \(B\) times.

Pairwise Jaccard/Simpson between variable rows.

**Interpretation:** Two traits are similar if their association patterns with brands (across cases) are alike.

**Dendrogram output:** `cluster_assignments` keys are **variable IDs**; PNG title says “variables”.

## 5. Hierarchical clustering (dendrograms)

After condensed distances are computed:

1. **Linkage** (`scipy.cluster.hierarchy.linkage`) merges clusters using the requested method:
   - `average` — average distance between clusters
   - `complete` — maximum distance between clusters
   - `ward` — Ward’s minimum variance (on condensed distances)
2. **Flat clusters** (`fcluster`, criterion `maxclust`) assign each entity to one of `num_groups` clusters.
3. **Color threshold** is derived from the linkage matrix for branch coloring in the PNG.
4. Labels come from payload descriptions (`variables` or `items`; variables may include group prefix).

## 6. Worked example (multiple mode)

Data:

| Case | IM1_11_2 | IM1_12_2 | weight |
|------|----------|----------|--------|
| 1 | 1 | 0 | 1.0 |
| 2 | 0 | 1 | 2.0 |

- **Item 11** profile (var 2 only): `[1, 0]` → flattened with weight `[1, 2]` → weighted vector `[1, 0]`
- **Item 12** profile: `[0, 1]` → weighted vector `[0, 2]`

Jaccard between items: intersection = 0, union = 1 + 2 = 3 → similarity = 0 → distance = 1.

- **Variable 2** profile: both items, both cases → vector `[1, 0, 0, 1]` with expanded weights `[1, 2, 1, 2]`.

## 7. Implementation reference

| Function | File | Purpose |
|----------|------|---------|
| `observation_distance_condensed` | `backend/services/distances.py` | Case–case distances |
| `variable_distance_condensed` | same | Variable–variable (single mode) |
| `item_distance_condensed` | same | Item–item (multiple mode) |
| `multiple_mode_variable_distance_condensed` | same | Variable–variable (multiple mode) |
| `compute_dendrogram` | `backend/services/dendrogram.py` | Linkage + PNG |
| `compute_segmentation` | `backend/services/segmentation.py` | Case segments |
| `compute_graph` | `backend/services/graph.py` | Case distance graph |
