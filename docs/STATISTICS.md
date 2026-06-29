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

## Distance metrics

Two similarity metrics are available. The API returns **distance** = **1 − similarity**.

### Jaccard similarity (weighted)

For two binary vectors \(a\) and \(b\) with non-negative weights \(u_k\) on each position \(k\):

1. Weighted presence on each vector:
   - \(|a| = \sum_k u_k \cdot a_k\)
   - \(|b| = \sum_k u_k \cdot b_k\)
2. Weighted intersection:
   - \(|a \cap b| = \sum_k u_k \cdot a_k \cdot b_k\)
3. Weighted union:
   - \(|a \cup b| = |a| + |b| - |a \cap b|\)
4. Similarity:
   - \(\text{sim}_\text{Jaccard} = |a \cap b| / |a \cup b|\) if union > 0, else 0
5. Distance:
   - \(d = 1 - \text{sim}_\text{Jaccard}\)

### Simpson similarity (weighted)

Uses the same weighted intersection, but normalizes by the **smaller** weighted size:

1. \(\text{sim}_\text{Simpson} = |a \cap b| / \min(|a|, |b|)\) if \(\min(|a|,|b|) > 0\)
2. If both sizes are 0, similarity = 1; if exactly one is 0, similarity = 0
3. Distance: \(d = 1 - \text{sim}_\text{Simpson}\)

Simpson emphasizes overlap relative to the smaller profile (asymmetric in interpretation).

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

## 7. Choosing a metric

| Metric | When to use |
|--------|-------------|
| **Jaccard** | Symmetric comparison; penalizes both unique presence and unique absence |
| **Simpson** | Overlap relative to the smaller profile; useful when one profile is a subset of another |

Both respect case weights throughout.

## 8. Implementation reference

| Function | File | Purpose |
|----------|------|---------|
| `observation_distance_condensed` | `backend/services/distances.py` | Case–case distances |
| `variable_distance_condensed` | same | Variable–variable (single mode) |
| `item_distance_condensed` | same | Item–item (multiple mode) |
| `multiple_mode_variable_distance_condensed` | same | Variable–variable (multiple mode) |
| `compute_dendrogram` | `backend/services/dendrogram.py` | Linkage + PNG |
| `compute_segmentation` | `backend/services/segmentation.py` | Case segments |
| `compute_graph` | `backend/services/graph.py` | Case distance graph |
