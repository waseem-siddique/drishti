/* DRISHTI - dependency-free charts (SVG + HTML), theme aware via CSS variables. */
(function (global) {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs) {
    var n = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function svg(w, h, cls) { return el("svg", { viewBox: "0 0 " + w + " " + h, class: "chart " + (cls || ""), role: "img", preserveAspectRatio: "xMidYMid meet" }); }
  function text(x, y, str, cls, anchor) { var t = el("text", { x: x, y: y, class: cls, "text-anchor": anchor || "middle" }); t.textContent = str; return t; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  var tip;
  function showTip(evt, html) {
    if (!tip) { tip = document.createElement("div"); tip.className = "chart-tip"; document.body.appendChild(tip); }
    tip.innerHTML = html; tip.hidden = false;
    tip.style.left = Math.min(evt.clientX + 12, window.innerWidth - tip.offsetWidth - 8) + "px";
    tip.style.top = (evt.clientY - 34) + "px";
  }
  function hideTip() { if (tip) tip.hidden = true; }

  function donut(data, opts) {
    opts = opts || {};
    var size = 200, r = 76, sw = 18, cx = 100, cy = 100, C = 2 * Math.PI * r;
    var total = data.reduce(function (a, d) { return a + d.value; }, 0) || 1;
    var s = svg(size, size, "chart--donut");
    s.appendChild(el("circle", { cx: cx, cy: cy, r: r, fill: "none", "stroke-width": sw, class: "chart__track" }));
    var off = 0, gap = data.filter(function (d) { return d.value; }).length > 1 ? 3 : 0;
    data.forEach(function (d) {
      if (!d.value) return;
      var len = (d.value / total) * C;
      var arc = el("circle", { cx: cx, cy: cy, r: r, fill: "none", "stroke-width": sw, "stroke-dasharray": Math.max(len - gap, 1) + " " + (C - Math.max(len - gap, 1)), "stroke-dashoffset": -off, transform: "rotate(-90 100 100)", class: "chart__arc sev-" + d.key });
      arc.addEventListener("mousemove", function (e) { showTip(e, "<b>" + esc(d.key) + "</b> · " + d.value + " (" + Math.round(d.value / total * 100) + "%)"); });
      arc.addEventListener("mouseleave", hideTip);
      s.appendChild(arc); off += len;
    });
    s.appendChild(text(cx, cy + 4, String(opts.centerValue != null ? opts.centerValue : total), "chart__big"));
    s.appendChild(text(cx, cy + 24, opts.centerLabel || "total", "chart__sub"));
    return s;
  }

  /* HTML horizontal bars with labels outside the fill (readable in both themes). */
  function bars(data, opts) {
    opts = opts || {};
    var max = opts.max || Math.max.apply(null, data.map(function (d) { return d.value; }).concat([1]));
    var wrap = document.createElement("div"); wrap.className = "hbars";
    data.forEach(function (d) {
      var row = document.createElement(d.onClick ? "button" : "div");
      row.className = "hbar"; if (d.onClick) { row.type = "button"; row.addEventListener("click", d.onClick); }
      row.innerHTML = '<span class="hbar__label" title="' + esc(d.label) + '">' + esc(d.label) + "</span>" +
        '<span class="hbar__track"><span class="hbar__fill ' + (d.tone ? "tone-" + d.tone : "") + '" style="width:0"></span></span>' +
        '<span class="hbar__value">' + esc(d.display != null ? d.display : d.value) + "</span>";
      wrap.appendChild(row);
      requestAnimationFrame(function () { row.querySelector(".hbar__fill").style.width = Math.max(1.5, d.value / max * 100) + "%"; });
    });
    return wrap;
  }

  function line(points, opts) {
    opts = opts || {};
    var w = 640, h = 220, pl = 54, pr = 12, pt = 14, pb = 28;
    var s = svg(w, h, "chart--line");
    if (!points.length) return s;
    var max = Math.max.apply(null, points.map(function (p) { return p.value; }).concat([1])) * 1.08;
    var step = (w - pl - pr) / Math.max(points.length - 1, 1);
    var X = function (i) { return pl + i * step; }, Y = function (v) { return pt + (1 - v / max) * (h - pt - pb); };
    [0, .25, .5, .75, 1].forEach(function (f) {
      var y = pt + f * (h - pt - pb);
      s.appendChild(el("line", { x1: pl, y1: y, x2: w - pr, y2: y, class: "chart__grid", "stroke-dasharray": f === 1 ? "" : "2 4" }));
      if (f % .5 === 0) s.appendChild(text(pl - 8, y + 4, opts.format ? opts.format(max * (1 - f)) : Math.round(max * (1 - f)), "chart__axis", "end"));
    });
    var d = points.map(function (p, i) { return (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(p.value).toFixed(1); }).join(" ");
    s.appendChild(el("path", { d: d + " L" + X(points.length - 1) + " " + (h - pb) + " L" + pl + " " + (h - pb) + " Z", class: "chart__area" }));
    s.appendChild(el("path", { d: d, class: "chart__line" }));
    points.forEach(function (p, i) {
      if (points.length < 16 || i % 2 === 0) s.appendChild(text(X(i), h - 8, p.label, "chart__axis"));
      var dot = el("circle", { cx: X(i), cy: Y(p.value), r: 3, class: "chart__dot" });
      s.appendChild(dot);
      var hit = el("rect", { x: X(i) - step / 2, y: pt, width: step, height: h - pt - pb, class: "chart__hit" });
      hit.addEventListener("mousemove", function (e) { dot.setAttribute("r", 5); showTip(e, "<b>" + esc(p.label) + "</b> · " + esc(opts.format ? opts.format(p.value) : p.value)); });
      hit.addEventListener("mouseleave", function () { dot.setAttribute("r", 3); hideTip(); });
      s.appendChild(hit);
    });
    return s;
  }

  function spark(values) {
    var w = 200, h = 34, s = svg(w, h, "kpi__spark");
    if (values.length < 2) return s;
    var max = Math.max.apply(null, values), min = Math.min.apply(null, values), span = (max - min) || 1;
    var step = w / (values.length - 1);
    var d = values.map(function (v, i) { return (i ? "L" : "M") + (i * step).toFixed(1) + " " + (h - 3 - (v - min) / span * (h - 6)).toFixed(1); }).join(" ");
    s.setAttribute("preserveAspectRatio", "none");
    s.appendChild(el("path", { d: d + " L" + w + " " + h + " L0 " + h + " Z", class: "chart__sparkarea" }));
    s.appendChild(el("path", { d: d, class: "chart__spark", "vector-effect": "non-scaling-stroke" }));
    return s;
  }

  function gauge(score, severity) {
    var size = 132, r = 54, cx = 66, cy = 66, C = 2 * Math.PI * r;
    var s = svg(size, size, "chart--gauge");
    s.appendChild(el("circle", { cx: cx, cy: cy, r: r, fill: "none", "stroke-width": 10, class: "chart__track" }));
    s.appendChild(el("circle", { cx: cx, cy: cy, r: r, fill: "none", "stroke-width": 10, "stroke-linecap": "round", "stroke-dasharray": (score / 100) * C + " " + C, transform: "rotate(-90 66 66)", class: "chart__arc sev-" + severity }));
    s.appendChild(text(cx, cy + 6, String(score), "chart__big"));
    s.appendChild(text(cx, cy + 25, "risk score", "chart__sub"));
    return s;
  }

  function heatGrid(cells, onPick) {
    var wrap = document.createElement("div"); wrap.className = "heatgrid";
    var max = Math.max.apply(null, cells.map(function (c) { return c.value; }).concat([1]));
    cells.forEach(function (c) {
      var b = document.createElement("button"); b.type = "button"; b.className = "heatcell";
      b.style.setProperty("--intensity", (c.value / max).toFixed(3));
      b.innerHTML = '<span class="heatcell__label">' + esc(c.label) + '</span><span class="heatcell__state">' + esc(c.state || "") + "</span>" +
        '<span class="heatcell__value">' + esc(c.display) + '</span><span class="heatcell__sub">' + esc(c.sub || "") + "</span>";
      if (onPick) b.addEventListener("click", function () { onPick(c); });
      wrap.appendChild(b);
    });
    return wrap;
  }

  global.Charts = { donut: donut, bars: bars, line: line, spark: spark, gauge: gauge, heatGrid: heatGrid };
})(window);
