const state = {
  summary: null,
  metadata: null,
  catalog: [],
  verification: [],
  exports: [],
  liveMap: null,
  map: null,
  baseLayer: null,
  markers: [],
  tileLayers: new Map(),
};

const byId = (id) => document.getElementById(id);

async function loadJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// href values need scheme validation on top of HTML escaping: catalog data
// could otherwise smuggle javascript: or other dangerous schemes into links.
function safeUrl(value) {
  const url = String(value || "").trim();
  if (url.startsWith("/")) return escapeHtml(url);
  try {
    const protocol = new URL(url).protocol;
    if (protocol === "http:" || protocol === "https:") return escapeHtml(url);
  } catch {
    // fall through: not a parseable absolute URL
  }
  return "#";
}

function badge(value) {
  const text = escapeHtml(value || "-");
  const goodValues = new Set(["success", "接続成功", "A", "本格利用候補", "production"]);
  const warnValues = new Set(["warning", "要確認", "接続失敗", "保留", "調査中"]);
  const klass = goodValues.has(value) ? "good" : warnValues.has(value) ? "warn" : "";
  return `<span class="badge ${klass}">${text}</span>`;
}

function countBy(items, key) {
  return items.reduce((acc, item) => {
    const value = item[key] || "未設定";
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }, {});
}

function uniqueValues(key) {
  return [...new Set(state.catalog.map((item) => item[key]).filter(Boolean))].sort();
}

function fillSelect(id, values) {
  const select = byId(id);
  const first = select.options[0].outerHTML;
  select.innerHTML = first + values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
}

function average(items, key) {
  const values = items.map((item) => Number(item[key])).filter((value) => !Number.isNaN(value));
  if (!values.length) return 0;
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function renderSummary() {
  byId("catalogCount").textContent = state.summary.catalog_count;
  byId("verificationCount").textContent = state.summary.verification_count;
  byId("implementedCount").textContent = state.summary.implemented_count;
  byId("candidateCount").textContent = state.summary.candidate_count;
  byId("avgFit").textContent = average(state.catalog, "business_fit_score");
  byId("avgInt").textContent = average(state.catalog, "integration_score");
  byId("metadataLine").textContent = `本番台帳 ${state.metadata.record_count}件を反映（${state.metadata.imported_at} 更新）`;
  byId("importedAt").textContent = state.metadata.imported_at;
  byId("sourceName").textContent = state.metadata.source;
  const productionCount = state.catalog.filter((item) => item.catalog_mode === "production").length;
  byId("productionCoverage").textContent = `${productionCount}/${state.catalog.length}`;
}

function renderFilters() {
  const categories = uniqueValues("category");
  const statuses = uniqueValues("connection_status");
  fillSelect("categoryFilter", categories);
  fillSelect("statusFilter", statuses);
  fillSelect("regionFilter", uniqueValues("region"));
  fillSelect("trustRankFilter", uniqueValues("trust_rank"));
  fillSelect("mapCategoryFilter", categories);
  fillSelect("mapStatusFilter", statuses);
}

function renderDistribution() {
  const categoryCounts = countBy(state.catalog, "category");
  const maxCategory = Math.max(...Object.values(categoryCounts));
  byId("categoryList").innerHTML = Object.entries(categoryCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => `
      <div class="barItem">
        <div><strong>${escapeHtml(name)}</strong><span>${count}件</span></div>
        <div class="barTrack"><span data-ratio="${(count / maxCategory) * 100}"></span></div>
      </div>
    `).join("");
  // CSP blocks style attributes in generated HTML; CSSOM assignment is allowed.
  document.querySelectorAll("#categoryList .barTrack span").forEach((bar) => {
    bar.style.width = `${bar.dataset.ratio}%`;
  });

  const statusCounts = countBy(state.catalog, "connection_status");
  const maxStatus = Math.max(1, ...Object.values(statusCounts));
  // Known statuses render in the design's fixed order; any extras follow.
  const orderedStatuses = [
    ...STATUS_ORDER.filter((name) => statusCounts[name]),
    ...Object.keys(statusCounts).filter((name) => !STATUS_ORDER.includes(name)),
  ];
  byId("statusList").innerHTML = orderedStatuses.map((name) => `
    <div class="statusItem">
      <span class="statusItemLabel">${escapeHtml(name)}</span>
      <div class="statusBarTrack"><span class="${statusColorClassByName(name)}" data-ratio="${(statusCounts[name] / maxStatus) * 100}"></span></div>
      <strong>${statusCounts[name]}</strong>
    </div>
  `).join("");
  // CSP blocks style attributes in generated HTML; widths set via CSSOM.
  document.querySelectorAll("#statusList .statusBarTrack span").forEach((bar) => {
    bar.style.width = `${bar.dataset.ratio}%`;
  });
}

const STATUS_ORDER = ["実装接続済", "本格利用候補", "接続検証済", "接続候補", "調査中", "保留"];

// A small status pill (colored dot + label) reused by the adoption-top table.
function statusPill(status) {
  return `<span class="statusPill"><span class="statusPillDot ${statusColorClassByName(status)}"></span>${escapeHtml(status || "-")}</span>`;
}

// Maps a 40-100 score onto a 0-1 axis position (design spec), clamped so
// out-of-range values stay inside the plot area.
function fitnessMap01(value) {
  return Math.max(0, Math.min(1, (Number(value) - 40) / 60));
}

function renderFitnessMap() {
  const container = byId("fitnessMap");
  const items = state.catalog.filter(
    (item) => Number.isFinite(item.business_fit_score) && Number.isFinite(item.integration_score),
  );
  byId("fitnessCount").textContent = `N=${items.length}`;
  const dots = items.map((item) => `
    <span class="fitnessDot ${statusColorClass(item)}"
      data-name="${escapeHtml(item.name)}"
      data-x="${item.business_fit_score}" data-y="${item.integration_score}"
      data-size="${8 + Number(item.connection_priority || 2) * 3}"
      title="${escapeHtml(item.name)}｜事業適合度 ${item.business_fit_score}／連携実装性 ${item.integration_score}／優先度 ${escapeHtml(String(item.connection_priority))}"></span>
  `).join("");
  const ticks = `
    <span class="fitnessTick fitnessTickYTop">100</span>
    <span class="fitnessTick fitnessTickYBottom">40</span>
    <span class="fitnessTick fitnessTickXLeft">40</span>
    <span class="fitnessTick fitnessTickXRight">100 →</span>
  `;
  container.innerHTML = dots + ticks;
  // Position via CSSOM because the CSP blocks style attributes in generated HTML.
  container.querySelectorAll(".fitnessDot").forEach((dot) => {
    const size = Number(dot.dataset.size);
    const x = fitnessMap01(dot.dataset.x) * 100;
    const y = fitnessMap01(dot.dataset.y) * 100;
    dot.style.width = `${size}px`;
    dot.style.height = `${size}px`;
    dot.style.left = `calc(${x}% - ${size / 2}px)`;
    dot.style.bottom = `calc(${y}% - ${size / 2}px)`;
    // Clicking a point jumps to the catalog view filtered to that API.
    dot.addEventListener("click", () => {
      setView("catalog");
      byId("searchInput").value = dot.dataset.name;
      renderCatalog();
    });
  });
}

function renderTrustRegion() {
  const trustCounts = countBy(state.catalog, "trust_rank");
  byId("trustRankCards").innerHTML = ["A", "B", "C"].map((rank) => `
    <div class="trustCard trustCard-${rank}">
      <strong>${trustCounts[rank] || 0}</strong>
      <span>信頼度 ${rank}</span>
    </div>
  `).join("");

  const regionCounts = countBy(state.catalog, "region");
  const maxRegion = Math.max(1, ...Object.values(regionCounts));
  byId("regionBars").innerHTML = Object.entries(regionCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => `
      <div class="barItem">
        <div><strong>${escapeHtml(name)}</strong><span>${count}件</span></div>
        <div class="barTrack"><span class="regionBar" data-ratio="${(count / maxRegion) * 100}"></span></div>
      </div>
    `).join("");
  // CSP blocks style attributes in generated HTML; widths set via CSSOM.
  document.querySelectorAll("#regionBars .regionBar").forEach((bar) => {
    bar.style.width = `${bar.dataset.ratio}%`;
  });
}

function jumpToCatalog(name) {
  setView("catalog");
  byId("searchInput").value = name;
  renderCatalog();
}

function renderAdoptionTop() {
  const clamp100 = (value) => Math.max(0, Math.min(100, Number(value) || 0));
  const rows = [...state.catalog]
    .sort(
      (a, b) =>
        (b.connection_priority - a.connection_priority) ||
        (b.business_fit_score - a.business_fit_score),
    )
    .slice(0, 8);
  byId("adoptionTopRows").innerHTML = rows.map((item) => {
    const stars = "★".repeat(Math.max(0, Math.min(5, Number(item.connection_priority) || 0)));
    return `
      <tr class="adoptionRow" data-name="${escapeHtml(item.name)}">
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.category)}</td>
        <td class="priorityStars">${stars}</td>
        <td class="adoptionBars">
          <div class="miniBarTrack"><span class="miniBarFit" data-ratio="${clamp100(item.business_fit_score)}"></span></div>
          <div class="miniBarTrack"><span class="miniBarInteg" data-ratio="${clamp100(item.integration_score)}"></span></div>
        </td>
        <td>${statusPill(item.connection_status)}</td>
      </tr>
    `;
  }).join("");
  // CSP blocks style attributes in generated HTML; widths set via CSSOM.
  document.querySelectorAll("#adoptionTopRows .miniBarFit, #adoptionTopRows .miniBarInteg").forEach((bar) => {
    bar.style.width = `${bar.dataset.ratio}%`;
  });
  document.querySelectorAll("#adoptionTopRows .adoptionRow").forEach((row) => {
    row.addEventListener("click", () => jumpToCatalog(row.dataset.name));
  });
}

function filteredCatalog() {
  const q = byId("searchInput").value.trim().toLowerCase();
  const category = byId("categoryFilter").value;
  const status = byId("statusFilter").value;
  const region = byId("regionFilter").value;
  const trustRank = byId("trustRankFilter").value;
  const minPriority = byId("minPriorityFilter").value;
  return state.catalog
    .filter((item) => !q || JSON.stringify(item).toLowerCase().includes(q))
    .filter((item) => !category || item.category === category)
    .filter((item) => !status || item.connection_status === status)
    .filter((item) => !region || item.region === region)
    .filter((item) => !trustRank || item.trust_rank === trustRank)
    .filter((item) => !minPriority || item.connection_priority >= Number(minPriority))
    .sort((a, b) => b.connection_priority - a.connection_priority || a.id.localeCompare(b.id));
}

function scoreBreakdownHtml(item) {
  const sb = item.score_breakdown;
  if (!sb) return "";
  const row = (label, value, factors) =>
    `<div class="sbRow"><b>${escapeHtml(label)} ${escapeHtml(value)}</b><span>${escapeHtml((factors || []).join(" / "))}</span></div>`;
  return `
    <div class="scoreBreak">
      <div class="sbTitle">スコア算定の根拠（評価値）</div>
      ${row("事業適合度", sb.business_fit.score, sb.business_fit.factors)}
      ${row("連携実装性", sb.integration.score, sb.integration.factors)}
      ${row("信頼度", `${sb.trust.rank}（${sb.trust.score}）`, sb.trust.factors)}
      ${row("優先度", `${sb.priority.rank}（${sb.priority.score}）`, sb.priority.factors)}
    </div>
  `;
}

function renderCatalog() {
  const rows = filteredCatalog();
  byId("catalogResultCount").textContent = `${rows.length}件`;
  byId("catalogRows").innerHTML = rows.map((item) => `
    <tr>
      <td><strong>${escapeHtml(item.id)}</strong><br>${badge(item.catalog_mode)}</td>
      <td>${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.category)}<br><small>${escapeHtml(item.sub_category || "")}</small></td>
      <td>${escapeHtml(item.provider)}</td>
      <td>${escapeHtml(item.region)}</td>
      <td>${escapeHtml(item.api_key_required)}<br><small>${escapeHtml(item.auth_type)}</small></td>
      <td>${badge(item.trust_rank)}</td>
      <td>${item.connection_priority}</td>
      <td>${badge(item.connection_status)}</td>
      <td>
        <details>
          <summary>${escapeHtml(item.usage_summary || "利用説明を確認")}</summary>
          <p>${escapeHtml(item.usage_notes || "").replaceAll("\n", "<br>")}</p>
          <div class="detailLinks">
            <a href="${safeUrl(item.official_url)}" target="_blank" rel="noreferrer">公式</a>
            <a href="${safeUrl(item.document_url || item.official_url)}" target="_blank" rel="noreferrer">仕様</a>
            ${item.sample_endpoint ? `<a href="${safeUrl(item.sample_endpoint)}" target="_blank" rel="noreferrer">サンプル</a>` : ""}
          </div>
          <small>形式: ${escapeHtml((item.data_formats || []).join(", "))}</small>
          ${scoreBreakdownHtml(item)}
        </details>
      </td>
    </tr>
  `).join("");
}

function renderVerification() {
  const latestRows = [...state.verification]
    .sort((a, b) => b.verified_at.localeCompare(a.verified_at))
    .slice(0, 5);
  const resultLabel = { success: "接続成功", failure: "接続失敗", warning: "要確認", skipped: "スキップ" };
  byId("verificationList").innerHTML = latestRows.map((item) => `
    <div class="listItem">
      <div>
        <strong>${escapeHtml(item.api_id)}</strong>
        <span>${escapeHtml(String(item.verified_at).slice(0, 10))} 検証</span>
      </div>
      ${badge(resultLabel[item.result] || item.result)}
    </div>
  `).join("");
}

function exportKind(name) {
  if (name.endsWith(".md")) return "Markdown";
  if (name.endsWith(".csv")) return "CSV";
  if (name.endsWith(".json")) return "JSON";
  return "File";
}

// Icon label + color class per file type (see .exportIcon-* in styles.css).
function exportIcon(name) {
  if (name.endsWith(".md")) return { label: "MD", cls: "exportIcon-md" };
  if (name.endsWith(".csv")) return { label: "CSV", cls: "exportIcon-csv" };
  if (name.endsWith(".json")) return { label: "JSON", cls: "exportIcon-json" };
  return { label: "FILE", cls: "exportIcon-file" };
}

function renderExports() {
  byId("exportList").innerHTML = state.exports.map((item) => {
    const icon = exportIcon(item.name);
    return `
    <article class="exportItem">
      <div class="exportItemHead">
        <span class="exportIcon ${icon.cls}">${icon.label}</span>
        <div>
          <strong>${escapeHtml(item.name)}</strong>
          <span>${exportKind(item.name)} / 本番データ成果物</span>
        </div>
      </div>
      <div class="exportActions">
        <a href="${safeUrl(item.url)}" target="_blank" rel="noreferrer">開く</a>
        <a href="${safeUrl(item.download_url || `${item.url}?download=1`)}" download>ダウンロード</a>
      </div>
    </article>
  `;
  }).join("");

  const downloadAll = byId("downloadAllExports");
  if (downloadAll) {
    downloadAll.addEventListener("click", () => {
      state.exports.forEach((item, index) => {
        // Stagger clicks so the browser does not drop concurrent downloads.
        setTimeout(() => {
          const anchor = document.createElement("a");
          anchor.setAttribute("href", safeUrl(item.download_url || `${item.url}?download=1`));
          anchor.setAttribute("download", "");
          document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
        }, index * 400);
      });
    });
  }
}

// CSP blocks style attributes in generated HTML, so status colors are
// applied through CSS classes (see .statusColor-* in styles.css).
// The six-status palette is shared by map markers, feature dots, the fitness
// scatter, status bars, legend and adoption pills.
function statusColorClassByName(status) {
  switch (status) {
    case "実装接続済":
      return "statusColor-impl";
    case "本格利用候補":
      return "statusColor-full";
    case "接続検証済":
      return "statusColor-verified";
    case "接続候補":
      return "statusColor-candidate";
    case "調査中":
      return "statusColor-survey";
    case "保留":
      return "statusColor-hold";
    default:
      return "statusColor-other";
  }
}

function statusColorClass(feature) {
  return statusColorClassByName(feature.connection_status);
}

function markerIcon(feature) {
  return L.divIcon({
    className: "catalogMarker",
    html: `<span class="${statusColorClass(feature)}">${escapeHtml(feature.connection_priority)}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function filteredMapFeatures() {
  const category = byId("mapCategoryFilter").value;
  const status = byId("mapStatusFilter").value;
  return state.liveMap.features
    .filter((item) => !category || item.category === category)
    .filter((item) => !status || item.connection_status === status);
}

function renderMapFeatures() {
  state.markers.forEach((marker) => marker.remove());
  state.markers = filteredMapFeatures().map((feature) => {
    const marker = L.marker([feature.lat, feature.lon], { icon: markerIcon(feature) }).addTo(state.map);
    marker.bindPopup(`
      <strong>${escapeHtml(feature.name)}</strong><br>
      ${escapeHtml(feature.provider)} / ${escapeHtml(feature.category)}<br>
      状態: ${escapeHtml(feature.connection_status)} / 検証: ${escapeHtml(feature.latest_verification)}<br>
      <small>${escapeHtml(feature.usage_summary)}</small>
    `);
    return marker;
  });
  const features = filteredMapFeatures();
  byId("featureCount").textContent = `${features.length}件`;
  byId("mapFeatureList").innerHTML = features.map((feature) => `
    <button class="mapFeatureButton" data-id="${escapeHtml(feature.id)}">
      <span class="featureDot ${statusColorClass(feature)}"></span>
      <span class="featureBody">
        <strong>${escapeHtml(feature.name)}</strong>
        <span>${escapeHtml(feature.category)} / ${escapeHtml(feature.connection_status)}</span>
      </span>
    </button>
  `).join("");
  document.querySelectorAll(".mapFeatureButton").forEach((button) => {
    button.addEventListener("click", () => {
      const feature = state.liveMap.features.find((item) => item.id === button.dataset.id);
      if (!feature) return;
      state.map.setView([feature.lat, feature.lon], 7);
    });
  });
}

function renderLayerList() {
  const layers = state.liveMap.layers.slice(0, 10);
  byId("layerCount").textContent = `${layers.length}層`;
  byId("layerList").innerHTML = layers.map((layer, index) => `
    <label class="layerToggle">
      <input type="checkbox" data-layer="${escapeHtml(layer.id)}" />
      <span>${escapeHtml(layer.name)}</span>
    </label>
  `).join("");
  document.querySelectorAll("[data-layer]").forEach((input) => {
    input.addEventListener("change", () => {
      const layer = state.tileLayers.get(input.dataset.layer);
      if (!layer) return;
      if (input.checked) layer.addTo(state.map);
      else layer.remove();
    });
  });
}

const BASE_MAPS = [
  {
    id: "osm",
    name: "OSM 標準",
    catalogId: "OSM-TILE-001",
    dotClass: "layerDot-osm",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  },
  {
    id: "osm_hot",
    name: "Humanitarian (HOT)",
    catalogId: "OSM-HOT",
    dotClass: "layerDot-hot",
    url: "https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
    subdomains: "abc",
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors, Tiles style by HOT",
  },
  {
    id: "osm_cyclosm",
    name: "CyclOSM",
    catalogId: "OSM-CYCLOSM",
    dotClass: "layerDot-cyclosm",
    url: "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
    subdomains: "abc",
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors, Tiles style by CyclOSM",
  },
  {
    id: "gsi_pale",
    name: "地理院 淡色地図",
    catalogId: "GSI-PALE",
    dotClass: "layerDot-gsi",
    url: "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png",
    maxZoom: 18,
    attribution: "&copy; <a href='https://maps.gsi.go.jp/development/ichiran.html'>国土地理院</a>",
  },
  {
    id: "gsi_std",
    name: "地理院 標準地図",
    catalogId: "GSI-STD",
    dotClass: "layerDot-gsi",
    url: "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
    maxZoom: 18,
    attribution: "&copy; <a href='https://maps.gsi.go.jp/development/ichiran.html'>国土地理院</a>",
  },
];

// A translucent overlay badge on the map showing the active base layer.
// Created lazily because Leaflet manages the #map container's children.
function updateCurrentLayerBadge(name) {
  let badge = byId("currentLayerBadge");
  if (!badge) {
    badge = document.createElement("div");
    badge.id = "currentLayerBadge";
    badge.className = "currentLayerBadge";
    byId("map").appendChild(badge);
  }
  badge.textContent = `CURRENT LAYER: ${name}`;
}

function setBaseMap(id) {
  const entry = BASE_MAPS.find((base) => base.id === id) || BASE_MAPS[0];
  if (state.baseLayer) state.baseLayer.remove();
  const options = { maxZoom: entry.maxZoom, attribution: entry.attribution };
  if (entry.subdomains) options.subdomains = entry.subdomains;
  state.baseLayer = L.tileLayer(entry.url, options).addTo(state.map);
  updateCurrentLayerBadge(entry.name);
}

function renderBaseMapList() {
  byId("baseMapList").innerHTML = BASE_MAPS.map((base, index) => `
    <label class="layerToggle">
      <input type="radio" name="baseMap" value="${escapeHtml(base.id)}" ${index === 0 ? "checked" : ""} />
      <span class="layerDot ${base.dotClass}"></span>
      <span>${escapeHtml(base.name)}<small class="layerSubId">${escapeHtml(base.catalogId)}</small></span>
    </label>
  `).join("");
  document.querySelectorAll('input[name="baseMap"]').forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) setBaseMap(input.value);
    });
  });
}

function overlayOpacity() {
  const slider = byId("overlayOpacity");
  return slider ? Number(slider.value) / 100 : 0.55;
}

function initMap() {
  if (!window.L) {
    byId("map").innerHTML = "<p>地図ライブラリを読み込めませんでした。ネットワーク接続を確認してください。</p>";
    return;
  }
  const { center } = state.liveMap;
  state.map = L.map("map", { scrollWheelZoom: true }).setView([center.lat, center.lon], center.zoom);
  setBaseMap(BASE_MAPS[0].id);
  // Catalog tiles are overlays only: none is shown by default so the base
  // map stays readable; users opt in per layer from the sidebar.
  state.liveMap.layers.slice(0, 10).forEach((layer) => {
    const tileLayer = L.tileLayer(layer.tile_url, {
      maxZoom: 18,
      opacity: overlayOpacity(),
      attribution: escapeHtml(layer.attribution || layer.provider),
    });
    state.tileLayers.set(layer.id, tileLayer);
  });
  byId("overlayOpacity").addEventListener("input", () => {
    const value = overlayOpacity();
    byId("overlayOpacityValue").textContent = `${Math.round(value * 100)}%`;
    state.tileLayers.forEach((layer) => layer.setOpacity(value));
  });
  renderBaseMapList();
  renderLayerList();
  renderMapFeatures();
}

const VIEWS = {
  dashboard: { kicker: "OVERVIEW", title: "採用ダッシュボード", sub: "スコア・接続ステータス・優先度の全体像" },
  catalog: { kicker: "LEDGER", title: "API・公開データ台帳", sub: "検索・絞り込み・スコア比較とAPI詳細を本番データで確認します。" },
  flow: { kicker: "HOW TO USE", title: "API活用フロー", sub: "選定から本番実装までの5ステップと、データ形式別の接続早見表。" },
  map: { kicker: "LIVE MAP", title: "地理空間ライブマップ", sub: "OpenStreetMap のタイルを実接続して表示します。" },
  exports: { kicker: "EXPORTS", title: "成果物エクスポート", sub: "台帳データから各種ファイルを生成・出力します。" },
};

function setView(view) {
  if (!VIEWS[view]) view = "dashboard";
  document.querySelectorAll(".view").forEach((el) => {
    el.hidden = el.dataset.view !== view;
  });
  document.querySelectorAll(".navBtn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  const meta = VIEWS[view];
  byId("viewKicker").textContent = meta.kicker;
  byId("viewTitle").textContent = meta.title;
  byId("viewSub").textContent = meta.sub;
  if (view === "map" && state.map) {
    state.map.invalidateSize();
    renderMapFeatures();
  }
  window.scrollTo(0, 0);
}

function initNav() {
  document.querySelectorAll(".navBtn").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
  setView("dashboard");
}

function setNavBadges() {
  byId("navBadgeCatalog").textContent = state.catalog.length;
  byId("navBadgeMap").textContent = "OSM";
  byId("navBadgeExports").textContent = state.exports.length;
  const lastCheck = byId("sideLastCheck");
  if (lastCheck) lastCheck.textContent = state.metadata.imported_at || "-";
}

// Light/dark theme via [data-theme] on <html>, persisted in localStorage.
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const toggle = byId("themeToggle");
  if (toggle) toggle.textContent = theme === "dark" ? "☀" : "☾";
}

function initTheme() {
  applyTheme(localStorage.getItem("theme") || "light");
  const toggle = byId("themeToggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("theme", next);
  });
}

async function boot() {
  [state.summary, state.metadata, state.catalog, state.verification, state.exports, state.liveMap] = await Promise.all([
    loadJson("/api/summary"),
    loadJson("/api/metadata"),
    loadJson("/api/catalog"),
    loadJson("/api/verification"),
    loadJson("/api/export"),
    loadJson("/api/live-map"),
  ]);
  renderSummary();
  renderFilters();
  renderDistribution();
  renderFitnessMap();
  renderTrustRegion();
  renderAdoptionTop();
  renderCatalog();
  renderVerification();
  renderExports();
  initMap();
  initNav();
  setNavBadges();
  initTheme();
  ["searchInput", "categoryFilter", "statusFilter", "regionFilter", "trustRankFilter", "minPriorityFilter"].forEach((id) => {
    byId(id).addEventListener("input", renderCatalog);
    byId(id).addEventListener("change", renderCatalog);
  });
  ["mapCategoryFilter", "mapStatusFilter"].forEach((id) => {
    byId(id).addEventListener("change", renderMapFeatures);
  });
}

boot().catch((error) => {
  document.body.innerHTML = `<main><section class="panel"><h1>Load failed</h1><p>${escapeHtml(error.message)}</p></section></main>`;
});
