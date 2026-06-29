const EXAMPLE_PAYLOAD_SINGLE = {
  variables: {
    "1": {
      short_description: "Var 1",
      long_description: "First variable",
      group_id: 10,
    },
    "2": {
      short_description: "Var 2",
      long_description: "Second variable",
      group_id: 10,
    },
  },
  groups: {
    "10": {
      short_description: "Group A",
      long_description: "Variable group A",
    },
  },
  mode: "single",
  weight_column: "wrakin1",
  outputs: {
    segmentation: { num_segments: 3 },
    dendrogram: {
      distance: "simpson",
      grouping: "average",
      num_groups: 3,
    },
    graph: { distance: "jaccard" },
  },
};

const EXAMPLE_PAYLOAD_MULTIPLE = {
  variables: {
    "1": {
      short_description: "Trait 1",
      long_description: "First trait",
    },
    "2": {
      short_description: "Trait 2",
      long_description: "Second trait",
    },
  },
  mode: "multiple",
  column_prefix: "IM6",
  items: {
    "101": {
      short_description: "Brand A",
      long_description: "Brand A full name",
    },
    "102": {
      short_description: "Brand B",
      long_description: "Brand B full name",
    },
  },
  weight_column: "wrakin1",
  outputs: {
    segmentation: { num_segments: 3 },
    dendrogram: {
      distance: "simpson",
      grouping: "average",
      num_groups: 2,
    },
    graph: { distance: "jaccard" },
  },
};

const payloadEl = document.getElementById("payload");
const formEl = document.getElementById("analyze-form");
const fileEl = document.getElementById("dataframe");
const errorEl = document.getElementById("error");
const resultsEl = document.getElementById("results");
const submitBtn = document.getElementById("submit-btn");
const modeSingleBtn = document.getElementById("mode-single");
const modeMultipleBtn = document.getElementById("mode-multiple");
const columnHintEl = document.getElementById("column-hint");

let activeMode = "single";

function setMode(mode) {
  activeMode = mode;
  modeSingleBtn.classList.toggle("active", mode === "single");
  modeMultipleBtn.classList.toggle("active", mode === "multiple");
  payloadEl.value = JSON.stringify(
    mode === "single" ? EXAMPLE_PAYLOAD_SINGLE : EXAMPLE_PAYLOAD_MULTIPLE,
    null,
    2,
  );
  columnHintEl.textContent =
    mode === "single"
      ? "Columns: VAR_1, VAR_2, … plus weight column (e.g. wrakin1)"
      : "Columns: {prefix}_{var}_{item} (e.g. IM6_1_101, IM6_2_102), plus weight column";
}

modeSingleBtn.addEventListener("click", () => setMode("single"));
modeMultipleBtn.addEventListener("click", () => setMode("multiple"));

setMode("single");

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove("hidden");
}

function clearError() {
  errorEl.textContent = "";
  errorEl.classList.add("hidden");
}

function renderResults(data) {
  resultsEl.innerHTML = "";
  resultsEl.classList.remove("hidden");

  if (data.dendrogram) {
    const d = data.dendrogram;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h2>Dendrogram</h2>
      <div class="meta-row">
        <span>Distance: <strong>${d.distance}</strong></span>
        <span>Grouping: <strong>${d.grouping}</strong></span>
        <span>Groups: <strong>${d.num_groups}</strong></span>
      </div>
      <img class="dendrogram-img" alt="Dendrogram" src="data:image/png;base64,${d.image_png_base64}" />
      <div class="actions">
        <button type="button" id="download-png">Download PNG</button>
      </div>
      <h2 style="margin-top:1.25rem">Cluster assignments</h2>
      <pre class="json-out"></pre>
    `;
    card.querySelector("pre").textContent = JSON.stringify(
      d.cluster_assignments,
      null,
      2,
    );
    card.querySelector("#download-png").addEventListener("click", () => {
      const link = document.createElement("a");
      link.href = `data:image/png;base64,${d.image_png_base64}`;
      link.download = `dendrogram_${d.distance}_${d.grouping}.png`;
      link.click();
    });
    resultsEl.appendChild(card);
  }

  if (data.segmentation) {
    const s = data.segmentation;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h2>Segmentation</h2>
      <div class="meta-row">
        <span>Segments: <strong>${s.num_segments}</strong></span>
      </div>
      <pre class="json-out"></pre>
    `;
    card.querySelector("pre").textContent = JSON.stringify(
      s.assignments,
      null,
      2,
    );
    resultsEl.appendChild(card);
  }

  if (data.graph) {
    const g = data.graph;
    const card = document.createElement("div");
    card.className = "card";
    const edgesPreview = g.edges.slice(0, 50);
    let text = JSON.stringify(edgesPreview, null, 2);
    if (g.edges.length > 50) text += "\n… (truncated)";
    card.innerHTML = `
      <h2>Graph</h2>
      <div class="meta-row">
        <span>Distance: <strong>${g.distance}</strong></span>
        <span>Nodes: <strong>${g.nodes.length}</strong></span>
        <span>Edges: <strong>${g.edges.length}</strong></span>
      </div>
      <pre class="json-out"></pre>
    `;
    card.querySelector("pre").textContent = text;
    resultsEl.appendChild(card);
  }
}

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();
  resultsEl.classList.add("hidden");

  const file = fileEl.files?.[0];
  if (!file) {
    showError("Please select an Arrow IPC dataframe file.");
    return;
  }

  try {
    JSON.parse(payloadEl.value);
  } catch {
    showError("Payload is not valid JSON.");
    return;
  }

  const form = new FormData();
  form.append("payload", payloadEl.value);
  form.append("dataframe", file);

  submitBtn.disabled = true;
  submitBtn.textContent = "Analyzing…";

  try {
    const res = await fetch("/api/v1/analyze", { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) {
      const detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail, null, 2);
      throw new Error(detail || `Request failed (${res.status})`);
    }
    renderResults(body);
  } catch (err) {
    showError(err instanceof Error ? err.message : "Request failed");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Run analysis";
  }
});
