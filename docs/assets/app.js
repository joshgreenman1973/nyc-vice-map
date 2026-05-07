/* NYC vice map */
(function () {
  'use strict';

  const CAT_COLOR = {
    liquor:   '#b8312f',
    cannabis: '#2e7d4f',
    tobacco:  '#c97a1f',
    beer:     '#b8860b',
  };
  const CAT_LABEL = {
    liquor:   'Liquor store',
    cannabis: 'Cannabis dispensary',
    tobacco:  'Tobacco / vape',
    beer:     'Beer (grocery / deli)',
  };
  const CATS = ['liquor', 'cannabis', 'tobacco', 'beer'];

  const map = L.map('map', { preferCanvas: true }).setView([40.72, -73.96], 11);

  // CARTO Positron — clean basemap, free tier OK
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map);

  // Heat layers per category — built lazily, color-tinted via gradient
  const heatLayers = {};
  const heatGradients = {
    liquor:   { 0.2: '#fff5f4', 0.5: '#e88f8e', 0.8: '#b8312f', 1.0: '#7a1a18' },
    cannabis: { 0.2: '#eef7f0', 0.5: '#7fc09a', 0.8: '#2e7d4f', 1.0: '#1a4a2e' },
    tobacco:  { 0.2: '#fdf3e7', 0.5: '#e3b378', 0.8: '#c97a1f', 1.0: '#7a4810' },
    beer:     { 0.2: '#fbf3dc', 0.5: '#dcbf6a', 0.8: '#b8860b', 1.0: '#705208' },
  };

  // One cluster group per category so toggles stay snappy
  const clusters = {};
  CATS.forEach((cat) => {
    clusters[cat] = L.markerClusterGroup({
      chunkedLoading: true,
      showCoverageOnHover: false,
      maxClusterRadius: 50,
      iconCreateFunction: (cluster) => {
        const c = cluster.getChildCount();
        return L.divIcon({
          html: `<div style="background:${CAT_COLOR[cat]};opacity:0.85;color:#fff;border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;font:600 12px var(--sans, sans-serif);border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.3);">${c}</div>`,
          className: '',
          iconSize: [36, 36],
        });
      },
    });
    map.addLayer(clusters[cat]);
  });

  let allFeatures = [];
  const state = {
    view: 'markers',  // 'markers' | 'heat'
    cats: { liquor: true, cannabis: true, tobacco: true, beer: false },
    borough: '',
    query: '',
  };
  let table;

  function makeMarker(feature) {
    const p = feature.properties;
    const [lon, lat] = feature.geometry.coordinates;
    const m = L.circleMarker([lat, lon], {
      radius: 4,
      color: CAT_COLOR[p.category],
      fillColor: CAT_COLOR[p.category],
      fillOpacity: 0.85,
      weight: 1,
    });
    const html = `
      <div class="pop-name">${escapeHtml(p.name || '(unnamed)')}</div>
      <div class="pop-cat ${p.category}">${CAT_LABEL[p.category]}</div>
      <div class="pop-addr">${escapeHtml(p.address || '')}</div>
      <div class="pop-meta">
        License ${escapeHtml(p.license_id || '—')} · ${escapeHtml(p.subcategory || '')}<br>
        Source: <a href="${p.source_url}" target="_blank" rel="noopener">${escapeHtml(p.source)}</a>
      </div>
    `;
    m.bindPopup(html);
    m._cat = p.category;
    m._props = p;
    return m;
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function passesFilters(p) {
    if (!state.cats[p.category]) return false;
    if (state.borough && p.borough !== state.borough) return false;
    if (state.query) {
      const q = state.query.toLowerCase();
      const blob = `${p.name || ''} ${p.address || ''} ${p.zip || ''} ${p.subcategory || ''}`.toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  }

  function clearHeatLayers() {
    Object.values(heatLayers).forEach((layer) => {
      if (layer && map.hasLayer(layer)) map.removeLayer(layer);
    });
  }

  function applyFilters() {
    const buckets = { liquor: [], cannabis: [], tobacco: [], beer: [] };
    const heatPoints = { liquor: [], cannabis: [], tobacco: [], beer: [] };
    let visible = 0;
    for (const f of allFeatures) {
      if (!passesFilters(f.properties)) continue;
      buckets[f.properties.category].push(f._marker);
      const [lon, lat] = f.geometry.coordinates;
      heatPoints[f.properties.category].push([lat, lon, 1]);
      visible++;
    }

    if (state.view === 'markers') {
      clearHeatLayers();
      Object.values(clusters).forEach((g) => {
        g.clearLayers();
        if (!map.hasLayer(g)) map.addLayer(g);
      });
      Object.entries(buckets).forEach(([cat, arr]) => {
        if (arr.length) clusters[cat].addLayers(arr);
      });
    } else {
      // heat view
      Object.values(clusters).forEach((g) => {
        g.clearLayers();
        if (map.hasLayer(g)) map.removeLayer(g);
      });
      clearHeatLayers();
      Object.entries(heatPoints).forEach(([cat, pts]) => {
        if (!pts.length) return;
        heatLayers[cat] = L.heatLayer(pts, {
          radius: 22,
          blur: 18,
          maxZoom: 16,
          minOpacity: 0.35,
          gradient: heatGradients[cat],
        });
        heatLayers[cat].addTo(map);
      });
    }

    document.getElementById('visible-count').textContent =
      `${visible.toLocaleString()} visible`;
    if (table) {
      table.setFilter((row) => passesFilters(row));
    }
  }

  function bindControls() {
    document.querySelectorAll('.view-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.view-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        state.view = btn.dataset.view;
        applyFilters();
      });
    });
    document.querySelectorAll('.cat-toggle input').forEach((el) => {
      el.addEventListener('change', () => {
        state.cats[el.dataset.cat] = el.checked;
        applyFilters();
      });
    });
    document.getElementById('borough-filter').addEventListener('change', (e) => {
      state.borough = e.target.value;
      applyFilters();
    });
    const searchEl = document.getElementById('search');
    const sugEl = document.getElementById('suggestions');
    let activeIdx = -1;
    let currentSuggestions = [];
    let t;

    function rankMatches(q) {
      const ql = q.toLowerCase();
      const out = [];
      for (const f of allFeatures) {
        const p = f.properties;
        if (!state.cats[p.category]) continue;  // respect active layers
        if (state.borough && p.borough !== state.borough) continue;
        const name = (p.name || '').toLowerCase();
        const addr = (p.address || '').toLowerCase();
        const zip = p.zip || '';
        let score = -1;
        if (name.startsWith(ql)) score = 100;
        else if (addr.startsWith(ql)) score = 90;
        else if (name.includes(ql)) score = 60;
        else if (addr.includes(ql)) score = 50;
        else if (zip === ql) score = 40;
        else if (zip.startsWith(ql)) score = 30;
        if (score >= 0) out.push({ f, score });
        if (out.length > 400) break;  // cap inner loop
      }
      out.sort((a, b) => b.score - a.score);
      return out.slice(0, 8).map((x) => x.f);
    }

    function highlight(text, q) {
      if (!q) return escapeHtml(text);
      const lower = text.toLowerCase();
      const i = lower.indexOf(q.toLowerCase());
      if (i < 0) return escapeHtml(text);
      return (
        escapeHtml(text.slice(0, i)) +
        '<mark>' + escapeHtml(text.slice(i, i + q.length)) + '</mark>' +
        escapeHtml(text.slice(i + q.length))
      );
    }

    function renderSuggestions(q) {
      if (q.length < 2) {
        sugEl.hidden = true;
        sugEl.innerHTML = '';
        currentSuggestions = [];
        return;
      }
      const matches = rankMatches(q);
      currentSuggestions = matches;
      activeIdx = -1;
      if (!matches.length) {
        sugEl.hidden = true;
        sugEl.innerHTML = '';
        return;
      }
      sugEl.innerHTML = matches.map((f, i) => {
        const p = f.properties;
        return `
          <div class="suggestion" data-idx="${i}">
            <span class="s-dot" style="background:${CAT_COLOR[p.category]}"></span>
            <span class="s-text">
              <div class="s-name">${highlight(p.name || '(unnamed)', q)}</div>
              <div class="s-addr">${highlight(p.address || '', q)}</div>
            </span>
          </div>
        `;
      }).join('');
      sugEl.hidden = false;
    }

    function pickSuggestion(idx) {
      const f = currentSuggestions[idx];
      if (!f) return;
      const [lon, lat] = f.geometry.coordinates;
      // Make sure the marker is on the map even in heat view
      if (state.view === 'heat') {
        document.querySelector('.view-btn[data-view="markers"]').click();
      }
      map.setView([lat, lon], 18);
      if (f._marker) {
        // Cluster may need a moment to expand; open popup after a tick
        setTimeout(() => f._marker.openPopup(), 250);
      }
      sugEl.hidden = true;
      searchEl.value = f.properties.name || f.properties.address || '';
      state.query = searchEl.value;
      applyFilters();
    }

    searchEl.addEventListener('input', (e) => {
      clearTimeout(t);
      const v = e.target.value.trim();
      renderSuggestions(v);
      t = setTimeout(() => {
        state.query = v;
        applyFilters();
      }, 150);
    });

    searchEl.addEventListener('keydown', (e) => {
      if (sugEl.hidden) return;
      const items = sugEl.querySelectorAll('.suggestion');
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIdx = Math.min(activeIdx + 1, items.length - 1);
        items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIdx = Math.max(activeIdx - 1, 0);
        items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
      } else if (e.key === 'Enter') {
        if (activeIdx >= 0) {
          e.preventDefault();
          pickSuggestion(activeIdx);
        } else if (currentSuggestions.length) {
          e.preventDefault();
          pickSuggestion(0);
        }
      } else if (e.key === 'Escape') {
        sugEl.hidden = true;
      }
    });

    sugEl.addEventListener('mousedown', (e) => {
      // mousedown beats blur — so the click registers
      const item = e.target.closest('.suggestion');
      if (!item) return;
      e.preventDefault();
      pickSuggestion(parseInt(item.dataset.idx, 10));
    });

    searchEl.addEventListener('blur', () => {
      setTimeout(() => { sugEl.hidden = true; }, 150);
    });
    searchEl.addEventListener('focus', () => {
      if (searchEl.value.trim().length >= 2) renderSuggestions(searchEl.value.trim());
    });
    document.getElementById('reset-btn').addEventListener('click', () => {
      state.view = 'markers';
      state.cats = { liquor: true, cannabis: true, tobacco: true, beer: false };
      state.borough = '';
      state.query = '';
      document.querySelectorAll('.view-btn').forEach((b) => b.classList.toggle('active', b.dataset.view === 'markers'));
      document.querySelectorAll('.cat-toggle input').forEach((el) => (el.checked = state.cats[el.dataset.cat]));
      document.getElementById('borough-filter').value = '';
      document.getElementById('search').value = '';
      applyFilters();
      map.setView([40.72, -73.96], 11);
    });
  }

  function buildTable() {
    const rows = allFeatures.map((f) => f.properties);
    table = new Tabulator('#table', {
      data: rows,
      layout: 'fitColumns',
      pagination: true,
      paginationSize: 25,
      paginationSizeSelector: [25, 50, 100, 250],
      placeholder: 'No locations match your filters.',
      initialSort: [{ column: 'name', dir: 'asc' }],
      columns: [
        {
          title: 'Category', field: 'category', width: 130, headerFilter: 'list',
          headerFilterParams: { values: { liquor: 'Liquor', cannabis: 'Cannabis', tobacco: 'Tobacco', beer: 'Beer' }, clearable: true },
          formatter: (cell) => `<span class="cat-pill ${cell.getValue()}">${cell.getValue()}</span>`,
        },
        { title: 'Name', field: 'name', headerFilter: 'input', minWidth: 180 },
        { title: 'Address', field: 'address', headerFilter: 'input', minWidth: 220 },
        { title: 'Borough', field: 'borough', width: 110, headerFilter: 'list',
          headerFilterParams: { values: ['', 'Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'], clearable: true } },
        { title: 'Type', field: 'subcategory', width: 200, headerFilter: 'input' },
        { title: 'License #', field: 'license_id', width: 140 },
      ],
      rowClick: (e, row) => {
        const p = row.getData();
        const f = allFeatures.find((x) => x.properties.id === p.id);
        if (f && f._marker) {
          map.setView(f._marker.getLatLng(), 17);
          f._marker.openPopup();
          window.scrollTo({ top: document.getElementById('map').offsetTop - 80, behavior: 'smooth' });
        }
      },
    });
  }

  function setCounts() {
    const counts = { liquor: 0, cannabis: 0, tobacco: 0 };
    allFeatures.forEach((f) => { counts[f.properties.category] = (counts[f.properties.category] || 0) + 1; });
    Object.entries(counts).forEach(([k, v]) => {
      const el = document.querySelector(`[data-count="${k}"]`);
      if (el) el.textContent = `(${v.toLocaleString()})`;
    });
  }

  Promise.all([
    fetch('data/locations.geojson').then((r) => r.json()),
    fetch('data/methodology.json').then((r) => r.json()).catch(() => null),
  ]).then(([geo, meta]) => {
    allFeatures = geo.features;
    allFeatures.forEach((f) => { f._marker = makeMarker(f); });
    setCounts();
    buildTable();
    bindControls();
    applyFilters();

    if (meta) {
      const d = new Date(meta.generated_at);
      const total = (meta.counts && meta.counts.total) || allFeatures.length;
      document.getElementById('meta-line').textContent =
        `Last refreshed ${d.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}. ${total.toLocaleString()} licensed locations; ${meta.mapped_features.toLocaleString()} mapped.`;
    }
  }).catch((err) => {
    console.error(err);
    document.getElementById('meta-line').textContent = 'Could not load data.';
  });
})();
