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
  user: null,
  manage: { items: [], loaded: false, editingId: null },
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
  const goodValues = new Set([
    "success",
    "接続成功",
    "A",
    "本格利用候補",
    "production",
  ]);
  const warnValues = new Set([
    "warning",
    "要確認",
    "接続失敗",
    "保留",
    "調査中",
  ]);
  const klass = goodValues.has(value)
    ? "good"
    : warnValues.has(value)
      ? "warn"
      : "";
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
  return [
    ...new Set(state.catalog.map((item) => item[key]).filter(Boolean)),
  ].sort();
}

function fillSelect(id, values) {
  const select = byId(id);
  const first = select.options[0].outerHTML;
  select.innerHTML =
    first +
    values
      .map(
        (value) =>
          `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`,
      )
      .join("");
}

function average(items, key) {
  const values = items
    .map((item) => Number(item[key]))
    .filter((value) => !Number.isNaN(value));
  if (!values.length) return 0;
  return Math.round(
    values.reduce((sum, value) => sum + value, 0) / values.length,
  );
}

function renderSummary() {
  byId("catalogCount").textContent = state.summary.catalog_count;
  byId("verificationCount").textContent = state.summary.verification_count;
  byId("implementedCount").textContent = state.summary.implemented_count;
  byId("candidateCount").textContent = state.summary.candidate_count;
  byId("avgFit").textContent = average(state.catalog, "business_fit_score");
  byId("avgInt").textContent = average(state.catalog, "integration_score");
  byId("serviceHost").textContent = window.location.host;
  byId("metadataLine").textContent =
    `本番台帳 ${state.metadata.record_count}件を反映（${state.metadata.imported_at} 更新）`;
  byId("importedAt").textContent = state.metadata.imported_at;
  byId("sourceName").textContent = state.metadata.source;
  const productionCount = state.catalog.filter(
    (item) => item.catalog_mode === "production",
  ).length;
  byId("productionCoverage").textContent =
    `${productionCount}/${state.catalog.length}`;
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
    .map(
      ([name, count]) => `
      <div class="barItem">
        <div><strong>${escapeHtml(name)}</strong><span>${count}件</span></div>
        <div class="barTrack"><span data-ratio="${(count / maxCategory) * 100}"></span></div>
      </div>
    `,
    )
    .join("");
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
  byId("statusList").innerHTML = orderedStatuses
    .map(
      (name) => `
    <div class="statusItem">
      <span class="statusItemLabel">${escapeHtml(name)}</span>
      <div class="statusBarTrack"><span class="${statusColorClassByName(name)}" data-ratio="${(statusCounts[name] / maxStatus) * 100}"></span></div>
      <strong>${statusCounts[name]}</strong>
    </div>
  `,
    )
    .join("");
  // CSP blocks style attributes in generated HTML; widths set via CSSOM.
  document
    .querySelectorAll("#statusList .statusBarTrack span")
    .forEach((bar) => {
      bar.style.width = `${bar.dataset.ratio}%`;
    });
}

const STATUS_ORDER = [
  "実装接続済",
  "本格利用候補",
  "接続検証済",
  "接続候補",
  "調査中",
  "保留",
];

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
    (item) =>
      Number.isFinite(item.business_fit_score) &&
      Number.isFinite(item.integration_score),
  );
  byId("fitnessCount").textContent = `N=${items.length}`;
  const dots = items
    .map(
      (item) => `
    <span class="fitnessDot ${statusColorClass(item)}"
      data-name="${escapeHtml(item.name)}"
      data-x="${item.business_fit_score}" data-y="${item.integration_score}"
      data-size="${8 + Number(item.connection_priority || 2) * 3}"
      title="${escapeHtml(item.name)}｜事業適合度 ${item.business_fit_score}／連携実装性 ${item.integration_score}／優先度 ${escapeHtml(String(item.connection_priority))}"></span>
  `,
    )
    .join("");
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
  byId("trustRankCards").innerHTML = ["A", "B", "C"]
    .map(
      (rank) => `
    <div class="trustCard trustCard-${rank}">
      <strong>${trustCounts[rank] || 0}</strong>
      <span>信頼度 ${rank}</span>
    </div>
  `,
    )
    .join("");

  const regionCounts = countBy(state.catalog, "region");
  const maxRegion = Math.max(1, ...Object.values(regionCounts));
  byId("regionBars").innerHTML = Object.entries(regionCounts)
    .sort((a, b) => b[1] - a[1])
    .map(
      ([name, count]) => `
      <div class="barItem">
        <div><strong>${escapeHtml(name)}</strong><span>${count}件</span></div>
        <div class="barTrack"><span class="regionBar" data-ratio="${(count / maxRegion) * 100}"></span></div>
      </div>
    `,
    )
    .join("");
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
        b.connection_priority - a.connection_priority ||
        b.business_fit_score - a.business_fit_score,
    )
    .slice(0, 8);
  byId("adoptionTopRows").innerHTML = rows
    .map((item) => {
      const stars = "★".repeat(
        Math.max(0, Math.min(5, Number(item.connection_priority) || 0)),
      );
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
    })
    .join("");
  // CSP blocks style attributes in generated HTML; widths set via CSSOM.
  document
    .querySelectorAll(
      "#adoptionTopRows .miniBarFit, #adoptionTopRows .miniBarInteg",
    )
    .forEach((bar) => {
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
    .filter(
      (item) => !minPriority || item.connection_priority >= Number(minPriority),
    )
    .sort(
      (a, b) =>
        b.connection_priority - a.connection_priority ||
        a.id.localeCompare(b.id),
    );
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
  byId("catalogRows").innerHTML = rows
    .map(
      (item) => `
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
  `,
    )
    .join("");
}

function renderVerification() {
  const latestRows = [...state.verification]
    .sort((a, b) => b.verified_at.localeCompare(a.verified_at))
    .slice(0, 5);
  const resultLabel = {
    success: "接続成功",
    failure: "接続失敗",
    warning: "要確認",
    skipped: "スキップ",
  };
  byId("verificationList").innerHTML = latestRows
    .map(
      (item) => `
    <div class="listItem">
      <div>
        <strong>${escapeHtml(item.api_id)}</strong>
        <span>${escapeHtml(String(item.verified_at).slice(0, 10))} 検証</span>
      </div>
      ${badge(resultLabel[item.result] || item.result)}
    </div>
  `,
    )
    .join("");
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
  byId("exportList").innerHTML = state.exports
    .map((item) => {
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
    })
    .join("");

  const downloadAll = byId("downloadAllExports");
  if (downloadAll) {
    downloadAll.addEventListener("click", () => {
      state.exports.forEach((item, index) => {
        // Stagger clicks so the browser does not drop concurrent downloads.
        setTimeout(() => {
          const anchor = document.createElement("a");
          anchor.setAttribute(
            "href",
            safeUrl(item.download_url || `${item.url}?download=1`),
          );
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
    const marker = L.marker([feature.lat, feature.lon], {
      icon: markerIcon(feature),
    }).addTo(state.map);
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
  byId("mapFeatureList").innerHTML = features
    .map(
      (feature) => `
    <button class="mapFeatureButton" data-id="${escapeHtml(feature.id)}">
      <span class="featureDot ${statusColorClass(feature)}"></span>
      <span class="featureBody">
        <strong>${escapeHtml(feature.name)}</strong>
        <span>${escapeHtml(feature.category)} / ${escapeHtml(feature.connection_status)}</span>
      </span>
    </button>
  `,
    )
    .join("");
  document.querySelectorAll(".mapFeatureButton").forEach((button) => {
    button.addEventListener("click", () => {
      const feature = state.liveMap.features.find(
        (item) => item.id === button.dataset.id,
      );
      if (!feature) return;
      state.map.setView([feature.lat, feature.lon], 7);
    });
  });
}

function renderLayerList() {
  const layers = state.liveMap.layers.slice(0, 10);
  byId("layerCount").textContent = `${layers.length}層`;
  byId("layerList").innerHTML = layers
    .map(
      (layer, index) => `
    <label class="layerToggle">
      <input type="checkbox" data-layer="${escapeHtml(layer.id)}" />
      <span>${escapeHtml(layer.name)}</span>
    </label>
  `,
    )
    .join("");
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
    attribution:
      "&copy; <a href='https://maps.gsi.go.jp/development/ichiran.html'>国土地理院</a>",
  },
  {
    id: "gsi_std",
    name: "地理院 標準地図",
    catalogId: "GSI-STD",
    dotClass: "layerDot-gsi",
    url: "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
    maxZoom: 18,
    attribution:
      "&copy; <a href='https://maps.gsi.go.jp/development/ichiran.html'>国土地理院</a>",
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
  byId("baseMapList").innerHTML = BASE_MAPS.map(
    (base, index) => `
    <label class="layerToggle">
      <input type="radio" name="baseMap" value="${escapeHtml(base.id)}" ${index === 0 ? "checked" : ""} />
      <span class="layerDot ${base.dotClass}"></span>
      <span>${escapeHtml(base.name)}<small class="layerSubId">${escapeHtml(base.catalogId)}</small></span>
    </label>
  `,
  ).join("");
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
    byId("map").innerHTML =
      "<p>地図ライブラリを読み込めませんでした。ネットワーク接続を確認してください。</p>";
    return;
  }
  const { center } = state.liveMap;
  state.map = L.map("map", { scrollWheelZoom: true }).setView(
    [center.lat, center.lon],
    center.zoom,
  );
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

// ===================== Auth / RBAC (Issue #64) =====================
// Server-side RBAC is authoritative; every role check here is UX gating only.

const CATALOG_ROLES = ["Admin", "Editor", "Verifier", "Approver", "Viewer"];

function hasRole(...names) {
  if (!state.user) return false;
  return names.some((name) => state.user.roles.includes(`Catalog.${name}`));
}

const isStaff = () => hasRole("Editor", "Verifier", "Approver", "Admin");

async function loadUser() {
  // A failed /auth/me (api_v1 down, anonymous, ...) must never break the
  // read-only catalog UI, so every failure path resolves to "not signed in".
  try {
    const response = await fetch("/auth/me");
    state.user = response.ok ? await response.json() : null;
  } catch {
    state.user = null;
  }
}

function renderAuthArea() {
  const loginButton = byId("loginButton");
  const userBox = byId("userBox");
  if (!loginButton || !userBox) return;
  if (!state.user) {
    loginButton.hidden = false;
    userBox.hidden = true;
    return;
  }
  loginButton.hidden = true;
  userBox.hidden = false;
  byId("userName").textContent = state.user.name || state.user.sub;
  byId("roleChips").innerHTML = CATALOG_ROLES.filter((role) =>
    state.user.roles.includes(`Catalog.${role}`),
  )
    .map(
      (role) =>
        `<span class="roleChip role-${role.toLowerCase()}">${role}</span>`,
    )
    .join("");
}

function updateNavForRoles() {
  const navManage = byId("navManage");
  if (navManage) navManage.hidden = !isStaff();
  const newEntryButton = byId("newEntryButton");
  if (newEntryButton) newEntryButton.hidden = !hasRole("Editor", "Admin");
}

// ===================== Local login (username/password) =====================

function openLoginDialog() {
  const dialog = byId("loginDialog");
  if (!dialog) return;
  byId("loginError").hidden = true;
  byId("loginForm").reset();
  dialog.showModal();
  byId("loginUsername").focus();
}

function wireLoginUI() {
  const loginButton = byId("loginButton");
  const dialog = byId("loginDialog");
  if (!loginButton || !dialog) return;
  // The anchor keeps /auth/login as a no-JS fallback (the server redirects
  // back to /?login=1 in local mode); with JS we open the dialog directly.
  loginButton.addEventListener("click", (event) => {
    event.preventDefault();
    openLoginDialog();
  });
  byId("loginCancel").addEventListener("click", () => dialog.close());
  byId("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = byId("loginError");
    const submit = byId("loginSubmit");
    error.hidden = true;
    submit.disabled = true;
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: byId("loginUsername").value,
          password: byId("loginPassword").value,
        }),
      });
      if (response.ok) {
        dialog.close();
        window.location.reload();
        return;
      }
      error.textContent =
        response.status === 423
          ? "アカウントが一時的にロックされています。15分ほど待って再試行してください"
          : response.status === 503
            ? "編集サービスに接続できません（api_v1 未起動）"
            : "ユーザー名またはパスワードが違います";
      error.hidden = false;
    } catch {
      error.textContent = "通信に失敗しました";
      error.hidden = false;
    } finally {
      submit.disabled = false;
    }
  });
  if (new URLSearchParams(window.location.search).has("login") && !state.user) {
    openLoginDialog();
  }
}

// ===================== Manage view (Issue #64) =====================

const WORKFLOW_LABELS = {
  draft: "下書き",
  in_review: "レビュー中",
  pending_approval: "承認待ち",
  published: "公開中",
  rejected: "差し戻し済",
};

const TRANSITION_LABELS = {
  submit: "レビュー依頼",
  review_ok: "レビューOK",
  approve: "承認・公開",
  send_back: "差し戻し",
  reopen: "編集再開",
};

const ENTRY_LIST_FIELDS = ["data_formats", "tags"];
const ENTRY_NUMBER_FIELDS = [
  "connection_priority",
  "business_fit_score",
  "integration_score",
];
// Optional in EntryCreate/EntryPatch: clearing one of these sends an explicit
// null so the server updates it (omitted keys mean "unchanged" under
// exclude_unset). Required-on-create fields are never nulled — the form marks
// them `required`, matching the API contract.
const ENTRY_NULLABLE_FIELDS = [
  "sub_category",
  "region",
  "endpoint_template",
  "sample_endpoint",
  "auth_type",
  "license_note",
  "commercial_use",
  "update_frequency",
  "trust_rank",
  "connection_priority",
  "business_fit_score",
  "integration_score",
  "usage_summary",
  "usage_notes",
  "risk_note",
];

function formatDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI/pydantic validation errors: [{loc, msg, ...}, ...]
    return detail
      .map(
        (item) =>
          `${(item.loc || []).filter((part) => part !== "body").join(".")}: ${item.msg}`,
      )
      .join(" / ");
  }
  return JSON.stringify(detail);
}

function apiErrorMessage(status, detail) {
  if (status === 401)
    return "ログインが必要です。右上の「ログイン」からサインインしてください。";
  if (status === 403) return `この操作を行う権限がありません（${detail}）`;
  if (status === 503)
    return "編集サービス(API v1)に接続できません。管理者に確認してください。";
  return detail;
}

async function apiV1(path, options = {}) {
  const init = { method: options.method || "GET", headers: {} };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw Object.assign(
      new Error("サーバーに接続できません。ネットワークを確認してください。"),
      {
        status: 0,
      },
    );
  }
  let payload = null;
  if (response.status !== 204) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    const detail =
      payload && payload.detail !== undefined
        ? formatDetail(payload.detail)
        : `HTTP ${response.status}`;
    throw Object.assign(new Error(apiErrorMessage(response.status, detail)), {
      status: response.status,
    });
  }
  return payload;
}

function showManageNotice(message, kind = "error") {
  const notice = byId("manageNotice");
  if (!notice) return;
  notice.textContent = message;
  notice.classList.toggle("error", kind === "error");
  notice.classList.toggle("success", kind === "success");
  notice.hidden = false;
}

function askReason(title, text) {
  // Resolves with the entered reason, or null when cancelled.
  return new Promise((resolve) => {
    const dialog = byId("reasonDialog");
    byId("reasonDialogTitle").textContent = title;
    byId("reasonDialogText").textContent = text;
    const input = byId("reasonInput");
    input.value = "";
    const form = byId("reasonForm");
    const cancelButton = byId("reasonCancel");
    const done = (value) => {
      form.removeEventListener("submit", onSubmit);
      cancelButton.removeEventListener("click", onCancel);
      dialog.removeEventListener("cancel", onDialogCancel);
      dialog.close();
      resolve(value);
    };
    const onSubmit = (event) => {
      event.preventDefault();
      if (!input.value.trim()) return;
      done(input.value.trim());
    };
    const onCancel = () => done(null);
    const onDialogCancel = (event) => {
      event.preventDefault();
      done(null);
    };
    form.addEventListener("submit", onSubmit);
    cancelButton.addEventListener("click", onCancel);
    dialog.addEventListener("cancel", onDialogCancel);
    dialog.showModal();
    input.focus();
  });
}

async function loadManageEntries() {
  const params = new URLSearchParams({ limit: "500" });
  const keyword = byId("manageSearch").value.trim();
  if (keyword) params.set("keyword", keyword);
  try {
    const data = await apiV1(`/api/v1/entries?${params.toString()}`);
    state.manage.items = data.items;
    state.manage.loaded = true;
    renderManage();
    const navBadge = byId("navBadgeManage");
    if (navBadge) navBadge.textContent = data.total;
  } catch (error) {
    showManageNotice(error.message);
  }
}

function transitionsForEntry(item) {
  const transitions = [];
  const wfState = item.workflow_state;
  if (
    (wfState === "draft" || wfState === "rejected") &&
    hasRole("Editor", "Admin")
  ) {
    transitions.push("submit");
  }
  if (wfState === "in_review" && hasRole("Verifier", "Admin")) {
    transitions.push("review_ok");
  }
  if (wfState === "pending_approval" && hasRole("Approver", "Admin")) {
    transitions.push("approve");
  }
  // Mirrors _TRANSITIONS in api_v1.py: send_back is allowed from either
  // review state for any of Verifier/Approver/Admin (state-independent).
  if (
    (wfState === "in_review" || wfState === "pending_approval") &&
    hasRole("Verifier", "Approver", "Admin")
  ) {
    transitions.push("send_back");
  }
  if (wfState === "published" && hasRole("Editor", "Admin")) {
    transitions.push("reopen");
  }
  return transitions;
}

function renderManage() {
  const rows = byId("manageRows");
  if (!rows) return;
  const stateFilter = byId("manageStateFilter").value;
  const items = state.manage.items.filter(
    (item) => !stateFilter || item.workflow_state === stateFilter,
  );
  if (!items.length) {
    rows.innerHTML = `<tr><td colspan="5" class="emptyCell">${
      state.manage.loaded ? "該当するエントリがありません。" : "読込中…"
    }</td></tr>`;
    return;
  }
  rows.innerHTML = items
    .map((item) => {
      const wfState = item.workflow_state;
      const buttons = [];
      if (
        hasRole("Editor", "Admin") &&
        (wfState === "draft" || wfState === "rejected")
      ) {
        buttons.push(
          `<button type="button" class="rowButton" data-act="edit" data-id="${escapeHtml(item.id)}">編集</button>`,
        );
      }
      transitionsForEntry(item).forEach((action) => {
        buttons.push(
          `<button type="button" class="rowButton" data-act="transition" data-action="${action}" data-id="${escapeHtml(item.id)}">${TRANSITION_LABELS[action]}</button>`,
        );
      });
      buttons.push(
        `<button type="button" class="rowButton" data-act="versions" data-id="${escapeHtml(item.id)}">版履歴</button>`,
      );
      if (hasRole("Admin")) {
        buttons.push(
          `<button type="button" class="rowButton danger" data-act="delete" data-id="${escapeHtml(item.id)}">削除</button>`,
        );
      }
      return `<tr>
        <td class="mono">${escapeHtml(item.id)}</td>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.provider)}</td>
        <td><span class="wfBadge wf-${escapeHtml(wfState)}">${escapeHtml(WORKFLOW_LABELS[wfState] || wfState)}</span></td>
        <td class="rowActions">${buttons.join("")}</td>
      </tr>`;
    })
    .join("");
}

async function doTransition(id, action) {
  const reason = await askReason(
    `${TRANSITION_LABELS[action]} — ${id}`,
    `エントリ ${id} に「${TRANSITION_LABELS[action]}」を実行します。`,
  );
  if (reason === null) return;
  try {
    const result = await apiV1(
      `/api/v1/entries/${encodeURIComponent(id)}/transitions`,
      {
        method: "POST",
        body: { action, reason },
      },
    );
    showManageNotice(
      `${id} を「${WORKFLOW_LABELS[result.state] || result.state}」にしました。`,
      "success",
    );
    await loadManageEntries();
  } catch (error) {
    showManageNotice(error.message);
  }
}

async function doDelete(id) {
  const reason = await askReason(
    `削除 — ${id}`,
    `エントリ ${id} を論理削除します（版履歴と監査ログは残ります）。`,
  );
  if (reason === null) return;
  try {
    await apiV1(
      `/api/v1/entries/${encodeURIComponent(id)}?reason=${encodeURIComponent(reason)}`,
      {
        method: "DELETE",
      },
    );
    showManageNotice(`${id} を削除しました。`, "success");
    await loadManageEntries();
  } catch (error) {
    showManageNotice(error.message);
  }
}

async function openVersions(id) {
  const dialog = byId("versionsDialog");
  byId("versionsDialogTitle").textContent = `版履歴 — ${id}`;
  const rows = byId("versionRows");
  rows.innerHTML = `<tr><td colspan="4" class="emptyCell">読込中…</td></tr>`;
  dialog.showModal();
  try {
    const data = await apiV1(
      `/api/v1/entries/${encodeURIComponent(id)}/versions`,
    );
    if (!data.items.length) {
      rows.innerHTML = `<tr><td colspan="4" class="emptyCell">版がまだありません。</td></tr>`;
      return;
    }
    rows.innerHTML = data.items
      .map(
        (version) => `<tr>
        <td class="mono">v${Number(version.version)}</td>
        <td>${escapeHtml(version.created_at)}</td>
        <td>${escapeHtml(version.created_by)}</td>
        <td class="rowActions">${
          hasRole("Admin")
            ? `<button type="button" class="rowButton" data-restore="${Number(version.version)}" data-id="${escapeHtml(id)}">この版に復元</button>`
            : ""
        }</td>
      </tr>`,
      )
      .join("");
  } catch (error) {
    rows.innerHTML = `<tr><td colspan="4" class="emptyCell">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function onVersionRowAction(event) {
  const button = event.target.closest("button[data-restore]");
  if (!button) return;
  const id = button.dataset.id;
  const version = Number(button.dataset.restore);
  byId("versionsDialog").close();
  const reason = await askReason(
    `復元 — ${id}`,
    `エントリ ${id} を v${version} の内容に復元します（draft状態のみ実行できます）。`,
  );
  if (reason === null) return;
  try {
    await apiV1(`/api/v1/entries/${encodeURIComponent(id)}/restore`, {
      method: "POST",
      body: { version, reason },
    });
    showManageNotice(`${id} を v${version} に復元しました。`, "success");
    await loadManageEntries();
  } catch (error) {
    showManageNotice(error.message);
  }
}

async function loadAudit() {
  const rows = byId("auditRows");
  if (!rows) return;
  try {
    const data = await apiV1("/api/v1/audit?limit=50");
    if (!data.items.length) {
      rows.innerHTML = `<tr><td colspan="6" class="emptyCell">監査ログはまだありません。</td></tr>`;
      return;
    }
    rows.innerHTML = data.items
      .map(
        (entry) => `<tr>
        <td class="mono">${Number(entry.seq)}</td>
        <td>${escapeHtml(entry.at)}</td>
        <td>${escapeHtml(entry.actor)}</td>
        <td class="mono">${escapeHtml(entry.action)}</td>
        <td class="mono">${escapeHtml(entry.record_id || "-")}</td>
        <td>${escapeHtml(entry.reason || "-")}</td>
      </tr>`,
      )
      .join("");
  } catch (error) {
    rows.innerHTML = `<tr><td colspan="6" class="emptyCell">${escapeHtml(error.message)}</td></tr>`;
  }
}

function openEntryForm(item = null) {
  state.manage.editingId = item ? item.id : null;
  byId("entryFormTitle").textContent = item
    ? `エントリ編集 — ${item.id}`
    : "エントリ新規登録";
  const form = byId("entryForm");
  form.reset();
  byId("entryFormError").hidden = true;
  form.elements.id.disabled = Boolean(item); // id is immutable after creation
  if (item) {
    Array.from(form.elements).forEach((element) => {
      if (!element.name || element.name === "reason") return;
      const value = item[element.name];
      if (value === undefined || value === null) return;
      element.value = ENTRY_LIST_FIELDS.includes(element.name)
        ? (value || []).join(", ")
        : String(value);
    });
  }
  byId("entryFormPanel").hidden = false;
  byId("entryFormPanel").scrollIntoView({ behavior: "smooth" });
}

function closeEntryForm() {
  byId("entryFormPanel").hidden = true;
  state.manage.editingId = null;
}

function collectEntryForm() {
  const form = byId("entryForm");
  const payload = {};
  Array.from(form.elements).forEach((element) => {
    if (!element.name || element.disabled) return;
    const raw = element.value.trim();
    if (ENTRY_LIST_FIELDS.includes(element.name)) {
      payload[element.name] = raw
        ? raw
            .split(",")
            .map((part) => part.trim())
            .filter(Boolean)
        : [];
      return;
    }
    if (ENTRY_NUMBER_FIELDS.includes(element.name)) {
      if (raw !== "") payload[element.name] = Number(raw);
      return;
    }
    if (raw !== "") payload[element.name] = raw;
  });
  return payload;
}

async function submitEntryForm(event) {
  event.preventDefault();
  const errorBox = byId("entryFormError");
  errorBox.hidden = true;
  const payload = collectEntryForm();
  const editingId = state.manage.editingId;
  try {
    if (editingId) {
      // PATCH applies only fields present in the body (exclude_unset), so the
      // audit diff stays minimal: send only what actually changed.
      const original = state.manage.items.find(
        (entry) => entry.id === editingId,
      );
      const patch = { reason: payload.reason };
      Object.entries(payload).forEach(([field, value]) => {
        if (field === "reason" || field === "id") return;
        const before = original ? original[field] : undefined;
        const beforeNorm = ENTRY_LIST_FIELDS.includes(field)
          ? JSON.stringify(before || [])
          : String(before ?? "");
        const afterNorm = ENTRY_LIST_FIELDS.includes(field)
          ? JSON.stringify(value)
          : String(value);
        if (beforeNorm !== afterNorm) patch[field] = value;
      });
      // A nullable field that had a value but is now blank must be sent as an
      // explicit null: an omitted key means "unchanged" under exclude_unset.
      ENTRY_NULLABLE_FIELDS.forEach((field) => {
        if (field in payload) return; // still has a value (blank keys are omitted)
        const before = original ? original[field] : undefined;
        if (before !== undefined && before !== null && String(before) !== "") {
          patch[field] = null;
        }
      });
      if (Object.keys(patch).length === 1) {
        errorBox.textContent = "変更されたフィールドがありません。";
        errorBox.hidden = false;
        return;
      }
      await apiV1(`/api/v1/entries/${encodeURIComponent(editingId)}`, {
        method: "PATCH",
        body: patch,
      });
      showManageNotice(`${editingId} を更新しました。`, "success");
    } else {
      await apiV1("/api/v1/entries", { method: "POST", body: payload });
      showManageNotice(
        `${payload.id} を登録しました（draft状態から開始します）。`,
        "success",
      );
    }
    closeEntryForm();
    await loadManageEntries();
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  }
}

async function onManageRowAction(event) {
  const button = event.target.closest("button[data-act]");
  if (!button) return;
  const id = button.dataset.id;
  const item = state.manage.items.find((entry) => entry.id === id);
  if (!item) return;
  if (button.dataset.act === "edit") openEntryForm(item);
  else if (button.dataset.act === "transition")
    await doTransition(id, button.dataset.action);
  else if (button.dataset.act === "versions") await openVersions(id);
  else if (button.dataset.act === "delete") await doDelete(id);
}

function initManage() {
  const manageRows = byId("manageRows");
  if (!manageRows) return;
  manageRows.addEventListener("click", onManageRowAction);
  byId("versionRows").addEventListener("click", onVersionRowAction);
  byId("versionsClose").addEventListener("click", () =>
    byId("versionsDialog").close(),
  );
  byId("newEntryButton").addEventListener("click", () => openEntryForm());
  byId("entryFormClose").addEventListener("click", closeEntryForm);
  byId("entryFormCancel").addEventListener("click", closeEntryForm);
  byId("entryForm").addEventListener("submit", submitEntryForm);
  byId("manageReload").addEventListener("click", loadManageEntries);
  byId("auditReload").addEventListener("click", loadAudit);
  byId("manageStateFilter").addEventListener("change", renderManage);
  byId("manageSearch").addEventListener("input", () => {
    // Keyword filtering is server-side; debounce the reload lightly.
    clearTimeout(state.manage.searchTimer);
    state.manage.searchTimer = setTimeout(loadManageEntries, 300);
  });
}

const VIEWS = {
  dashboard: {
    kicker: "OVERVIEW",
    title: "採用ダッシュボード",
    sub: "スコア・接続ステータス・優先度の全体像",
  },
  catalog: {
    kicker: "LEDGER",
    title: "API・公開データ台帳",
    sub: "検索・絞り込み・スコア比較とAPI詳細を本番データで確認します。",
  },
  flow: {
    kicker: "HOW TO USE",
    title: "API活用フロー",
    sub: "選定から本番実装までの5ステップと、データ形式別の接続早見表。",
  },
  map: {
    kicker: "LIVE MAP",
    title: "地理空間ライブマップ",
    sub: "OpenStreetMap のタイルを実接続して表示します。",
  },
  exports: {
    kicker: "EXPORTS",
    title: "成果物エクスポート",
    sub: "台帳データから各種ファイルを生成・出力します。",
  },
  manage: {
    kicker: "MANAGE",
    title: "登録・承認管理",
    sub: "台帳エントリの登録・編集・レビュー・承認・監査ログを一元管理します。",
  },
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
  if (view === "manage" && !state.manage.loaded) {
    loadManageEntries();
    loadAudit();
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
    const next =
      document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("theme", next);
  });
}

async function boot() {
  [
    state.summary,
    state.metadata,
    state.catalog,
    state.verification,
    state.exports,
    state.liveMap,
  ] = await Promise.all([
    loadJson("/api/summary"),
    loadJson("/api/metadata"),
    loadJson("/api/catalog"),
    loadJson("/api/verification"),
    loadJson("/api/export"),
    loadJson("/api/live-map"),
    loadUser(),
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
  renderAuthArea();
  updateNavForRoles();
  wireLoginUI();
  initManage();
  [
    "searchInput",
    "categoryFilter",
    "statusFilter",
    "regionFilter",
    "trustRankFilter",
    "minPriorityFilter",
  ].forEach((id) => {
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
