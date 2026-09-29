/* =========================================================================
   DRISHTI - visual effects + adaptive layout (vanilla ports of popular
   React Bits patterns: DotGrid, SplitText/BlurText, SpotlightCard,
   Magnet, LogoLoop, AnimatedContent). No dependencies.
   ========================================================================= */
(function () {
  "use strict";
  var doc = document, root = doc.documentElement;
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $$ = function (s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); };

  /* ---------- Lucide icons ---------- */
  function hydrateIcons(scope) {
    $$("[data-lu]", scope).forEach(function (n) {
      var inner = window.LU && window.LU[n.getAttribute("data-lu")];
      if (!inner) return;
      var s = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
      s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("class", "icon " + (n.className || "")); s.setAttribute("aria-hidden", "true");
      s.innerHTML = inner; n.replaceWith(s);
    });
  }
  hydrateIcons(doc);

  /* ---------- window size classes, orientation, posture (fold / unfold) ---------- */
  var lastClass = "";
  function sizeClass() {
    var vv = window.visualViewport, w = Math.round(vv ? vv.width : window.innerWidth), h = Math.round(vv ? vv.height : window.innerHeight);
    var cls = w < 600 ? "compact" : w < 1024 ? "medium" : "expanded";
    root.dataset.layout = cls;
    root.dataset.orient = w > h ? "landscape" : "portrait";
    root.style.setProperty("--vvh", h + "px");
    var posture = (navigator.devicePosture && navigator.devicePosture.type) || "";
    root.dataset.posture = posture || (window.matchMedia && matchMedia("(horizontal-viewport-segments: 2)").matches ? "dual" : "flat");
    if (cls !== lastClass) {
      // leaving the drawer layout (e.g. unfolding) must not leave the slide-over open
      var app = doc.getElementById("app"); if (app && cls !== "compact") app.classList.remove("nav-open");
      lastClass = cls;
    }
  }
  var rq; function schedule() { cancelAnimationFrame(rq); rq = requestAnimationFrame(sizeClass); }
  window.addEventListener("resize", schedule);
  window.addEventListener("orientationchange", schedule);
  if (window.visualViewport) visualViewport.addEventListener("resize", schedule);
  if (navigator.devicePosture && navigator.devicePosture.addEventListener) navigator.devicePosture.addEventListener("change", schedule);
  if (window.matchMedia) { try { matchMedia("(horizontal-viewport-segments: 2)").addEventListener("change", schedule); } catch (e) {} }
  sizeClass();

  /* ---------- tooltips for the icon rail ---------- */
  $$(".nav__item").forEach(function (a) { var t = a.querySelector("span"); if (t) a.title = t.textContent; });

  /* ---------- SplitText / BlurText ---------- */
  function split(el) {
    var mode = el.getAttribute("data-split"), txt = el.textContent; el.textContent = "";
    var parts = mode === "chars" ? txt.split("") : txt.split(/(\s+)/);
    var i = 0;
    parts.forEach(function (p) {
      if (/^\s+$/.test(p)) { el.appendChild(doc.createTextNode(" ")); return; }
      var s = doc.createElement("span"); s.className = "sp"; s.textContent = p; s.style.setProperty("--i", i++); el.appendChild(s);
    });
  }
  $$("[data-split]").forEach(split);
  $$(".lsec__head h2, .lcta h2").forEach(function (h) { h.setAttribute("data-split", "words"); split(h); });

  /* ---------- scroll reveal (AnimatedContent) ---------- */
  var reveal = [".lsec__head", ".ps-card", ".pain > div", ".layers > div", ".feat > div", ".steps > div", ".lcta", ".lnote", ".marquee"].join(",");
  var targets = $$(reveal);
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: .12, rootMargin: "0px 0px -6% 0px" });
    targets.forEach(function (t, i) { t.classList.add("rv"); t.style.transitionDelay = (i % 4) * 70 + "ms"; io.observe(t); });
  } else targets.forEach(function (t) { t.classList.add("in"); });

  /* ---------- SpotlightCard ---------- */
  var spotSel = ".card, .kpi, .att, .feat > div, .layers > div, .pain > div, .ps-card, .kcard, .col, .heatcell";
  doc.addEventListener("pointermove", function (e) {
    if (e.pointerType === "touch") return;
    var c = e.target.closest && e.target.closest(spotSel);
    if (!c) return;
    var r = c.getBoundingClientRect();
    c.style.setProperty("--mx", (e.clientX - r.left) + "px"); c.style.setProperty("--my", (e.clientY - r.top) + "px");
  }, { passive: true });

  /* ---------- Magnet buttons ---------- */
  if (!reduce && window.matchMedia && matchMedia("(hover: hover)").matches) {
    $$("[data-launch].btn--primary, .lcta .btn").forEach(function (b) {
      b.addEventListener("pointermove", function (e) { var r = b.getBoundingClientRect(); b.style.transform = "translate(" + ((e.clientX - r.left - r.width / 2) * .18).toFixed(1) + "px," + ((e.clientY - r.top - r.height / 2) * .28).toFixed(1) + "px)"; });
      b.addEventListener("pointerleave", function () { b.style.transform = ""; });
    });
  }

  /* ---------- DotGrid (interactive canvas background) ---------- */
  function dotGrid(canvas) {
    var ctx = canvas.getContext("2d"), dots = [], mouse = { x: -999, y: -999 }, W = 0, H = 0, raf = 0, visible = true, gap = 26;
    function build() {
      var host = canvas.parentElement, r = host.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
      W = Math.max(1, r.width); H = Math.max(1, r.height);
      canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      dots = []; var cols = Math.floor(W / gap), rows = Math.floor(H / gap), ox = (W - (cols - 1) * gap) / 2, oy = (H - (rows - 1) * gap) / 2;
      for (var y = 0; y < rows; y++) for (var x = 0; x < cols; x++) dots.push({ x: ox + x * gap, y: oy + y * gap, dx: 0, dy: 0 });
      draw();
    }
    function draw() {
      ctx.clearRect(0, 0, W, H);
      var dark = canvas.dataset.tone === "dark" || root.dataset.theme === "dark";
      var base = dark ? "230,232,230" : "25,25,25", alphaBase = dark ? .18 : .16;
      for (var i = 0; i < dots.length; i++) {
        var d = dots[i], ddx = mouse.x - d.x, ddy = mouse.y - d.y, dist = Math.sqrt(ddx * ddx + ddy * ddy), R = 130;
        var near = dist < R ? 1 - dist / R : 0;
        if (near > 0 && !reduce) { d.dx += (-ddx / (dist || 1) * near * 10 - d.dx) * .12; d.dy += (-ddy / (dist || 1) * near * 10 - d.dy) * .12; }
        else { d.dx *= .88; d.dy *= .88; }
        ctx.beginPath(); ctx.arc(d.x + d.dx, d.y + d.dy, 1.4 + near * 2.2, 0, 6.283);
        ctx.fillStyle = near > .05 ? "rgba(241,80,37," + (.35 + near * .65).toFixed(2) + ")" : "rgba(" + base + "," + alphaBase + ")";
        ctx.fill();
      }
      if (visible && !reduce) raf = requestAnimationFrame(draw);
    }
    var host = canvas.parentElement;
    host.addEventListener("pointermove", function (e) { var r = canvas.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; });
    host.addEventListener("pointerleave", function () { mouse.x = mouse.y = -999; });
    if ("ResizeObserver" in window) new ResizeObserver(function () { build(); }).observe(host); else window.addEventListener("resize", build);
    if ("IntersectionObserver" in window) new IntersectionObserver(function (es) { var v = es[0].isIntersecting; if (v && !visible) { visible = true; draw(); } visible = v; }).observe(canvas);
    build();
  }
  $$("[data-dotgrid]").forEach(dotGrid);
  // theme changes redraw static dots for reduced-motion users
  new MutationObserver(function () { $$("[data-dotgrid]").forEach(function (c) { c.dispatchEvent(new Event("redraw")); }); }).observe(root, { attributes: true, attributeFilter: ["data-theme"] });

  /* ---------- hydrate icons injected later (case drawer, cards) ---------- */
  new MutationObserver(function (ms) {
    ms.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1 && (n.hasAttribute("data-lu") || n.querySelector("[data-lu]"))) hydrateIcons(n.parentNode || doc); }); });
  }).observe(doc.body, { childList: true, subtree: true });
})();
