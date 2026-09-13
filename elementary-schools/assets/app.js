(() => {
  "use strict";

  const DATA_VERSION = "2026-09-12-elementary-schools";
  const DATA_URLS = {
    schools: `data/schools.json?v=${DATA_VERSION}`,
    locations: `data/school-locations.json?v=${DATA_VERSION}`,
    manifest: `data/boundary-manifest.json?v=${DATA_VERSION}`,
    crosswalk: `data/boundary-crosswalk.json?v=${DATA_VERSION}`
  };

  const COLORS = {
    best: "#1a9850",
    good: "#91cf60",
    mid: "#fee08b",
    low: "#fc8d59",
    worst: "#d73027",
    none: "#727a80"
  };

  const state = {
    schools: [],
    schoolsById: new Map(),
    pointRecords: [],
    boundaryRecords: [],
    linkedSchoolIds: new Set(),
    contextualSchoolIds: new Set(),
    boundaryFailures: [],
    duplicateSchoolIds: 0,
    filters: { query: "", jurisdiction: "", schoolType: "", grade: "", minRating: 0 },
    map: null,
    pointGroup: null,
    boundaryGroup: null,
    boundaryRenderer: null,
    contextualBoundaryRenderer: null
  };

  const elements = {
    status: document.querySelector("#load-status"),
    dataAsOf: document.querySelector("#data-as-of"),
    kpiSchools: document.querySelector("#kpi-schools"),
    kpiBoundaries: document.querySelector("#kpi-boundaries"),
    kpiAverage: document.querySelector("#kpi-average"),
    kpiVisible: document.querySelector("#kpi-visible"),
    filters: document.querySelector("#filters"),
    search: document.querySelector("#search-input"),
    jurisdiction: document.querySelector("#jurisdiction-filter"),
    schoolType: document.querySelector("#type-filter"),
    grade: document.querySelector("#grades-filter"),
    rating: document.querySelector("#rating-filter"),
    toggleBoundaries: document.querySelector("#toggle-boundaries"),
    togglePoints: document.querySelector("#toggle-points"),
    list: document.querySelector("#school-list"),
    listCount: document.querySelector("#list-count"),
    empty: document.querySelector("#empty-state"),
    coverage: document.querySelector("#coverage-note")
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function normalizeForSearch(value) {
    return String(value ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("es")
      .trim();
  }

  function safeUrl(value) {
    try {
      const url = new URL(String(value));
      return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  }

  function formatDate(value) {
    if (!value) return "No indicada";
    const text = String(value);
    if (/^\d{4}$/.test(text)) return text;
    if (/^\d{4}-\d{2}$/.test(text)) {
      const month = new Date(`${text}-01T00:00:00`);
      return new Intl.DateTimeFormat("es", { year: "numeric", month: "long", timeZone: "UTC" }).format(month);
    }
    const normalized = /^\d{4}-\d{2}-\d{2}$/.test(text) ? `${text}T00:00:00` : text;
    const date = new Date(normalized);
    if (Number.isNaN(date.valueOf())) return text;
    return new Intl.DateTimeFormat("es", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" }).format(date);
  }

  function ratingCategory(rating) {
    if (rating === null || rating === undefined || rating === "") return "none";
    const value = Number(rating);
    if (!Number.isFinite(value)) return "none";
    if (value >= 9) return "best";
    if (value >= 7) return "good";
    if (value >= 5) return "mid";
    if (value >= 3) return "low";
    return "worst";
  }

  function ratingLabel(rating) {
    if (rating === null || rating === undefined || rating === "") return "Sin dato";
    return Number.isFinite(Number(rating)) ? `${Number(rating)}/10` : "Sin dato";
  }

  function ratingStatusLabel(status) {
    const labels = {
      verified: "Verificada",
      verified_user_supplied: "Verificada en el libro entregado por el usuario",
      not_available: "No disponible en la fuente",
      legacy_unverified: "Heredada; verificación pendiente"
    };
    return labels[status] || "Estado no indicado";
  }

  function boundaryStyle(school, boundaryType) {
    const category = school ? ratingCategory(school.rating) : "none";
    const nonAttendance = !isOfficialAttendance(boundaryType);
    const dashByCategory = {
      best: null,
      good: "12 4",
      mid: "8 5",
      low: "4 5",
      worst: "1 5",
      none: "5 5"
    };
    return {
      color: COLORS[category],
      fillColor: COLORS[category],
      fillOpacity: nonAttendance ? 0.22 : 0.16,
      opacity: nonAttendance ? 1 : 0.9,
      weight: nonAttendance ? 3 : (category === "best" ? 2.2 : 1.7),
      dashArray: nonAttendance ? "10 7" : dashByCategory[category],
      lineCap: "round",
      lineJoin: "round"
    };
  }

  function isOfficialAttendance(boundaryType) {
    if (!boundaryType) return true;
    const type = normalizeForSearch(boundaryType);
    return !["municip", "approx", "aproxim", "city limit", "limite de ciudad"].some((term) => type.includes(term));
  }

  function formatBoundaryType(boundaryType) {
    const labels = {
      attendance_boundary: "Zona oficial de asistencia",
      municipal_boundary: "Límite municipal",
      school_boundary: "Límite escolar",
      approximate_boundary: "Zona aproximada"
    };
    return labels[boundaryType] || boundaryType || "Límite escolar";
  }

  function formatBoundaryPeriod(entry) {
    if (!isOfficialAttendance(entry.boundary_type)) return "No aplica (límite municipal)";
    if (!entry.school_year || entry.school_year === "unknown") return "No indicada";
    return entry.school_year;
  }

  function setStatus(kind, message) {
    elements.status.className = `status status-${kind}`;
    elements.status.innerHTML = `<span class="status-dot" aria-hidden="true"></span>${escapeHtml(message)}`;
  }

  async function fetchJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    return response.json();
  }

  function initMap() {
    if (!window.L) throw new Error("Leaflet no pudo cargarse");
    state.map = L.map("map", {
      center: [38.91, -77.08],
      zoom: 9,
      minZoom: 7,
      preferCanvas: false,
      keyboard: true
    });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(state.map);
    state.map.createPane("attendance-boundaries");
    state.map.getPane("attendance-boundaries").style.zIndex = "410";
    state.map.createPane("municipal-boundaries");
    state.map.getPane("municipal-boundaries").style.zIndex = "420";
    state.boundaryRenderer = L.canvas({ pane: "attendance-boundaries", padding: 0.45, tolerance: 5 });
    state.contextualBoundaryRenderer = L.canvas({ pane: "municipal-boundaries", padding: 0.45, tolerance: 5 });
    state.boundaryGroup = L.layerGroup().addTo(state.map);
    state.pointGroup = L.layerGroup().addTo(state.map);
    L.control.scale({ imperial: true, metric: false, position: "bottomright" }).addTo(state.map);
  }

  function validateAndSetSchools(rawSchools) {
    if (!Array.isArray(rawSchools)) throw new Error("schools.json no contiene un arreglo");
    const seen = new Set();
    for (const item of rawSchools) {
      const id = String(item.id ?? "").trim();
      if (!id || seen.has(id)) {
        if (seen.has(id)) state.duplicateSchoolIds += 1;
        continue;
      }
      seen.add(id);
      const school = {
        ...item,
        id,
        name: String(item.name ?? "Escuela sin nombre"),
        address: String(item.address ?? "Dirección no indicada"),
        jurisdiction: String(item.jurisdiction ?? "Jurisdicción no indicada"),
        rating: item.rating === null || item.rating === "" ? null : Number(item.rating),
        lat: Number(item.lat),
        lng: Number(item.lng),
        school_type: String(item.school_type || "unknown"),
        grades_label: String(item.grades_label || item.grades || "No indicados"),
        grades_served: Array.isArray(item.grades_served) ? item.grades_served.map(String) : [],
        attendance_model: String(item.attendance_model || (item.school_type === "charter" ? "charter_no_zone" : "unknown")),
        location_status: String(item.location_status || "pending_official_source")
      };
      if (!Number.isFinite(school.rating) || school.rating < 1 || school.rating > 10) school.rating = null;
      state.schools.push(school);
      state.schoolsById.set(id, school);
    }
    state.schools.sort((a, b) => a.name.localeCompare(b.name, "es"));
  }

  function mergeOfficialLocations(rawLocations) {
    const rows = Array.isArray(rawLocations) ? rawLocations : rawLocations?.locations;
    if (!Array.isArray(rows)) throw new Error("school-locations.json no contiene locations");
    for (const location of rows) {
      const school = state.schoolsById.get(String(location.school_id || ""));
      if (!school) continue;
      school.location_status = String(location.location_status || "pending_official_source");
      school.location_source = String(location.source_name || "Fuente oficial no indicada");
      school.location_source_url = String(location.source_url || "");
      school.location_note = String(location.note || "");
      school.operational_status = String(location.operational_status || "unknown");
      if (!["verified_official", "verified_official_historical"].includes(school.location_status)) continue;
      school.address = String(location.address || school.address);
      school.lat = Number(location.lat);
      school.lng = Number(location.lng);
    }
  }

  function populateSelect(element, values) {
    for (const value of values) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      element.append(option);
    }
  }

  function typeLabel(value) {
    return { public: "Pública de distrito", charter: "Charter pública" }[value] || "Tipo no indicado";
  }

  function attendanceLabel(value) {
    return {
      zoned: "Puede tener zona de asistencia",
      charter_no_zone: "Sin zona de asistencia",
      choice_no_zone: "Programa de elección; sin zona propia",
      municipal_context: "Contexto municipal; no es zona",
      unknown: "Asignación no confirmada"
    }[value] || "Asignación no confirmada";
  }

  function operationalLabel(value) {
    return value === "closed_historical" ? "Cerrada; registro histórico" : "";
  }

  function hasMapLocation(school) {
    return Number.isFinite(school.lat) && Number.isFinite(school.lng)
      && Math.abs(school.lat) <= 90 && Math.abs(school.lng) <= 180;
  }

  function locationStatusLabel(school) {
    return hasMapLocation(school) ? "Ubicación oficial disponible" : "Ubicación oficial pendiente";
  }

  function populateFilters() {
    const jurisdictions = [...new Set(state.schools.map((school) => school.jurisdiction))].sort((a, b) => a.localeCompare(b, "es"));
    const schoolTypes = [...new Set(state.schools.map((school) => school.school_type))].sort();
    const grades = [...new Set(state.schools.flatMap((school) => school.grades_served))].sort((a, b) => Number(a) - Number(b));
    populateSelect(elements.jurisdiction, jurisdictions);
    for (const value of schoolTypes) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = typeLabel(value);
      elements.schoolType.append(option);
    }
    for (const value of grades) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "-1" ? "Pre-K" : value === "0" ? "K" : `${value}.º`;
      elements.grade.append(option);
    }
  }

  function schoolPopup(school) {
    const category = ratingCategory(school.rating);
    const sourceUrl = safeUrl(school.rating_source_url);
    const source = sourceUrl
      ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Fuente de la calificación</a>`
      : escapeHtml(school.rating_source || "Fuente no indicada");
    const effectiveDate = school.rating_as_of ? formatDate(school.rating_as_of) : "No publicada";
    const checkedDate = school.rating_checked_at ? formatDate(school.rating_checked_at) : "No verificada";
    const locationUrl = safeUrl(school.location_source_url);
    const locationSource = locationUrl
      ? `<a href="${escapeHtml(locationUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(school.location_source || "Fuente oficial de ubicación")}</a>`
      : escapeHtml(school.location_source || "Fuente de ubicación no indicada");
    return `
      <div class="popup-title">${escapeHtml(school.name)}</div>
      <span class="rating-badge rating-${category}">${escapeHtml(ratingLabel(school.rating))}</span>
      <p class="popup-meta">${escapeHtml(school.address)}</p>
      <p class="popup-meta"><strong>Jurisdicción:</strong> ${escapeHtml(school.jurisdiction)}</p>
      <p class="popup-meta"><strong>Tipo:</strong> ${escapeHtml(typeLabel(school.school_type))}</p>
      <p class="popup-meta"><strong>Grados:</strong> ${escapeHtml(school.grades_label)}</p>
      <p class="popup-meta"><strong>Asignación:</strong> ${escapeHtml(attendanceLabel(school.attendance_model))}</p>
      <p class="popup-meta"><strong>Ubicación:</strong> ${locationSource}</p>
      ${operationalLabel(school.operational_status) ? `<p class="popup-meta"><strong>Operación:</strong> ${escapeHtml(operationalLabel(school.operational_status))}</p>` : ""}
      ${school.location_note ? `<p class="popup-meta"><strong>Nota:</strong> ${escapeHtml(school.location_note)}</p>` : ""}
      <p class="popup-source">${source}<br><strong>Estado:</strong> ${escapeHtml(ratingStatusLabel(school.rating_status))}<br><strong>Vigencia de la fuente:</strong> ${escapeHtml(effectiveDate)}<br><strong>Entrega procesada:</strong> ${escapeHtml(checkedDate)}</p>`;
  }

  function addSchoolPoints() {
    for (const school of state.schools) {
      if (!hasMapLocation(school)) continue;
      const category = ratingCategory(school.rating);
      const marker = L.circleMarker([school.lat, school.lng], {
        radius: 6.5,
        color: "#ffffff",
        weight: 2,
        fillColor: COLORS[category],
        fillOpacity: 1,
        pane: "markerPane",
        keyboard: true,
        bubblingMouseEvents: false
      }).bindPopup(schoolPopup(school));
      marker.on("add", () => makeMarkerAccessible(marker, school));
      state.pointGroup.addLayer(marker);
      state.pointRecords.push({ school, layer: marker });
    }
  }

  function makeMarkerAccessible(marker, school) {
    const node = marker.getElement?.();
    if (!node || node.dataset.a11yReady) return;
    node.dataset.a11yReady = "true";
    node.setAttribute("tabindex", "0");
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", `${school.name}, calificación ${ratingLabel(school.rating)}`);
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        marker.openPopup();
      }
    });
  }

  function manifestEntries(raw) {
    if (Array.isArray(raw)) return raw;
    if (Array.isArray(raw?.entries)) return raw.entries;
    if (Array.isArray(raw?.boundaries)) return raw.boundaries;
    if (Array.isArray(raw?.layers)) return raw.layers;
    throw new Error("boundary-manifest.json no contiene entries");
  }

  function basename(path) {
    return String(path ?? "").replaceAll("\\", "/").split("/").pop();
  }

  function crosswalkKey(file, featureName) {
    return `${String(file ?? "")}\u0000${String(featureName ?? "")}`;
  }

  function normalizeCrosswalk(raw) {
    const output = new Map();
    const schoolIdsFrom = (value) => {
      const values = Array.isArray(value) ? value : [value];
      return [...new Set(values.filter((item) => item && item !== "unmatched").map(String))];
    };
    const add = (file, featureName, schoolIds) => {
      if (!file || featureName === undefined || featureName === null) return;
      const value = schoolIdsFrom(schoolIds);
      output.set(crosswalkKey(file, featureName), value);
      output.set(crosswalkKey(basename(file), featureName), value);
    };
    const addRows = (rows) => {
      for (const row of rows) {
        const file = row.file || row.path || row.boundary_file;
        if (Array.isArray(row.mappings)) {
          for (const mapping of row.mappings) add(file, mapping.feature_name ?? mapping.name ?? mapping.boundary_name, mapping.school_ids ?? mapping.school_id);
        } else if (row.mappings && typeof row.mappings === "object") {
          for (const [featureName, mapping] of Object.entries(row.mappings)) {
            add(file, featureName, typeof mapping === "object" ? mapping?.school_ids ?? mapping?.school_id : mapping);
          }
        } else {
          add(file, row.feature_name ?? row.name ?? row.boundary_name, row.school_ids ?? row.school_id);
        }
      }
    };
    const addObject = (object) => {
      for (const [file, mappings] of Object.entries(object || {})) {
        if (Array.isArray(mappings)) {
          for (const row of mappings) add(file, row.feature_name ?? row.name ?? row.boundary_name, row.school_ids ?? row.school_id);
        } else if (mappings && typeof mappings === "object") {
          for (const [featureName, mapping] of Object.entries(mappings)) {
            add(file, featureName, typeof mapping === "object" ? mapping?.school_ids ?? mapping?.school_id : mapping);
          }
        }
      }
    };
    if (Array.isArray(raw)) addRows(raw);
    else if (Array.isArray(raw?.entries)) addRows(raw.entries);
    else if (Array.isArray(raw?.mappings)) addRows(raw.mappings);
    else if (Array.isArray(raw?.files)) addRows(raw.files);
    else if (raw?.files && typeof raw.files === "object") addObject(raw.files);
    else if (raw?.mappings && typeof raw.mappings === "object") addObject(raw.mappings);
    else if (raw && typeof raw === "object") addObject(raw);
    return output;
  }

  function resolveBoundaryUrl(entry) {
    const value = String(entry.path || entry.file || "");
    if (!value) throw new Error("Entrada del manifiesto sin file/path");
    return value;
  }

  function lookupSchoolIds(crosswalk, entry, featureName) {
    const candidates = [entry.file, entry.path, basename(entry.file), basename(entry.path)].filter(Boolean);
    for (const file of candidates) {
      const key = crosswalkKey(file, featureName);
      if (crosswalk.has(key)) return crosswalk.get(key);
    }
    return [];
  }

  function boundaryPopup(entry, featureName, schools) {
    const sourceUrl = safeUrl(entry.source_url || entry.source);
    const source = sourceUrl
      ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Fuente oficial del límite</a>`
      : escapeHtml(entry.source_name || entry.source || "Fuente no indicada");
    const title = schools.length === 1
      ? schools[0].name
      : schools.length > 1 ? `${schools.length} escuelas vinculadas` : featureName || "Límite sin nombre";
    const schoolList = schools.length
      ? schools.map((school) => `${escapeHtml(school.name)} (${escapeHtml(ratingLabel(school.rating))})`).join("<br>")
      : "Sin escuela vinculada";
    const relation = schools.length
      ? `Vinculado por ID: ${schools.map((school) => school.id).join(", ")}`
      : "Sin escuela vinculada";
    return `
      <div class="popup-title">${escapeHtml(title)}</div>
      <p class="popup-meta"><strong>Nombre en la fuente:</strong> ${escapeHtml(featureName || "No indicado")}</p>
      <p class="popup-meta"><strong>Jurisdicción:</strong> ${escapeHtml(entry.jurisdiction || schools[0]?.jurisdiction || "No indicada")}</p>
      <p class="popup-meta"><strong>${schools.length === 1 ? "Escuela" : "Escuelas"}:</strong><br>${schoolList}</p>
      <p class="popup-meta"><strong>Tipo:</strong> ${escapeHtml(formatBoundaryType(entry.boundary_type))}</p>
      <p class="popup-meta"><strong>Vigencia:</strong> ${escapeHtml(formatBoundaryPeriod(entry))}</p>
      <p class="popup-source">${source}<br>${escapeHtml(relation)}</p>`;
  }

  async function loadBoundaryEntry(entry, crosswalk) {
    const url = resolveBoundaryUrl(entry);
    const geojson = await fetchJson(url);
    if (!Array.isArray(geojson?.features)) throw new Error(`${url}: GeoJSON sin features`);
    for (const feature of geojson.features) {
      const featureName = feature?.properties?.[entry.name_field];
      const schoolIds = lookupSchoolIds(crosswalk, entry, featureName);
      const schools = schoolIds.map((schoolId) => state.schoolsById.get(schoolId)).filter(Boolean);
      const styleSchool = schools.find((school) => school.rating !== null) || schools[0] || null;
      const attendanceBoundary = isOfficialAttendance(entry.boundary_type);
      const geoLayer = L.geoJSON(feature, {
        renderer: attendanceBoundary ? state.boundaryRenderer : state.contextualBoundaryRenderer,
        style: boundaryStyle(styleSchool, entry.boundary_type),
        onEachFeature: (_item, layer) => {
          layer.bindPopup(boundaryPopup(entry, featureName, schools));
          layer.on({
            mouseover: () => layer.setStyle({
              weight: 3.4,
              fillOpacity: attendanceBoundary ? 0.24 : 0.32
            }),
            mouseout: () => layer.setStyle(boundaryStyle(styleSchool, entry.boundary_type))
          });
          state.boundaryGroup.addLayer(layer);
          state.boundaryRecords.push({
            layer,
            schools,
            school: schools[0] || null,
            schoolIds: schools.map((school) => school.id),
            jurisdiction: String(entry.jurisdiction || schools[0]?.jurisdiction || ""),
            boundaryType: entry.boundary_type
          });
          for (const school of schools) {
            if (attendanceBoundary) state.linkedSchoolIds.add(school.id);
            else state.contextualSchoolIds.add(school.id);
          }
        }
      });
      if (!geoLayer.getLayers().length) throw new Error(`${url}: geometría no renderizable`);
    }
    return geojson.features.length;
  }

  function schoolMatches(school) {
    const query = normalizeForSearch(state.filters.query);
    const haystack = normalizeForSearch(`${school.name} ${school.city} ${school.address} ${school.jurisdiction} ${typeLabel(school.school_type)} ${school.grades_label}`);
    const rating = school.rating === null ? null : Number(school.rating);
    return (!query || haystack.includes(query))
      && (!state.filters.jurisdiction || school.jurisdiction === state.filters.jurisdiction)
      && (!state.filters.schoolType || school.school_type === state.filters.schoolType)
      && (!state.filters.grade || school.grades_served.includes(state.filters.grade))
      && (!state.filters.minRating || (rating !== null && Number.isFinite(rating) && rating >= state.filters.minRating));
  }

  function boundaryMatches(record) {
    if (record.schools?.length) return record.schools.some(schoolMatches);
    return !state.filters.query
      && !state.filters.schoolType
      && !state.filters.grade
      && !state.filters.minRating
      && (!state.filters.jurisdiction || record.jurisdiction === state.filters.jurisdiction);
  }

  function syncLayer(group, layer, visible) {
    if (visible && !group.hasLayer(layer)) group.addLayer(layer);
    if (!visible && group.hasLayer(layer)) group.removeLayer(layer);
  }

  function renderList(visibleSchools) {
    const fragment = document.createDocumentFragment();
    for (const school of visibleSchools) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const category = ratingCategory(school.rating);
      button.type = "button";
      button.className = "school-card";
      const mapped = hasMapLocation(school);
      button.setAttribute("aria-label", `${school.name}, ${school.jurisdiction}, calificación ${ratingLabel(school.rating)}. ${mapped ? "Mostrar en el mapa." : "Ubicación oficial pendiente."}`);
      if (!mapped) {
        button.disabled = true;
        button.classList.add("school-card-unmapped");
      }
      button.innerHTML = `
        <span class="school-name">${escapeHtml(school.name)}</span>
        <span class="school-meta">${escapeHtml(school.jurisdiction)} · ${escapeHtml(typeLabel(school.school_type))} · ${escapeHtml(school.grades_label)}</span>
        <span class="school-meta">${escapeHtml(attendanceLabel(school.attendance_model))}</span>
        <span class="school-meta">${escapeHtml(locationStatusLabel(school))}</span>
        ${operationalLabel(school.operational_status) ? `<span class="school-meta">${escapeHtml(operationalLabel(school.operational_status))}</span>` : ""}
        <span class="rating-badge rating-${category}">${escapeHtml(ratingLabel(school.rating))}</span>`;
      if (mapped) button.addEventListener("click", () => focusSchool(school));
      item.append(button);
      fragment.append(item);
    }
    elements.list.replaceChildren(fragment);
    elements.listCount.textContent = `${visibleSchools.length} ${visibleSchools.length === 1 ? "resultado" : "resultados"}`;
    elements.empty.hidden = visibleSchools.length !== 0;
  }

  function focusSchool(school) {
    const record = state.pointRecords.find((item) => item.school.id === school.id);
    if (!record) return;
    if (!elements.togglePoints.checked) {
      elements.togglePoints.checked = true;
      updateView();
    }
    state.map.setView([school.lat, school.lng], Math.max(state.map.getZoom(), 13));
    record.layer.openPopup();
  }

  function updateView() {
    const visibleSchools = state.schools.filter(schoolMatches);
    const showPoints = elements.togglePoints.checked;
    const showBoundaries = elements.toggleBoundaries.checked;
    for (const record of state.pointRecords) syncLayer(state.pointGroup, record.layer, showPoints && schoolMatches(record.school));
    for (const record of state.boundaryRecords) syncLayer(state.boundaryGroup, record.layer, showBoundaries && boundaryMatches(record));
    renderList(visibleSchools);
    elements.kpiVisible.textContent = visibleSchools.length.toLocaleString("es");
  }

  function renderSummary() {
    const verifiedSchools = state.schools.filter((school) => ["verified", "verified_user_supplied"].includes(school.rating_status));
    const ratings = verifiedSchools
      .map((school) => school.rating === null ? null : Number(school.rating))
      .filter((rating) => rating !== null && Number.isFinite(rating));
    const average = ratings.length ? ratings.reduce((sum, value) => sum + value, 0) / ratings.length : null;
    const dates = verifiedSchools.map((school) => school.rating_checked_at).filter(Boolean).sort();
    elements.kpiSchools.textContent = state.schools.length.toLocaleString("es");
    elements.kpiBoundaries.textContent = state.linkedSchoolIds.size.toLocaleString("es");
    elements.kpiAverage.textContent = average === null ? "—" : average.toLocaleString("es", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    elements.dataAsOf.textContent = dates.length ? formatDate(dates.at(-1)) : "Sin verificación actual";
    const jurisdictions = new Set(state.schools.map((school) => school.jurisdiction)).size;
    elements.coverage.textContent = `${state.schools.length} escuelas únicas en ${jurisdictions} jurisdicciones; ${state.pointRecords.length} con ubicación oficial, ${state.linkedSchoolIds.size} con zona oficial, ${state.contextualSchoolIds.size} con contexto municipal y ${verifiedSchools.length} con calificación verificada.`;
  }

  function bindControls() {
    elements.search.addEventListener("input", () => {
      state.filters.query = elements.search.value;
      updateView();
    });
    elements.jurisdiction.addEventListener("change", () => {
      state.filters.jurisdiction = elements.jurisdiction.value;
      updateView();
    });
    elements.schoolType.addEventListener("change", () => {
      state.filters.schoolType = elements.schoolType.value;
      updateView();
    });
    elements.grade.addEventListener("change", () => {
      state.filters.grade = elements.grade.value;
      updateView();
    });
    elements.rating.addEventListener("change", () => {
      state.filters.minRating = Number(elements.rating.value);
      updateView();
    });
    elements.toggleBoundaries.addEventListener("change", updateView);
    elements.togglePoints.addEventListener("change", updateView);
    elements.filters.addEventListener("reset", () => {
      window.setTimeout(() => {
        state.filters = { query: "", jurisdiction: "", schoolType: "", grade: "", minRating: 0 };
        updateView();
        elements.search.focus();
      }, 0);
    });
  }

  async function start() {
    try {
      initMap();
      bindControls();
      const [schoolsResult, locationsResult, manifestResult, crosswalkResult] = await Promise.allSettled([
        fetchJson(DATA_URLS.schools),
        fetchJson(DATA_URLS.locations),
        fetchJson(DATA_URLS.manifest),
        fetchJson(DATA_URLS.crosswalk)
      ]);

      if (schoolsResult.status === "rejected") throw new Error(`No se pudieron cargar las escuelas: ${schoolsResult.reason.message}`);
      validateAndSetSchools(schoolsResult.value);
      if (locationsResult.status === "rejected") throw new Error(`No se pudieron cargar las ubicaciones: ${locationsResult.reason.message}`);
      mergeOfficialLocations(locationsResult.value);
      populateFilters();
      addSchoolPoints();
      updateView();
      renderSummary();

      if (manifestResult.status === "rejected" || crosswalkResult.status === "rejected") {
        const missing = [manifestResult, crosswalkResult].filter((result) => result.status === "rejected").length;
        setStatus("warning", `Las escuelas están disponibles, pero faltan ${missing} archivos de control de límites. Se muestran solo los puntos.`);
        return;
      }

      const entries = manifestEntries(manifestResult.value);
      const crosswalk = normalizeCrosswalk(crosswalkResult.value);
      const results = await Promise.allSettled(entries.map((entry) => loadBoundaryEntry(entry, crosswalk)));
      results.forEach((result, index) => {
        if (result.status === "rejected") state.boundaryFailures.push(`${entries[index].jurisdiction || entries[index].file}: ${result.reason.message}`);
      });
      renderSummary();
      updateView();

      const loaded = results.length - state.boundaryFailures.length;
      const unverifiedRatings = state.schools.filter((school) => !["verified", "verified_user_supplied", "not_available"].includes(school.rating_status)).length;
      const warnings = state.boundaryFailures.length + (state.duplicateSchoolIds ? 1 : 0) + (unverifiedRatings ? 1 : 0);
      if (warnings) {
        const details = [];
        if (state.boundaryFailures.length) details.push(`${state.boundaryFailures.length} capas fallaron`);
        if (state.duplicateSchoolIds) details.push(`${state.duplicateSchoolIds} IDs duplicados se omitieron`);
        if (unverifiedRatings) details.push(`${unverifiedRatings} calificaciones heredadas aún no están verificadas`);
        setStatus("warning", `${state.schools.length} escuelas cargadas. ${loaded} de ${results.length} capas de límites disponibles; ${details.join("; ")}.`);
        if (state.boundaryFailures.length) console.warn("Problemas de carga de límites:", state.boundaryFailures);
      } else {
        setStatus("success", `${state.schools.length} escuelas y ${loaded} capas de límites cargadas correctamente.`);
      }
    } catch (error) {
      console.error(error);
      setStatus("error", `No se pudo iniciar el explorador: ${error.message}`);
      elements.dataAsOf.textContent = "No disponible";
    }
  }

  start();
})();
