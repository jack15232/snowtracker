/* Alagna Snow: renders docs/data/summary.json. No dependencies. */
(() => {
  const TZ = "Europe/Rome";
  const REPO = (document.querySelector('meta[name="snowcast-repo"]') || {}).content || "";
  const STALE_MIN = 90;
  const $ = (id) => document.getElementById(id);
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  let data = null;
  let band = store.get("snowcast:band") || null;
  let openDay = null;

  // ---------- formatting ----------
  const fmt = (o) => new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...o });
  const fTime = fmt({ hour: "2-digit", minute: "2-digit" });
  const fDayHour = fmt({ weekday: "short", hour: "2-digit", minute: "2-digit" });
  const fDow = fmt({ weekday: "short" });
  const fHour = fmt({ hour: "numeric" });
  const cm = (v) => (v == null ? "–" : v < 0.5 ? "0" : v < 1 ? "<1" : String(Math.round(v)));
  const pct = (p) => (p == null ? "–" : Math.round(p * 100) + "%");
  const ago = (t) => {
    const m = Math.round((Date.now() / 1000 - t) / 60);
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    const h = Math.floor(m / 60);
    return h < 48 ? `${h}h ${m % 60}m ago` : Math.round(h / 24) + " days ago";
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------- data ----------
  async function fetchJSON(url, opts) {
    const r = await fetch(url, { cache: "no-store", ...opts });
    if (!r.ok) throw new Error(r.status + " " + url);
    return r.json();
  }
  async function load() {
    const btn = $("refresh");
    btn.classList.add("spin");
    let fresh = null, err = null;
    const sources = [];
    if (REPO && !REPO.startsWith("__")) {
      sources.push(() => fetchJSON(`https://api.github.com/repos/${REPO}/contents/docs/data/summary.json?ref=main`,
        { headers: { Accept: "application/vnd.github.raw" } }));
    }
    sources.push(() => fetchJSON(`data/summary.json?t=${Date.now()}`));
    for (const src of sources) {
      try { fresh = await src(); break; } catch (e) { err = e; }
    }
    btn.classList.remove("spin");
    if (fresh) {
      data = fresh;
      store.set("snowcast:last", fresh);
      banner(null);
    } else {
      data = data || store.get("snowcast:last");
      banner(data ? `Couldn't reach GitHub, showing saved data. (${esc(err && err.message)})`
                  : "Couldn't load the forecast and nothing is saved yet. Check your connection.", "bad");
    }
    if (data) render();
  }
  function banner(html, kind = "warn") {
    const b = $("banner");
    b.className = "banner" + (html ? " show " + kind : "");
    b.innerHTML = html || "";
  }

  // ---------- render ----------
  function render() {
    const s = data;
    if (!band || !s.bands[band]) band = s.headline_band;
    const stale = (Date.now() / 1000 - s.generated_at) / 60 > STALE_MIN;
    $("updated").textContent = `Monterosa Ski · updated ${ago(s.generated_at)}`;
    if (stale && !$("banner").classList.contains("bad")) {
      banner(`Your Mac hasn't published since ${fDayHour.format(s.generated_at * 1000)} (Alagna time). It may be asleep or offline, so these numbers are getting old.`, "warn");
    }
    $("now").innerHTML = nowCard(s.obs) + camsCard(s.webcams);
    $("bands").innerHTML = Object.entries(s.bands).map(([id, b]) =>
      `<button data-band="${id}" aria-pressed="${id === band}">${b.elev}m</button>`).join("");
    const B = s.bands[band];
    const hasFc = B.days.some((d) => d.snow);
    $("main").innerHTML = hasFc ? [
      heroCard(B), daysCard(B), `<div class="card" id="timingCard"></div>`, `<div class="card" id="flCard"></div>`,
      stationsCard(s.obs), avalancheCard(s.avalanche), modelsCard(s, B),
    ].join("") : `<div class="card empty">No forecast data yet. The first run on your Mac hasn't finished.</div>` +
      stationsCard(s.obs) + avalancheCard(s.avalanche) + modelsCard(s, B);
    if (hasFc) { timingChart(B); flChart(s, B); }
    $("footer").innerHTML = footer(s);
  }


  function nowCard(obs) {
    const st = ((obs && obs.stations) || []).filter((x) => x.ok);
    if (!st.length) return "";
    const short = { "Bocchetta delle Pisse": "Pisse", "Alagna Miniere": "Alagna", "Passo del Moro": "Moro" };
    const sign = (v) => (v == null ? "–" : (v > 0 ? "+" : "") + Math.round(v));
    const order = ["Bocchetta delle Pisse", "Alagna Miniere", "Passo del Moro"];
    st.sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name));
    const latest = Math.max(...st.map((x) => x.hs_time));
    return `<div class="card"><h2>Snow on the ground now <span class="note">measured ${ago(latest)}</span></h2>
      <div class="now">${st.map((x) => `<div class="tile">
        <div class="t">${esc(short[x.name] || x.name)} ${x.elev}m</div>
        <div class="n">${Math.round(x.hs_cm)}<small> cm</small></div>
        <div class="c">${sign(x.d24)} cm in 24h</div></div>`).join("")}</div>
      <div class="axis-note">Total depth from ARPA's automatic snow stations. Passo del Moro is across the ridge above Macugnaga.</div></div>`;
  }

  function camsCard(w) {
    if (!w || !w.cams) return "";
    const live = w.cams.filter((c) => c.ok);
    const bust = Math.floor(Date.now() / 300000); // new image at most every 5 min
    const cams = (live.length ? live : w.cams).map((c) => {
      const fresh = c.updated ? `photo ${ago(c.updated)}` : "";
      return `<div class="cam"><a href="${esc(c.page)}" target="_blank" rel="noopener">
        <div class="img"><img src="${esc(c.url)}?t=${bust}" alt="${esc(c.name)} webcam" loading="lazy"
          onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'off',textContent:'Camera image unavailable. Tap to open the resort page'}))"></div>
        <div class="cap"><b>${esc(c.name)} · ${c.elev}m</b><span>${fresh}</span></div></a></div>`;
    }).join("");
    return `<div class="card"><h2>Webcams <span class="note">swipe · tap to open</span></h2>
      <div class="cams">${cams}</div>
      <div class="axis-note"><a href="${esc(w.index)}" target="_blank" rel="noopener" style="color:var(--snow)">All Monterosa Ski webcams</a></div></div>`;
  }

  function heroCard(B) {
    const h = B.next72h;
    if (!h) return `<div class="card"><h2>Next 72 hours · ${esc(B.label)}</h2><div class="muted">Not enough model coverage yet.</div></div>`;
    const agr = { good: ["good", "Models agree"], mixed: ["warn", "Models partly agree"], poor: ["serious", "Models disagree"] }[h.agreement];
    const fl = (data.freezing_level || [])[0];
    return `<div class="card">
      <h2>Next 72 hours · ${esc(B.label)}</h2>
      <div class="hero">
        <div class="num">${cm(h.p50)}<small>cm</small></div>
        <div class="meta">likely range ${cm(h.p10)}–${cm(h.p90)} cm<br>${pct(h.p_gt20)} chance of more than 20 cm</div>
      </div>
      <div class="chips">
        ${agr ? `<span class="chip ${agr[0]}"><span class="dot" style="background:var(--${agr[0] === "good" ? "good" : agr[0] === "warn" ? "warn" : "serious"})"></span>${agr[1]}</span>` : ""}
        ${fl ? `<span class="chip">Freezing level now ~${Math.round(fl[2] / 50) * 50}m</span>` : ""}
        ${B.next7d ? `<span class="chip">7 days: ${cm(B.next7d.p50)} cm (${cm(B.next7d.p10)}–${cm(B.next7d.p90)})</span>` : ""}
      </div>
    </div>`;
  }

  function daysCard(B) {
    const max = Math.max(10, ...B.days.map((d) => (d.snow ? d.snow.p90 || 0 : 0)));
    const x = (v) => Math.min(100, (Math.max(0, v || 0) / max) * 100);
    const rows = B.days.map((d, i) => {
      const s = d.snow;
      const label = i === 0 ? "Today" : d.dow;
      const sub = i === 0 ? `from ${d.partial_from}` : d.date.slice(8) + "/" + d.date.slice(5, 7);
      if (!s) return `<div class="day"><div class="d">${label}<small>${sub}</small></div><div class="muted" style="font-size:13px">no coverage</div><div></div></div>`;
      const reg = d.regime && d.regime.code !== "dry" ? d.regime.label : d.regime ? "Mostly dry" : "";
      return `<div class="day${openDay === i ? " open" : ""}" data-day="${i}">
        <div class="d">${label}<small>${sub}</small></div>
        <div class="bar" role="img" aria-label="median ${cm(s.p50)} cm, 80% range ${cm(s.p10)} to ${cm(s.p90)} cm">
          <div class="track"></div>
          <div class="rng" style="left:${x(s.p10)}%;width:max(4px,${x(s.p90) - x(s.p10)}%)"></div>
          <div class="iqr" style="left:${x(s.p25)}%;width:max(4px,${x(s.p75) - x(s.p25)}%)"></div>
          <div class="med" style="left:${x(s.p50)}%"></div>
        </div>
        <div class="v">${cm(s.p50)}<small>${s.p_gt10 >= 0.05 ? pct(s.p_gt10) + " >10" : "cm"}</small></div>
        <div class="detail"><div class="kv">
          <span>Range</span><b>${cm(s.p10)}–${cm(s.p90)} cm (middle half ${cm(s.p25)}–${cm(s.p75)})</b>
          <span>Chances</span><b>${pct(s.p_gt10)} over 10 cm · ${pct(s.p_gt30)} over 30 cm</b>
          <span>By model</span><b>${Object.entries(s.by_model).map(([m, v]) => `${modelName(m)} ${cm(v)}`).join(" · ")}</b>
          <span>Raw model</span><b>${cm(d.raw_model_p50)} cm <span class="muted">(Open-Meteo snowfall, no elevation fix)</span></b>
          ${reg ? `<span>Flow</span><b>${esc(reg)}</b>` : ""}
        </div></div>
      </div>`;
    }).join("");
    return `<div class="card"><h2>Daily new snow · ${esc(B.label)} <span class="note">tap a day</span></h2>
      <div class="days">${rows}</div>
      <div class="legend"><span><span class="sw" style="background:var(--snow);width:4px;height:14px"></span>Median</span>
      <span><span class="sw" style="background:var(--snow-range-strong)"></span>Middle 50%</span>
      <span><span class="sw" style="background:var(--snow-range)"></span>80% range</span></div></div>`;
  }

  const modelName = (id) => ((data.models || []).find((m) => m.id === id) || { name: id }).name.replace("MeteoSwiss ", "");

  // ---------- SVG helpers ----------
  const NS = "http://www.w3.org/2000/svg";
  function svgEl(w, h) { return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="${NS}">`; }
  function attachTip(container, svg, points, html) {
    // points: [{x, y}] in svg coords; html(i) -> tooltip content
    const tip = document.createElement("div");
    tip.className = "tip";
    container.appendChild(tip);
    const cursor = svg.querySelector(".cursor");
    const show = (ev) => {
      const r = svg.getBoundingClientRect();
      const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
      let best = 0;
      points.forEach((p, i) => { if (Math.abs(p.x - px) < Math.abs(points[best].x - px)) best = i; });
      const p = points[best];
      tip.innerHTML = html(best);
      tip.style.left = Math.max(60, Math.min(r.width - 60, p.x)) + "px";
      tip.style.top = p.y + "px";
      tip.classList.add("show");
      if (cursor) { cursor.setAttribute("x1", p.x); cursor.setAttribute("x2", p.x); cursor.style.opacity = 1; }
    };
    const hide = () => { tip.classList.remove("show"); if (cursor) cursor.style.opacity = 0; };
    svg.addEventListener("pointerdown", show);
    svg.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse" || e.buttons) show(e); });
    svg.addEventListener("pointerleave", hide);
    svg.addEventListener("touchmove", show, { passive: true });
    document.addEventListener("pointerdown", (e) => { if (!container.contains(e.target)) hide(); });
  }
  function niceMax(v) { const steps = [5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200]; return steps.find((s) => s >= v) || Math.ceil(v / 50) * 50; }
  function dayTicks(t0, t1) {
    const out = [];
    for (let t = Math.ceil(t0 / 3600) * 3600; t <= t1; t += 3600) if (parseInt(fHour.format(t * 1000), 10) % 24 === 0) out.push(t);
    return out;
  }

  function timingChart(B) {
    const card = $("timingCard");
    const blocks = B.blocks3h || [];
    card.innerHTML = `<h2>Timing · next 72h in 3-hour blocks</h2><div class="chart"></div>
      <div class="legend"><span><span class="sw" style="background:var(--snow)"></span>Median</span><span><span class="sw" style="background:var(--snow-range)"></span>90th percentile</span></div>`;
    if (!blocks.length) return;
    const box = card.querySelector(".chart");
    const W = box.clientWidth || 340, H = 150, L = 28, R = 4, T = 8, Bm = 22;
    const ymax = niceMax(Math.max(2, ...blocks.map((b) => b.p90 || 0)));
    const t0 = blocks[0].t0, t1 = blocks[blocks.length - 1].t0 + 3 * 3600;
    const xs = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
    const ys = (v) => T + (1 - v / ymax) * (H - T - Bm);
    const bw = Math.max(3, (W - L - R) / blocks.length - 2);
    let g = svgEl(W, H);
    [0, ymax / 2, ymax].forEach((v) => {
      g += `<line x1="${L}" x2="${W - R}" y1="${ys(v)}" y2="${ys(v)}" stroke="var(--line)" stroke-width="1"/>`;
      g += `<text x="${L - 5}" y="${ys(v) + 4}" text-anchor="end" font-size="10.5" fill="var(--text-3)">${v}</text>`;
    });
    dayTicks(t0, t1).forEach((t) => {
      g += `<line x1="${xs(t)}" x2="${xs(t)}" y1="${T}" y2="${H - Bm}" stroke="var(--line)" stroke-dasharray="2 3"/>`;
      if (xs(t) < W - R - 24) g += `<text x="${xs(t) + 3}" y="${H - 6}" font-size="11" fill="var(--text-2)">${fDow.format(t * 1000)}</text>`;
    });
    const pts = [];
    blocks.forEach((b) => {
      const x = xs(b.t0) + 1, y90 = ys(b.p90 || 0), y50 = ys(b.p50 || 0), base = ys(0);
      if (b.p90 > 0.05) g += `<path d="${bar(x, y90, bw, base)}" fill="var(--snow-range)"/>`;
      if (b.p50 > 0.05) g += `<path d="${bar(x, y50, bw, base)}" fill="var(--snow)"/>`;
      pts.push({ x: x + bw / 2, y: y90 });
    });
    g += `<line class="cursor" y1="${T}" y2="${H - Bm}" stroke="var(--text-3)" stroke-width="1" style="opacity:0"/>`;
    g += `<rect x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg>`;
    box.innerHTML = g;
    attachTip(box, box.querySelector("svg"), pts, (i) => {
      const b = blocks[i];
      return `<b>${fDayHour.format(b.t0 * 1000)}–${fTime.format((b.t0 + 10800) * 1000)}</b><br>median ${cm(b.p50)} cm · 90th ${cm(b.p90)} cm`;
    });
  }
  function bar(x, y, w, base) {
    const h = base - y, r = Math.min(4, h, w / 2);
    if (h <= 0) return "";
    return `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${base}Z`;
  }

  function flChart(s, B) {
    const card = $("flCard");
    const fl = s.freezing_level || [];
    card.innerHTML = `<h2>Freezing level</h2><div class="chart"></div>
      <div class="legend"><span><span class="sw" style="background:var(--fl);height:3px"></span>Median</span><span><span class="sw" style="background:var(--fl-range)"></span>80% range</span>
      <span><span class="sw" style="border-top:2px dashed var(--text-2);height:0;border-radius:0"></span>${esc(B.label)}</span></div>
      <div class="axis-note">Snow usually falls down to about 300m below the freezing level. MeteoSwiss reports it directly; for other models it is estimated from temperature.</div>`;
    if (fl.length < 2) return;
    const box = card.querySelector(".chart");
    const W = box.clientWidth || 340, H = 170, L = 40, R = 6, T = 10, Bm = 22;
    const lo = Math.min(B.elev, ...fl.map((p) => p[1])) - 200, hi = Math.max(B.elev, ...fl.map((p) => p[3])) + 200;
    const y0 = Math.floor(lo / 500) * 500, y1 = Math.ceil(hi / 500) * 500;
    const t0 = fl[0][0], t1 = fl[fl.length - 1][0];
    const xs = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
    const ys = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - Bm);
    let g = svgEl(W, H);
    const step = (y1 - y0) / 500 > 6 ? 1000 : 500;
    for (let v = y0; v <= y1; v += step) {
      g += `<line x1="${L}" x2="${W - R}" y1="${ys(v)}" y2="${ys(v)}" stroke="var(--line)"/>`;
      g += `<text x="${L - 5}" y="${ys(v) + 4}" text-anchor="end" font-size="10.5" fill="var(--text-3)">${v}</text>`;
    }
    dayTicks(t0, t1).forEach((t) => {
      if (xs(t) < W - R - 24) g += `<text x="${xs(t) + 2}" y="${H - 6}" font-size="11" fill="var(--text-2)">${fDow.format(t * 1000)}</text>`;
      g += `<line x1="${xs(t)}" x2="${xs(t)}" y1="${T}" y2="${H - Bm}" stroke="var(--line)" stroke-dasharray="2 3"/>`;
    });
    const area = fl.map((p) => `${xs(p[0])},${ys(p[3])}`).join(" ") + " " + fl.slice().reverse().map((p) => `${xs(p[0])},${ys(p[1])}`).join(" ");
    g += `<polygon points="${area}" fill="var(--fl-range)"/>`;
    g += `<polyline points="${fl.map((p) => `${xs(p[0])},${ys(p[2])}`).join(" ")}" fill="none" stroke="var(--fl)" stroke-width="2" stroke-linejoin="round"/>`;
    g += `<line x1="${L}" x2="${W - R}" y1="${ys(B.elev)}" y2="${ys(B.elev)}" stroke="var(--text-2)" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    g += `<text x="${W - R - 2}" y="${ys(B.elev) - 5}" text-anchor="end" font-size="11" fill="var(--text-2)" paint-order="stroke" stroke="var(--surface)" stroke-width="3">${B.elev}m</text>`;
    g += `<line class="cursor" y1="${T}" y2="${H - Bm}" stroke="var(--text-3)" style="opacity:0"/>`;
    g += `<rect x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg>`;
    box.innerHTML = g;
    const pts = fl.map((p) => ({ x: xs(p[0]), y: ys(p[3]) }));
    attachTip(box, box.querySelector("svg"), pts, (i) => {
      const p = fl[i];
      return `<b>${fDayHour.format(p[0] * 1000)}</b><br>${p[2]}m <span style="opacity:.75">(${p[1]}–${p[3]})</span>`;
    });
  }

  function spark(series, W = 300, H = 38) {
    if (!series || series.length < 2) return "";
    const v = series.map((p) => p[1]);
    const lo = Math.min(...v), hi = Math.max(...v, lo + 20);
    const t0 = series[0][0], t1 = series[series.length - 1][0];
    const xs = (t) => 2 + ((t - t0) / (t1 - t0 || 1)) * (W - 4);
    const ys = (x) => 4 + (1 - (x - lo) / (hi - lo)) * (H - 8);
    const last = series[series.length - 1];
    return `<svg width="100%" height="${H}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="snow depth, last 7 days">
      <polyline points="${series.map((p) => `${xs(p[0])},${ys(p[1])}`).join(" ")}" fill="none" stroke="var(--snow)" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
      <circle cx="${xs(last[0])}" cy="${ys(last[1])}" r="3" fill="var(--snow)" stroke="var(--surface)" stroke-width="2"/></svg>`;
  }

  function stationsCard(obs) {
    if (!obs) return "";
    const sign = (v) => (v == null ? "–" : (v > 0 ? "+" : "") + Math.round(v));
    const rows = obs.stations.map((st) => st.ok ? `<div class="st">
        <div><div class="name">${esc(st.name)} <small>${st.elev}m</small></div>
        <div class="chg">24h ${sign(st.d24)} cm · 72h ${sign(st.d72)} cm${st.temp_c != null ? ` · ${st.temp_c.toFixed(1)}°C` : ""}</div></div>
        <div class="hs">${Math.round(st.hs_cm)}<small> cm</small></div>
        <div class="spark">${spark(st.series)}</div>
        <div class="muted" style="font-size:11.5px;grid-column:1/-1">reading ${fDayHour.format(st.hs_time * 1000)} · 7-day trend</div>
      </div>` : `<div class="st"><div><div class="name">${esc(st.name)} <small>${st.elev}m</small></div>
        <div class="chg muted">No live reading (${esc(st.error || "unavailable")})</div></div></div>`).join("");
    return `<div class="card"><h2>Snow depth, last 7 days <span class="note">ARPA stations</span></h2><div class="stations">${rows}</div>
      <div class="axis-note">Depth changes include settling, so a 24h gain is a rough guide to new snow.</div></div>`;
  }

  const AV_COL = { 1: "#ccff66", 2: "#ffff00", 3: "#ff9900", 4: "#ff0000", 5: "#a50000" };
  const AV_NAME = { low: "Low", moderate: "Moderate", considerable: "Considerable", high: "High", very_high: "Very high" };
  const AV_NUM = { low: 1, moderate: 2, considerable: 3, high: 4, very_high: 5 };
  const PROB = { new_snow: "new snow", wind_slab: "wind slab", persistent_weak_layers: "persistent weak layers",
    wet_snow: "wet snow", gliding_snow: "gliding snow", favourable_situation: "favourable situation" };
  function avalancheCard(av) {
    if (!av) return "";
    if (av.days.every((d) => !d.published && !d.error)) {
      return `<div class="card"><h2>Avalanche danger <span class="note">Alpi Pennine di confine</span></h2>
        <div class="muted">No bulletin yet. AINEVA publishes December–May; it will show here automatically.</div></div>`;
    }
    const days = av.days.map((d, i) => {
      const lbl = i === 0 ? "Today" : "Tomorrow";
      if (!d.published) return `<div class="muted" style="margin-bottom:6px">${lbl}: not published${d.error ? " (fetch error)" : " yet. AINEVA bulletins run December–May"}</div>`;
      if (!d.region_found) return `<div class="muted">${lbl}: published, but Alagna's zone wasn't in it</div>`;
      const top = d.ratings.reduce((a, r) => (AV_NUM[r.level] > AV_NUM[a.level] ? r : a), d.ratings[0]);
      const n = AV_NUM[top.level] || 0;
      return `<div class="av-row"><span class="av-level" style="background:${AV_COL[n] || "#ccc"};color:${n === 5 ? "#fff" : "#111"}">${n}</span>
        <div><b>${lbl}: ${AV_NAME[top.level] || esc(top.level)}</b> <span class="muted">${d.ratings.map((r) => `${AV_NAME[r.level] || r.level} ${r.where}${r.period ? " (" + r.period + ")" : ""}`).join(" · ")}</span>
        ${d.problems.length ? `<div class="muted" style="font-size:13px">${[...new Set(d.problems.map((p) => PROB[p.type] || p.type))].join(", ")}</div>` : ""}</div></div>`;
    }).join("");
    return `<div class="card"><h2>Avalanche danger <span class="note">Alpi Pennine di confine</span></h2>${days}
      <div class="axis-note">Always read the full AINEVA bulletin before going off-piste.</div></div>`;
  }

  function modelsCard(s, B) {
    const m72 = (B.next72h || {}).by_model || {}, m7 = (B.next7d || {}).by_model || {};
    const rows = (s.models || []).map((m) => `<tr>
      <td>${esc(m.name)}${m.ok ? "" : ` <span style="color:var(--serious)">${m.using_archived ? "· old run" : "· failed"}</span>`}</td>
      <td>${m.members ?? "–"}</td><td>${m.horizon_h ? Math.round(m.horizon_h / 24 * 10) / 10 + "d" : "–"}</td>
      <td>${m.id in m72 ? cm(m72[m.id]) : "–"}</td><td>${m.id in m7 ? cm(m7[m.id]) : "–"}</td></tr>`).join("");
    return `<div class="card"><h2>Models <span class="note">median cm at ${B.elev}m</span></h2>
      <table class="models"><thead><tr><th>Model</th><th>Memb.</th><th>Range</th><th>72h</th><th>7d</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="axis-note">A dash means the model doesn't reach that far. Every model gets equal weight in the totals above.</div>
      ${REPO && !REPO.startsWith("__") ? `<div class="axis-note"><a href="https://github.com/${REPO}/actions/workflows/update.yml" style="color:var(--snow)">Force a fresh fetch now</a> (tap "Run workflow", then refresh here in ~2 min)</div>` : ""}</div>`;
  }

  function footer(s) {
    return `Forecast data: Open-Meteo (ECMWF, DWD, NOAA, MeteoSwiss). Snow and avalanche data: Arpa Piemonte (CC BY 4.0), AINEVA/EAWS. Webcams: Monterosa Ski.<br>
      ${esc(s.method && s.method.snow)}<br>Times are Alagna local time. Built ${fDayHour.format(s.generated_at * 1000)}.`;
  }

  // ---------- events ----------
  $("refresh").addEventListener("click", load);
  $("bands").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-band]");
    if (!b) return;
    band = b.dataset.band; store.set("snowcast:band", band); render();
  });
  $("main").addEventListener("click", (e) => {
    const d = e.target.closest(".day[data-day]");
    if (!d) return;
    const i = +d.dataset.day;
    openDay = openDay === i ? null : i;
    d.parentElement.querySelectorAll(".day").forEach((el) => el.classList.toggle("open", +el.dataset.day === openDay));
  });
  let rz; addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => data && render(), 200); });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && data && Date.now() / 1000 - data.generated_at > 20 * 60) load();
  });
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});

  data = store.get("snowcast:last");
  if (data) render();
  load();
})();
