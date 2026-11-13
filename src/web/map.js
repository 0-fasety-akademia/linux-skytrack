/* linux-skytrack — trips map (Leaflet). Talks to Python via webkit messageHandlers. */
(function () {
  "use strict";

  const UA_NOTE = "linux-skytrack";
  const post = (obj) => {
    try { window.webkit.messageHandlers.skytrack.postMessage(JSON.stringify(obj)); }
    catch (e) { console.log(UA_NOTE, "post failed", e); }
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtKm = (km) => Math.round(km).toLocaleString("pl-PL") + " km";

  const map = L.map("map", {
    worldCopyJump: true, zoomControl: true, minZoom: 2, maxZoom: 18,
    zoomSnap: 0.25, attributionControl: true,
  }).setView([50, 15], 4);
  map.attributionControl.setPrefix(false);

  const layers = {
    map: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }),
    sat: L.layerGroup([
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 18,
        attribution: "Tiles &copy; Esri — Esri, Maxar, Earthstar Geographics, GIS User Community",
      }),
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 18, opacity: 0.85,
      }),
    ]),
  };
  layers.outline = L.layerGroup();          // offline: country outlines only (always drawn below)
  let currentLayer = null;

  // ---- offline outline map (Natural Earth countries, bundled) ---------------------------------
  const outlinePane = map.createPane("outline");
  outlinePane.style.zIndex = 150;            // below the tile pane (200): tiles cover it when online
  outlinePane.style.pointerEvents = "none";
  const OUTLINE = {
    light:   { land: "#f6f5f4", border: "#b9b6b0", visited: "#f8c98f", home: "#dfe8f5" },
    dark:    { land: "#252a33", border: "#4a5262", visited: "#7a4a1e", home: "#24364f" },
    flighty: { land: "#151b2b", border: "#2c3754", visited: "#3a3418", home: "#1b2c52" },
    matrix:  { land: "#031a08", border: "#0d6b25", visited: "#1f5c00", home: "#063a14" },
  };
  let visitedCC = new Set(), homeCC = "", outlineGeo = null;
  const outlineKey = () => theme === "flighty" ? "flighty" : theme === "matrix" ? "matrix"
    : document.body.classList.contains("dark") ? "dark" : "light";
  function outlineStyle(f) {
    const pal = OUTLINE[outlineKey()], cc = f.properties.cc;
    return { color: pal.border, weight: 0.8, opacity: 1, fillOpacity: 1,
      fillColor: visitedCC.has(cc) ? pal.visited : (cc && cc === homeCC ? pal.home : pal.land) };
  }
  function initOutline() {
   try {
    if (window.WORLD_TOPO && window.topojson) {
      const gj = topojson.feature(window.WORLD_TOPO, window.WORLD_TOPO.objects.countries);
      outlineGeo = L.geoJSON(gj, { style: outlineStyle, interactive: false, pane: "outline",
        renderer: L.canvas({ pane: "outline", padding: 0.5 }) }).addTo(map);
    }
   } catch (e) { console.log(UA_NOTE, "outline failed", e); }
  }
  const restyleOutline = () => outlineGeo && outlineGeo.setStyle(outlineStyle);

  // tiles failing (no internet): say so — the outline below stays visible
  let tilesOk = false, tileErrors = 0;
  function setOffline(off) {
    document.body.classList.toggle("offline", off);
    const el = document.getElementById("offlineNote");
    if (el) el.hidden = !off || currentLayer === "outline";
  }
  [layers.map, ...layers.sat.getLayers()].forEach((tl) => {
    tl.on("tileload", () => { tilesOk = true; tileErrors = 0; setOffline(false); });
    tl.on("tileerror", () => { tileErrors++; if (!tilesOk && tileErrors >= 3) setOffline(true); });
  });
  window.addEventListener("offline", () => { tilesOk = false; setOffline(true); });
  window.addEventListener("online", () => setOffline(false));
  if (navigator.onLine === false) setTimeout(() => setOffline(true), 0);

  function setLayer(name, notify) {
    if (!layers[name]) name = "map";
    if (currentLayer) map.removeLayer(layers[currentLayer]);
    layers[name].addTo(map);
    currentLayer = name;
    if (name !== "outline") { tilesOk = false; tileErrors = 0; }
    setOffline(document.body.classList.contains("offline"));
    document.body.classList.toggle("sat", name === "sat");
    document.body.classList.toggle("layer-map", name === "map");
    document.body.classList.toggle("layer-outline", name === "outline");
    document.querySelectorAll("#layerSwitch button").forEach((b) =>
      b.classList.toggle("active", b.dataset.layer === name));
    if (notify) post({ type: "layer", value: name });
  }
  document.querySelectorAll("#layerSwitch button").forEach((b) =>
    b.addEventListener("click", () => setLayer(b.dataset.layer, true)));

  // ---- great-circle geometry -------------------------------------------------
  const rad = (d) => (d * Math.PI) / 180, deg = (r) => (r * 180) / Math.PI;

  function greatCircle(a, b, n) {
    const φ1 = rad(a.lat), λ1 = rad(a.lon), φ2 = rad(b.lat), λ2 = rad(b.lon);
    const d = 2 * Math.asin(Math.sqrt(Math.sin((φ2 - φ1) / 2) ** 2 +
      Math.cos(φ1) * Math.cos(φ2) * Math.sin((λ2 - λ1) / 2) ** 2));
    if (d < 1e-9) return [[a.lat, a.lon], [b.lat, b.lon]];
    const pts = [];
    let prevLon = null;
    for (let i = 0; i <= n; i++) {
      const f = i / n;
      const A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
      const x = A * Math.cos(φ1) * Math.cos(λ1) + B * Math.cos(φ2) * Math.cos(λ2);
      const y = A * Math.cos(φ1) * Math.sin(λ1) + B * Math.cos(φ2) * Math.sin(λ2);
      const z = A * Math.sin(φ1) + B * Math.sin(φ2);
      let lon = deg(Math.atan2(y, x));
      const lat = deg(Math.atan2(z, Math.sqrt(x * x + y * y)));
      if (prevLon !== null) {           // unwrap across the antimeridian
        while (lon - prevLon > 180) lon -= 360;
        while (lon - prevLon < -180) lon += 360;
      }
      prevLon = lon;
      pts.push([lat, lon]);
    }
    return pts;
  }

  // ---- markers -------------------------------------------------------------------
  function pinIcon(count, planned) {
    const badge = count > 1 ? `<span class="count">${count}</span>` : "";
    return L.divIcon({
      className: "pin" + (planned ? " pin-planned" : ""),
      html: `<svg width="26" height="36" viewBox="0 0 26 36" aria-hidden="true">
        <path d="M13 1C6.4 1 1 6.3 1 12.9 1 21.8 13 35 13 35s12-13.2 12-22.1C25 6.3 19.6 1 13 1z"
          fill="var(--pin)" stroke="var(--pin-stroke)" stroke-width="2"/>
        <circle cx="13" cy="13" r="4.6" fill="var(--pin-stroke)"/></svg>${badge}`,
      iconSize: [26, 36], iconAnchor: [13, 35], popupAnchor: [0, -32],
    });
  }

  const arcsLayer = L.layerGroup().addTo(map);
  const pointsLayer = L.layerGroup().addTo(map);
  let arcs = new Map();      // trip id -> polyline
  let trips = [];
  let focused = null;

  let theme = "system";
  const PALETTE = {
    system:  { arc: "#1c71d8", arcDark: "#99c1f1", focus: "#e66100", plan: "#c88800", planDark: "#f6d32d" },
    flighty: { arc: "#6f97ff", arcDark: "#6f97ff", focus: "#ffc83d", plan: "#ffc83d", planDark: "#ffc83d" },
    matrix:  { arc: "#00ff41", arcDark: "#00ff41", focus: "#d4ff5c", plan: "#c6ff00", planDark: "#c6ff00" },
    aurora:  { arc: "#7c5cff", arcDark: "#22d3ee", focus: "#ec4899", plan: "#8b5cf6", planDark: "#c4b5fd" },
  };

  function arcStyle(active, planned) {
    const pal = PALETTE[theme] || PALETTE.system;
    const dark = document.body.classList.contains("dark") || currentLayer === "sat";
    if (active) return { color: pal.focus, weight: 4, opacity: 1, dashArray: planned ? "8 7" : null };
    return {
      color: planned ? (dark ? pal.planDark : pal.plan) : (dark ? pal.arcDark : pal.arc),
      weight: theme === "flighty" ? 2.4 : 2,
      opacity: focused == null ? (theme === "matrix" ? 0.85 : 0.75) : 0.22,
      dashArray: planned ? "6 7" : null,
    };
  }

  let T = { visited: "Odwiedzone", departures: "Wyloty", planned: "zaplanowane", plan: "plan" };

  function setLang(texts) {
    T = Object.assign(T, texts || {});
    document.querySelectorAll("[data-t]").forEach((el) => {
      if (T[el.dataset.t]) el.textContent = T[el.dataset.t];
    });
    if (T.layerGroup) document.getElementById("layerSwitch").setAttribute("aria-label", T.layerGroup);
    document.documentElement.lang = T.lang || "pl";
  }

  function popupFor(ap, visits, departures, nPlanned = 0) {
    const items = visits.slice(0, 30).map((t) =>
      `<li><a data-trip="${t.id}">${esc(t.dateLabel)}</a> · ${esc(t.label)}` +
      (t.planned ? ` <i>(${esc(T.plan)})</i>` : "") + `</li>`).join("");
    const head = `<div class="pop-title">${esc(ap.iata)} · ${esc(ap.city || ap.name)}</div>
      <div class="pop-sub">${esc(ap.name)}${ap.country ? ", " + esc(ap.country) : ""}</div>`;
    const flownN = visits.length - nPlanned;
    let stats = visits.length ? `${esc(T.visited)}: <b>${flownN}×</b>` : `${esc(T.departures)}: <b>${departures}×</b>`;
    if (nPlanned) stats += ` · ${esc(T.planned)}: <b>${nPlanned}</b>`;
    return head + stats + (items ? `<ul class="pop-list">${items}</ul>` : "");
  }

  function setData(payload) {
    trips = payload.trips || [];
    visitedCC = new Set(payload.visited || []);
    homeCC = payload.home || "";
    restyleOutline();
    arcsLayer.clearLayers();
    pointsLayer.clearLayers();
    arcs = new Map();
    focused = null;

    const dests = new Map(), origins = new Map();
    for (const t of trips) {
      const line = L.polyline(greatCircle(t.from, t.to, 96),
        Object.assign({ className: "arc" + (t.planned ? " planned" : "") }, arcStyle(false, t.planned)));
      line._planned = !!t.planned;
      line.bindTooltip(`${esc(t.label)} · ${fmtKm(t.km)}<br>${esc(t.dateLabel)}` +
        (t.planned ? " · <b>zaplanowana</b>" : ""), { sticky: true });
      line.on("click", () => { focus(t.id, false); post({ type: "select", id: t.id }); });
      line.addTo(arcsLayer);
      arcs.set(t.id, line);
      if (!dests.has(t.to.iata)) dests.set(t.to.iata, { ap: t.to, visits: [], plans: [] });
      dests.get(t.to.iata)[t.planned ? "plans" : "visits"].push(t);
      origins.set(t.from.iata, { ap: t.from, n: (origins.get(t.from.iata)?.n || 0) + 1 });
    }

    for (const [code, o] of origins) {
      if (dests.has(code)) continue;
      const pal = PALETTE[theme] || PALETTE.system;
      L.circleMarker([o.ap.lat, o.ap.lon], {
        radius: 5, color: pal.arcDark, weight: 2, fillColor: (theme === "system" || theme === "aurora") ? "#fff" : "#000",
        fillOpacity: 1, className: "origin",
      }).bindPopup(popupFor(o.ap, [], o.n))
        .bindTooltip(code, { permanent: true, direction: "right", className: "code-label", offset: [6, 0] })
        .addTo(pointsLayer);
    }
    for (const [code, d] of dests) {
      const onlyPlanned = d.visits.length === 0;
      L.marker([d.ap.lat, d.ap.lon], {
        icon: pinIcon(d.visits.length, onlyPlanned), riseOnHover: true, title: code })
        .bindPopup(popupFor(d.ap, d.visits.concat(d.plans), 0, d.plans.length))
        .bindTooltip(code, { permanent: true, direction: "right", className: "code-label", offset: [10, -18] })
        .addTo(pointsLayer);
    }
    document.getElementById("legend").hidden = trips.length === 0;
    document.getElementById("legPlan").hidden = !trips.some((t) => t.planned);
    placePlane();
    fitAll();
  }

  let pendingFit = false;
  function fitAll() {
    const size = map.getSize();
    if (!size.x || !size.y) { pendingFit = true; return; }   // hidden (e.g. lock screen): fit later
    pendingFit = false;
    const all = [];
    arcs.forEach((l) => all.push(...l.getLatLngs()));
    if (all.length) map.fitBounds(L.latLngBounds(all), { padding: [40, 40], maxZoom: 7, animate: false });
  }

  function focus(id, fly = true) {
    focused = arcs.has(id) ? id : null;
    arcs.forEach((line, tid) => {
      line.setStyle(arcStyle(tid === focused, line._planned));
      if (tid === focused) line.bringToFront();
    });
    placePlane();
    const sz = map.getSize();
    if (focused != null && fly && (!sz.x || !sz.y)) { pendingFit = true; return; }
    if (focused != null && fly) {
      map.flyToBounds(arcs.get(focused).getBounds(), { padding: [60, 60], maxZoom: 7, duration: 0.8 });
    }
  }

  function clearFocus() { focus(null); fitAll(); }

  map.on("popupopen", (e) => {
    e.popup.getElement().querySelectorAll("a[data-trip]").forEach((a) =>
      a.addEventListener("click", () => {
        const id = Number(a.dataset.trip);
        focus(id); post({ type: "select", id });
      }));
  });

  function restyle() {
    arcs.forEach((line, tid) => line.setStyle(arcStyle(tid === focused, line._planned)));
    const pal = PALETTE[theme] || PALETTE.system;
    pointsLayer.eachLayer((l) => {
      if (l instanceof L.CircleMarker) l.setStyle({ color: pal.arcDark,
        fillColor: (theme === "system" || theme === "aurora") ? "#fff" : "#000" });
    });
    placePlane();
  }

  function setTheme(name, dark) {
    theme = PALETTE[name] ? name : "system";
    document.body.classList.toggle("dark", !!dark || (theme !== "system" && theme !== "aurora"));
    // Aurora korzysta z tej samej mapy co Systemowy (przygaszona w jasnym, ciemna w ciemnym) – inne są tylko trasy
    ["system", "flighty", "matrix"].forEach((n) => document.body.classList.toggle("theme-" + n,
      n === theme || (n === "system" && theme === "aurora")));
    restyle();
    restyleOutline();
    if (liveData) setLive(liveData, false);
  }

  // ---- plane on the focused arc -------------------------------------------------------
  let planeMarker = null;
  function placePlane() {
    if (planeMarker) { map.removeLayer(planeMarker); planeMarker = null; }
    if (focused == null || !arcs.has(focused)) return;
    const pts = arcs.get(focused).getLatLngs();
    if (pts.length < 3) return;
    const mid = Math.floor(pts.length / 2);
    const p1 = map.latLngToLayerPoint(pts[mid - 1]), p2 = map.latLngToLayerPoint(pts[mid + 1]);
    const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * 180 / Math.PI + 90;
    planeMarker = L.marker(pts[mid], {
      interactive: false, keyboard: false, zIndexOffset: 1000,
      icon: L.divIcon({
        className: "plane-marker", iconSize: [30, 30], iconAnchor: [15, 15],
        html: `<svg width="30" height="30" viewBox="0 0 16 16" style="transform:rotate(${angle}deg)">
          <path d="M8 .8C8.9.8 9.2 2 9.2 3v2.6L15 9.2v1.6L9.2 9v3.4l1.8 1.4V15L8 14.2 5 15v-1.2l1.8-1.4V9L1 10.8V9.2l5.8-3.6V3C6.8 2 7.1.8 8 .8z"/></svg>`,
      }),
    }).addTo(map);
  }
  map.on("zoomend", placePlane);

  // the WebView can be hidden while data arrives (login screen) — fix size and view when shown
  new ResizeObserver(() => {
    map.invalidateSize({ animate: false });
    if (pendingFit) { focused == null ? fitAll() : focus(focused); }
    if (liveMode) reportView();
  }).observe(document.getElementById("map"));

  function refit() {
    map.invalidateSize({ animate: false });
    if (focused == null) fitAll(); else focus(focused);
  }

  // ---- live tracking mode ------------------------------------------------------------------
  const liveLayer = L.layerGroup().addTo(map);
  let liveData = null;
  function setMode(mode) {
    liveMode = mode === "live";
    document.body.classList.toggle("live", mode === "live");
    setTimeout(reportView, 300);
    if (mode === "live") map.attributionControl.addAttribution(
      '<a href="https://opensky-network.org">The OpenSky Network</a>');
  }
  function apMarker(ap, cls) {
    return L.circleMarker([ap.lat, ap.lon], { radius: 5, weight: 2, className: cls,
      color: (PALETTE[theme] || PALETTE.system).arcDark, fillColor: (theme === "system" || theme === "aurora") ? "#fff" : "#000",
      fillOpacity: 1 }).bindTooltip(ap.iata, { permanent: true, direction: "right",
      className: "code-label", offset: [6, 0] });
  }
  function setLive(d, fit = true) {
    liveData = d;
    liveLayer.clearLayers();
    if (!d) return;
    const pal = PALETTE[theme] || PALETTE.system;
    const dark = document.body.classList.contains("dark") || currentLayer === "sat";
    const pts = [];
    if (d.origin && d.dest) {
      const route = greatCircle(d.origin, d.dest, 128);
      L.polyline(route, { color: dark ? pal.planDark : pal.plan, weight: 2, opacity: 0.8,
        dashArray: "6 7", interactive: false }).addTo(liveLayer);
      pts.push(...route);
    }
    [d.origin, d.dest].forEach((ap) => { if (ap) apMarker(ap, "origin").addTo(liveLayer); });
    if (d.trail && d.trail.length > 1) {
      L.polyline(d.trail, { color: pal.focus, weight: 3, opacity: 0.95, interactive: false }).addTo(liveLayer);
      pts.push(...d.trail);
    }
    if (d.pos) {
      const hdg = Number(d.pos.heading) || 0;
      L.marker([d.pos.lat, d.pos.lon], {
        interactive: false, keyboard: false, zIndexOffset: 1000,
        icon: L.divIcon({ className: "plane-marker live-plane" + (d.pos.stale ? " stale" : ""),
          iconSize: [36, 36], iconAnchor: [18, 18],
          html: `<svg width="36" height="36" viewBox="0 0 16 16" style="transform:rotate(${hdg}deg)">
            <path d="M8 .8C8.9.8 9.2 2 9.2 3v2.6L15 9.2v1.6L9.2 9v3.4l1.8 1.4V15L8 14.2 5 15v-1.2l1.8-1.4V9L1 10.8V9.2l5.8-3.6V3C6.8 2 7.1.8 8 .8z"/></svg>` }),
      }).bindTooltip(esc(d.label || ""), { permanent: !!d.label, direction: "top",
        className: "code-label live-label", offset: [0, -16] }).addTo(liveLayer);
      pts.push([d.pos.lat, d.pos.lon]);
    }
    if (!fit) return;
    const size = map.getSize();
    if (!size.x || !size.y) return;
    // never zoom: only move the view to the plane (first find, or "follow")
    if ((d.follow || d.center) && d.pos) map.panTo([d.pos.lat, d.pos.lon], { animate: !d.center });
  }

  // ---- traffic: every aircraft in view (community ADS-B) ------------------------------------
  const trafficLayer = L.layerGroup().addTo(map);
  const trafficRoute = L.layerGroup().addTo(map);
  const trafficMarkers = new Map();
  let selectedHex = null, liveMode = false;
  const planeSvg = (hdg, cls) => `<svg class="${cls}" width="24" height="24" viewBox="0 0 16 16" style="transform:rotate(${hdg}deg)">
      <path d="M8 .8C8.9.8 9.2 2 9.2 3v2.6L15 9.2v1.6L9.2 9v3.4l1.8 1.4V15L8 14.2 5 15v-1.2l1.8-1.4V9L1 10.8V9.2l5.8-3.6V3C6.8 2 7.1.8 8 .8z"/></svg>`;
  function trafficIcon(p) {
    const cls = (p.g ? "ground" : "") + (p.h === selectedHex ? " selected" : "");
    return L.divIcon({ className: "traffic-plane", iconSize: [24, 24], iconAnchor: [12, 12],
      html: planeSvg(Math.round(p.tr || 0), cls) });
  }
  function setTraffic(list) {
    const seen = new Set();
    for (const p of list || []) {
      seen.add(p.h);
      let m = trafficMarkers.get(p.h);
      if (!m) {
        m = L.marker([p.la, p.lo], { icon: trafficIcon(p), keyboard: false, title: p.c || p.h });
        m.on("click", () => {
          selectedHex = p.h;
          trafficMarkers.forEach((mm, h) => mm.setIcon(trafficIcon(mm._p)));
          post({ type: "plane", hex: p.h });
        });
        m.addTo(trafficLayer);
        trafficMarkers.set(p.h, m);
      } else {
        m.setLatLng([p.la, p.lo]);
        if (!m._p || Math.round(m._p.tr) !== Math.round(p.tr) || m._p.g !== p.g) m.setIcon(trafficIcon(p));
      }
      m._p = p;
    }
    trafficMarkers.forEach((m, h) => {
      if (!seen.has(h) && h !== selectedHex) { trafficLayer.removeLayer(m); trafficMarkers.delete(h); }
    });
  }
  function planeInfo(info) {
    const m = trafficMarkers.get(info.hex);
    if (m && selectedHex !== info.hex) {
      const prev = selectedHex;
      selectedHex = info.hex;
      [prev, info.hex].forEach((h) => { const mm = trafficMarkers.get(h); if (mm && mm._p) mm.setIcon(trafficIcon(mm._p)); });
    }
    trafficRoute.clearLayers();
    if (info.route && info.route.from && info.route.to) {
      const pal = PALETTE[theme] || PALETTE.system;
      L.polyline(greatCircle(info.route.from, info.route.to, 96), { color: pal.focus, weight: 2,
        dashArray: "6 7", opacity: 0.9, interactive: false }).addTo(trafficRoute);
      [info.route.from, info.route.to].forEach((ap) => apMarker(ap, "origin").addTo(trafficRoute));
    }
    if (!m) return;
    const lines = (info.lines || []).map((l) => `<div>${esc(l)}</div>`).join("");
    const action = info.tracking
      ? `<p class="pop-tracking">${esc(info.tracking)}</p>`
      : (info.track ? `<p style="margin:8px 0 0"><a class="pop-btn" href="#" data-track="${esc(info.hex)}" data-tracking="${esc(info.trackingLabel || "")}">${esc(info.track)}</a></p>` : "");
    const html = `<div class="pop-title">${esc(info.title || "")}</div>` +
      (info.subtitle ? `<div class="pop-sub">${esc(info.subtitle)}</div>` : "") + lines + action;
    if (m.getPopup()) m.setPopupContent(html); else m.bindPopup(html, { autoPan: true });
    m.openPopup();
  }
  // one delegated handler: the popup's content is replaced when the route arrives
  document.addEventListener("click", (ev) => {
    const a = ev.target.closest && ev.target.closest("a[data-track]");
    if (!a) return;
    ev.preventDefault();
    ev.stopPropagation();
    const p = document.createElement("p");
    p.className = "pop-tracking";
    p.textContent = a.dataset.tracking || "";
    a.parentNode.replaceWith(p);
    post({ type: "track", hex: a.dataset.track });
  }, true);
  map.on("click", () => { if (liveMode) post({ type: "map-click" }); });
  map.on("popupclose", (e) => {
    if (!liveMode) return;
    trafficRoute.clearLayers();
    if (selectedHex) {
      const h = selectedHex; selectedHex = null;
      const m = trafficMarkers.get(h);
      if (m && m._p) m.setIcon(trafficIcon(m._p));
      post({ type: "plane-closed", hex: h });
    }
  });
  function reportView() {
    if (!liveMode) return;
    const size = map.getSize();
    if (!size.x || !size.y) return;
    const c = map.getCenter(), ne = map.getBounds().getNorthEast();
    const nm = c.distanceTo(ne) / 1852;
    post({ type: "view", lat: c.lat, lon: c.lng, nm: Math.round(nm) });
  }
  map.on("moveend", reportView);

  function setView(lat, lon, zoom) {
    map.setView([lat, lon], zoom, { animate: false });
    setTimeout(reportView, 100);
  }

  window.SkyMap = { setView, setTraffic, planeInfo, reportView, setMode, setLive, setLang, setData, focus, clearFocus, setLayer: (n) => { setLayer(n, false); restyle(); },
    setTheme, fitAll, refit };

  initOutline();
  setLayer("map", false);
  post({ type: "ready" });
})();
