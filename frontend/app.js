/* PathSnap frontend - centralized API client + Leaflet map UI. */
(function () {
  "use strict";

  // ---- Centralized API client ------------------------------------------
  function resolveApiBase() {
    var params = new URLSearchParams(window.location.search);
    var fromQuery = params.get("api");
    if (fromQuery) {
      localStorage.setItem("pathsnap_api_base", fromQuery);
      return fromQuery.replace(/\/$/, "");
    }
    var stored = localStorage.getItem("pathsnap_api_base");
    if (stored) return stored.replace(/\/$/, "");
    if (window.PATHSNAP_API_BASE) return window.PATHSNAP_API_BASE.replace(/\/$/, "");
    return ""; // same origin
  }

  var API_BASE = resolveApiBase();

  function apiFetch(path, options) {
    return fetch(API_BASE + path, options).then(function (resp) {
      if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (body) {
          var err = new Error(body.detail || ("HTTP " + resp.status));
          err.status = resp.status;
          throw err;
        });
      }
      return resp.json();
    });
  }

  var api = {
    health: function () { return apiFetch("/api/health"); },
    trips: function () { return apiFetch("/api/trips"); },
    match: function (tripId) {
      return apiFetch("/api/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trip_id: tripId }),
      });
    },
    evaluate: function (tripId) {
      return apiFetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trip_id: tripId }),
      });
    },
  };

  // ---- UI helpers --------------------------------------------------------
  var els = {
    conn: document.getElementById("conn-status"),
    modeBadge: document.getElementById("mode-badge"),
    tripCount: document.getElementById("trip-count"),
    tripList: document.getElementById("trip-list"),
    runBtn: document.getElementById("run-btn"),
    evalBtn: document.getElementById("eval-btn"),
    evalBody: document.getElementById("eval-body"),
    mapEmpty: document.getElementById("map-empty"),
    legend: document.getElementById("legend"),
    toast: document.getElementById("toast"),
    spinner: document.getElementById("spinner"),
    spinnerText: document.getElementById("spinner-text"),
  };

  function showToast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.remove("hidden");
    setTimeout(function () { els.toast.classList.add("hidden"); }, 6000);
  }

  function setBusy(busy, text) {
    if (busy) {
      els.spinnerText.textContent = text || "Processing...";
      els.spinner.classList.remove("hidden");
    } else {
      els.spinner.classList.add("hidden");
    }
    els.runBtn.disabled = busy || !state.selectedTrip;
    els.evalBtn.disabled = busy || !state.lastMatch;
  }

  // ---- Map ---------------------------------------------------------------
  var map = L.map("map").setView([12.9716, 77.5946], 14);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  var layers = { gps: null, route: null, ref: null, gaps: null };
  function clearLayers() {
    Object.keys(layers).forEach(function (k) {
      if (layers[k]) { map.removeLayer(layers[k]); layers[k] = null; }
    });
  }

  // ---- State ---------------------------------------------------------------
  var state = { selectedTrip: null, lastMatch: null, mode: null };

  // ---- Rendering -----------------------------------------------------------
  function renderTrips(trips) {
    els.tripList.innerHTML = "";
    if (!trips.length) {
      els.tripList.innerHTML = '<div class="empty-state">No trips available from the backend.</div>';
      return;
    }
    trips.forEach(function (t) {
      var div = document.createElement("div");
      div.className = "trip-item";
      div.innerHTML = "<span>" + t.trip_id + "</span><span class='obs-count'>" +
        t.num_observations + " obs</span>";
      div.addEventListener("click", function () {
        state.selectedTrip = t.trip_id;
        state.lastMatch = null;
        els.evalBtn.disabled = true;
        Array.prototype.forEach.call(els.tripList.children, function (c) {
          c.classList.remove("selected");
        });
        div.classList.add("selected");
        els.runBtn.disabled = false;
      });
      els.tripList.appendChild(div);
    });
  }

  function renderMatch(body) {
    clearLayers();
    els.mapEmpty.classList.add("hidden");
    els.legend.classList.remove("hidden");

    layers.gps = L.layerGroup(
      body.observations.map(function (ob) {
        return L.circleMarker([ob.lat, ob.lon], {
          radius: 4, color: "#e5484d", fillOpacity: 0.85,
        }).bindTooltip("obs " + ob.index + " @ " + ob.timestamp);
      })
    ).addTo(map);

    layers.route = L.layerGroup(
      body.stretches.map(function (st) {
        // Each continuous stretch is its own polyline - never joined across gaps.
        return L.polyline(st.geometry, { color: "#2f81f7", weight: 6, opacity: 0.85 })
          .bindTooltip(
            "stretch " + st.stretch_id + " (obs " + st.from_obs + "-" + st.to_obs + ")" +
            (st.reconstructed_arc_ids.length
              ? " - includes " + st.reconstructed_arc_ids.length + " reconstructed arc(s)"
              : "")
          );
      })
    ).addTo(map);

    if (body.gaps.length) {
      layers.gaps = L.layerGroup(
        body.gaps.map(function (g) {
          var ob = body.observations[g.after_obs];
          if (!ob) return null;
          return L.circleMarker([ob.lat, ob.lon], {
            radius: 7, color: "#d29922", weight: 3, fill: false,
          }).bindTooltip("GPS gap: obs " + g.after_obs + " to " + g.before_obs);
        }).filter(Boolean)
      ).addTo(map);
    }

    var bounds = [];
    body.stretches.forEach(function (st) { st.geometry.forEach(function (p) { bounds.push(p); }); });
    body.observations.forEach(function (ob) { bounds.push([ob.lat, ob.lon]); });
    if (bounds.length) map.fitBounds(L.latLngBounds(bounds).pad(0.15));
  }

  function renderEvaluation(body) {
    var m = body.metrics;
    function row(label, value) {
      return "<tr><td>" + label + "</td><td>" + (value === null || value === undefined ? "n/a" : value) + "</td></tr>";
    }
    function pct(v) { return v === null || v === undefined ? null : (v * 100).toFixed(1) + "%"; }
    els.evalBody.innerHTML =
      "<table>" +
      row("Top-1 accuracy", pct(m.top1_accuracy)) +
      row("Candidate recall", pct(m.candidate_recall)) +
      row("Matched fraction", pct(m.matched_fraction)) +
      row("Predicted stretches", m.num_predicted_stretches) +
      row("Continuity ratio", m.continuity_ratio === null ? null : m.continuity_ratio.toFixed(3)) +
      row("Processing time", m.processing_time_ms.toFixed(1) + " ms") +
      "</table>" +
      '<p class="hint">' + body.note + "</p>";

    if (body.reference_geometry && body.reference_geometry.length) {
      if (layers.ref) map.removeLayer(layers.ref);
      layers.ref = L.polyline(body.reference_geometry, {
        color: "#3fb950", weight: 4, opacity: 0.9, dashArray: "8 6",
      }).bindTooltip("Reference route (revealed after prediction)").addTo(map);
    }
  }

  // ---- Boot ----------------------------------------------------------------
  function checkHealth() {
    api.health().then(function (h) {
      els.conn.textContent = "Backend: connected (" + (API_BASE || "same origin") + ")";
      els.conn.className = "conn conn-ok";
      state.mode = h.mode;
      if (h.mode === "mock") {
        els.modeBadge.textContent = "MOCK DATA - pipeline placeholders";
        els.modeBadge.classList.remove("hidden");
      } else {
        els.modeBadge.classList.add("hidden");
      }
    }).catch(function () {
      els.conn.textContent = "Backend: unreachable";
      els.conn.className = "conn conn-bad";
    });
  }

  function loadTrips() {
    api.trips().then(function (body) {
      els.tripCount.textContent = body.count;
      renderTrips(body.trips);
    }).catch(function (err) {
      els.tripList.innerHTML = '<div class="empty-state">Could not load trips.</div>';
      showToast("Failed to load trips: " + err.message);
    });
  }

  els.runBtn.addEventListener("click", function () {
    if (!state.selectedTrip || els.runBtn.disabled) return;
    setBusy(true, "Running map matching for " + state.selectedTrip + "...");
    api.match(state.selectedTrip).then(function (body) {
      state.lastMatch = body;
      renderMatch(body);
      els.evalBtn.disabled = false;
    }).catch(function (err) {
      showToast("Matching failed: " + err.message);
    }).finally(function () { setBusy(false); });
  });

  els.evalBtn.addEventListener("click", function () {
    if (!state.lastMatch || els.evalBtn.disabled) return;
    setBusy(true, "Evaluating on the server...");
    api.evaluate(state.lastMatch.trip_id).then(function (body) {
      renderEvaluation(body);
    }).catch(function (err) {
      showToast("Evaluation failed: " + err.message);
    }).finally(function () { setBusy(false); });
  });

  checkHealth();
  loadTrips();
})();
