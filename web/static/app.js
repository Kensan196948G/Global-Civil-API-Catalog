const state = {
  summary: null,
  catalog: [],
  verification: [],
  exports: [],
};

const byId = (id) => document.getElementById(id);

async function loadJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json();
}

function badge(value) {
  const klass = value === "success" || value === "A" || value === "本格利用候補" ? "good" :
    value === "warning" || value === "保留" || value === "調査中" ? "warn" : "";
  return `<span class="badge ${klass}">${value}</span>`;
}

function renderSummary() {
  byId("catalogCount").textContent = state.summary.catalog_count;
  byId("verificationCount").textContent = state.summary.verification_count;
  byId("implementedCount").textContent = state.summary.implemented_count;
  byId("candidateCount").textContent = state.summary.candidate_count;

  for (const category of state.summary.categories) {
    byId("categoryFilter").insertAdjacentHTML("beforeend", `<option value="${category}">${category}</option>`);
  }
  for (const status of state.summary.statuses) {
    byId("statusFilter").insertAdjacentHTML("beforeend", `<option value="${status}">${status}</option>`);
  }
}

function renderCatalog() {
  const q = byId("searchInput").value.trim().toLowerCase();
  const category = byId("categoryFilter").value;
  const status = byId("statusFilter").value;
  const rows = state.catalog
    .filter((item) => !q || JSON.stringify(item).toLowerCase().includes(q))
    .filter((item) => !category || item.category === category)
    .filter((item) => !status || item.connection_status === status)
    .map((item) => `
      <tr>
        <td><strong>${item.id}</strong></td>
        <td>${item.name}</td>
        <td>${item.category}</td>
        <td>${item.provider}</td>
        <td>${item.data_formats.join(", ")}</td>
        <td>${item.api_key_required}</td>
        <td>${badge(item.trust_rank)}</td>
        <td>${item.connection_priority}</td>
        <td>${badge(item.connection_status)}</td>
      </tr>
    `);
  byId("catalogRows").innerHTML = rows.join("");
}

function renderVerification() {
  const rows = state.verification.slice(0, 10).map((item) => `
    <div class="listItem">
      <div>
        <strong>${item.api_id}</strong>
        <span>${item.verified_at} / ${item.note || ""}</span>
      </div>
      ${badge(item.result)}
    </div>
  `);
  byId("verificationList").innerHTML = rows.join("");
}

function renderExports() {
  byId("exportList").innerHTML = state.exports.map((item) => `
    <div class="listItem">
      <a href="${item.url}" target="_blank" rel="noreferrer">${item.name}</a>
      <span>open</span>
    </div>
  `).join("");
}

async function boot() {
  [state.summary, state.catalog, state.verification, state.exports] = await Promise.all([
    loadJson("/api/summary"),
    loadJson("/api/catalog"),
    loadJson("/api/verification"),
    loadJson("/api/export"),
  ]);
  renderSummary();
  renderCatalog();
  renderVerification();
  renderExports();
  byId("searchInput").addEventListener("input", renderCatalog);
  byId("categoryFilter").addEventListener("change", renderCatalog);
  byId("statusFilter").addEventListener("change", renderCatalog);
}

boot().catch((error) => {
  document.body.innerHTML = `<main><section class="panel"><h1>Load failed</h1><p>${error.message}</p></section></main>`;
});
