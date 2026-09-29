/* =========================================================================
   DRISHTI - frontend application (vanilla JS, no build step)
   Landing page, console, case management, policy studio, collaboration.
   ========================================================================= */
(function () {
  "use strict";

  var DEFAULT_FILTERS = { severity: "all", status: "all", state: "all", district: "all", category: "all", code: "all", sla: "all", assignee: "all", watch: "", q: "", sort: "risk", page: 1, limit: 25 };
  var State = {
    token: localStorage.getItem("drishti-token") || "",
    user: JSON.parse(localStorage.getItem("drishti-user") || "null"),
    filters: Object.assign({}, DEFAULT_FILTERS),
    activeView: null,
    options: null, users: null, views: null,
    selected: {},
    focusRow: -1,
    lastItems: []
  };

  var ROUTES = {
    dashboard: { title: "Overview", subtitle: "What needs attention in your jurisdiction today", render: renderDashboard },
    alerts: { title: "Alert queue", subtitle: "Ranked works that need officer review", render: renderAlerts },
    board: { title: "Case board", subtitle: "Move cases from triage to closure, within SLA", render: renderBoard },
    districts: { title: "Risk map", subtitle: "Where risk concentrates, district by district", render: renderDistricts },
    watchlist: { title: "Watchlist", subtitle: "Works you are following", render: renderWatchlist },
    scorecards: { title: "Scorecards", subtitle: "Accountability league tables for agencies, MPs and districts", render: renderScorecards },
    analytics: { title: "Analytics", subtitle: "Detection mix, categories and officer activity", render: renderAnalytics },
    quality: { title: "Data quality", subtitle: "Records too incomplete to score confidently", render: renderQuality },
    policy: { title: "Policy studio", subtitle: "Tune detection, simulate the impact, publish a versioned policy", render: renderPolicy },
    audit: { title: "Audit trail", subtitle: "Every login, decision and policy change", render: renderAudit },
    about: { title: "How it works", subtitle: "How DRISHTI decides what needs attention", render: renderAbout }
  };

  var REASON_NEXT = {
    COST_OVERRUN: "Obtain the revised estimate and technical sanction before releasing any further instalment.",
    PAYMENT_WITHOUT_PROGRESS: "Order a site inspection to verify physical progress against the measurement book.",
    STALLED_WORK: "Seek a status report from the implementing agency and confirm whether the site is active.",
    SCHEDULE_OVERRUN: "Ask the agency for a revised completion plan and the reasons for delay.",
    DUPLICATE_WORK: "Compare scope and location with the linked work to rule out a double sanction.",
    SPENDING_BURST: "Verify the bill and supporting vouchers behind the large instalment.",
    COST_OUTLIER: "Compare the estimate with the schedule of rates for similar works in the district.",
    RAPID_COMPLETION: "Verify the completion certificate with geo-tagged photos or a site visit.",
    LOW_DATA_QUALITY: "Ask the district to complete the missing fields before taking action.",
    ML_ANOMALY: "Review the full timeline. The combination of signals is rare across the portfolio."
  };

  /* ----------------------------- helpers -------------------------------- */
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function inr(v) {
    var n = Number(v || 0);
    if (Math.abs(n) >= 1e7) return "\u20b9" + (n / 1e7).toFixed(2) + " Cr";
    if (Math.abs(n) >= 1e5) return "\u20b9" + (n / 1e5).toFixed(1) + " L";
    return "\u20b9" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }
  function num(v) { return Number(v || 0).toLocaleString("en-IN"); }
  function pct(v) { return Math.round(Number(v || 0)) + "%"; }
  function dateFmt(v) {
    if (!v) return "\u2014";
    var d = new Date(String(v).slice(0, 10));
    return isNaN(d) ? String(v) : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  }
  function ago(v) {
    var d = new Date(v); if (isNaN(d)) return "";
    var s = (Date.now() - d.getTime()) / 1000;
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    if (s < 86400 * 30) return Math.floor(s / 86400) + "d ago";
    return dateFmt(v);
  }
  function codeLabel(c) { return String(c || "").replace(/_/g, " ").toLowerCase().replace(/^\w/, function (m) { return m.toUpperCase(); }); }
  function initials(name) { return String(name || "?").replace(/\(.*\)/, "").trim().split(/\s+/).filter(function (p) { return /[A-Za-z]/.test(p); }).slice(-2).map(function (p) { return p.replace(/[^A-Za-z]/g, "")[0] || ""; }).join("").toUpperCase() || "?"; }
  var AV_COLORS = ["#2783DE", "#46A171", "#D5803B", "#9B6BC4", "#D1628E", "#3AA6B9", "#C27D2E", "#6D7FD6"];
  function avColor(key) { var h = 0; String(key || "").split("").forEach(function (c) { h = (h * 31 + c.charCodeAt(0)) >>> 0; }); return AV_COLORS[h % AV_COLORS.length]; }
  function avatar(username, name, lg) {
    if (!username) return '<span class="avatar avatar--empty' + (lg ? " avatar--lg" : "") + '" title="Unassigned">?</span>';
    return '<span class="avatar' + (lg ? " avatar--lg" : "") + '" style="background:' + avColor(username) + '" title="' + esc(name || username) + '">' + esc(initials(name || username)) + "</span>";
  }
  function svgIcon(path) { return '<svg class="icon" viewBox="0 0 24 24">' + path + "</svg>"; }
  var ICONS = {
    alert: '<path d="M12 4 2.8 19.5h18.4zM12 10v4.5M12 17.2v.3"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    user: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    inbox: '<path d="M4 13.5 6.5 5h11l2.5 8.5V19H4zM4 13.5h5a3 3 0 0 0 6 0h5"/>',
    check: '<path d="m5 12.5 4.2 4.2L19 7"/>',
    star: '<path d="m12 4 2.4 4.9 5.4.8-3.9 3.8.9 5.4L12 16.4l-4.8 2.5.9-5.4-3.9-3.8 5.4-.8z"/>',
    chat: '<path d="M5 5h14v10H9.5L5 19z"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    print: '<path d="M7 9V4h10v5M7 17H5v-6h14v6h-2M7 14h10v6H7z"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    sparkle: '<path d="M12 3.5 13.8 10 20.5 12l-6.7 2L12 20.5 10.2 14 3.5 12l6.7-2z"/>',
    download: '<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>',
    policy: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4-4"/>',
    grid: '<path d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 8h6V4h-6z"/>',
    moon: '<path d="M20 14.5A8.2 8.2 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.5-5.8M20 4v4h-4"/>',
    out: '<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10"/>'
  };

  function toast(message, kind) {
    var node = document.createElement("div");
    node.className = "toast" + (kind ? " toast--" + kind : "");
    node.textContent = message;
    $("#toasts").appendChild(node);
    setTimeout(function () { node.remove(); }, 3600);
  }

  function api(path, options) {
    options = options || {};
    var headers = { "Content-Type": "application/json" };
    if (State.token) headers.Authorization = "Bearer " + State.token;
    return fetch(path, { method: options.method || "GET", headers: headers, body: options.body ? JSON.stringify(options.body) : undefined })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            if (res.status === 401 && State.token) signOut(true);
            throw new Error(data.error || "Request failed (" + res.status + ")");
          }
          return data;
        });
      });
  }

  function slaChip(state, hours) {
    if (!state || state === "closed") return '<span class="sla sla--closed">\u2014</span>';
    var label;
    if (state === "breached") label = "Overdue " + (Math.abs(hours) >= 48 ? Math.round(Math.abs(hours) / 24) + "d" : Math.abs(hours) + "h");
    else if (state === "due_soon") label = "Due in " + (hours >= 24 ? Math.round(hours / 24) + "d" : hours + "h");
    else label = (hours != null ? Math.round(hours / 24) + "d left" : "On track");
    return '<span class="sla sla--' + state + '">' + label + "</span>";
  }
  function sevBadge(sev) { return '<span class="badge badge--' + esc(sev) + '">' + esc(sev ? sev[0].toUpperCase() + sev.slice(1) : "") + "</span>"; }
  function statusLabel(s) { return { open: "Open", in_review: "In review", actioned: "Escalated", dismissed: "Closed" }[s] || s; }
  function statusPill(s) { return '<span class="status status--' + esc(s) + '"><i></i>' + statusLabel(s) + "</span>"; }
  function scoreCell(score, sev) {
    return '<span class="score">' + Number(score).toFixed(0) + '<span class="score__bar"><span class="sev-' + esc(sev) + '-bg" style="width:' + Math.min(100, score) + '%"></span></span></span>';
  }
  function loading(target) { target.innerHTML = '<div class="card"><div class="skeleton skeleton--row" style="width:40%"></div><div class="skeleton skeleton--row"></div><div class="skeleton skeleton--row"></div><div class="skeleton skeleton--row" style="width:70%"></div></div>'; }
  function errorCard(err) { return '<div class="card"><div class="empty">' + svgIcon(ICONS.alert) + "<strong>Could not load data</strong><p>" + esc(err.message) + "</p></div></div>"; }
  function empty(title, text, icon) { return '<div class="empty">' + svgIcon(icon || ICONS.inbox) + "<strong>" + esc(title) + "</strong><p>" + esc(text || "") + "</p></div>"; }
  function card(title, sub, body, extra, cls) {
    return '<section class="card' + (cls ? " " + cls : "") + '"><div class="card__head"><div><h3>' + esc(title) + "</h3>" + (sub ? "<p>" + esc(sub) + "</p>" : "") + "</div>" + (extra || "") + "</div>" + body + "</section>";
  }
  function goQueue(filters) {
    State.filters = Object.assign({}, DEFAULT_FILTERS, filters || {});
    State.activeView = null;
    if (location.hash === "#/alerts") router(); else location.hash = "#/alerts";
  }
  function loadUsers() { if (State.users) return Promise.resolve(State.users); return api("/api/users").then(function (d) { State.users = d.items; return d.items; }); }
  function loadOptions() { if (State.options) return Promise.resolve(State.options); return api("/api/filters").then(function (d) { State.options = d; return d; }); }
  function userName(u) { var f = (State.users || []).filter(function (x) { return x.username === u; })[0]; return f ? f.name : u; }

  /* ----------------------------- theme ---------------------------------- */
  function toggleTheme() {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("drishti-theme", next);
    var meta = $('meta[name="theme-color"]'); if (meta) meta.setAttribute("content", next === "dark" ? "#191919" : "#ffffff");
  }

  /* ----------------------------- auth / screens -------------------------- */
  function screen(name) {
    $("#landing").hidden = name !== "landing";
    $("#login-screen").hidden = name !== "login";
    $("#app").hidden = name !== "app";
    window.scrollTo(0, 0);
  }

  function hydrateUser() {
    var u = State.user || {};
    $("#user-name").textContent = String(u.name || u.username || "User").replace(/\s*\(.*\)/, "");
    $("#user-role").textContent = [u.role, u.district || u.state].filter(Boolean).join(" \u00b7 ");
    var ini = $("#user-initials"); ini.textContent = initials(u.name); ini.style.background = avColor(u.username);
    $("#ws-scope").textContent = u.district ? u.district + " district" : u.state ? u.state : "All India \u00b7 Ministry";
    var si = $("#side-initials"); si.textContent = initials(u.name); si.style.background = avColor(u.username);
    $("#side-name").textContent = String(u.name || u.username || "User").replace(/\s*\(.*\)/, "");
    $("#side-role").textContent = (u.role ? u.role[0].toUpperCase() + u.role.slice(1) : "");
    $("#rerun-detection").hidden = !(u.role === "ministry" || u.role === "state");
  }

  function signIn(username, password) {
    return api("/api/auth/login", { method: "POST", body: { username: username, password: password } }).then(function (data) {
      State.token = data.token; State.user = data.user;
      localStorage.setItem("drishti-token", data.token);
      localStorage.setItem("drishti-user", JSON.stringify(data.user));
      State.options = null; State.users = null; State.views = null;
      State.filters = Object.assign({}, DEFAULT_FILTERS);
      var next = sessionStorage.getItem("drishti-next");
      sessionStorage.removeItem("drishti-next");
      location.hash = next || "#/dashboard";
      router();
      toast("Signed in as " + data.user.name, "success");
    });
  }

  function signOut(silent) {
    State.token = ""; State.user = null; State.options = null; State.users = null;
    localStorage.removeItem("drishti-token"); localStorage.removeItem("drishti-user");
    closeDrawer(); closeModals();
    location.hash = "#/home";
    if (!silent) toast("Signed out");
  }

  /* ----------------------------- dashboard ------------------------------ */
  function greeting() { var h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; }

  function renderDashboard(view) {
    loading(view);
    Promise.all([api("/api/summary"), api("/api/alerts?limit=6&sort=risk&status=open")]).then(function (res) {
      var s = res[0], top = res[1], k = s.kpis, sla = s.sla;
      updateNavCounts(s);
      var first = String((State.user || {}).name || "").replace(/\s*\(.*\)/, "");
      var sevTotal = Math.max(1, s.severity.reduce(function (a, d) { return a + d.value; }, 0));

      view.innerHTML =
        '<div class="hello"><div><h2>' + greeting() + ", " + esc(first) + "</h2><p>" +
          new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" }) + " \u00b7 " + num(k.works) + " works monitored in " + esc($("#ws-scope").textContent) + "</p></div>" +
          '<div class="row"><button class="btn btn--ghost btn--sm" data-go="board">Open case board</button><button class="btn btn--primary btn--sm" data-q=\'{"sla":"breached"}\'>Review overdue cases</button></div></div>' +

        '<div class="attention">' +
          att("red", ICONS.clock, sla.breached, "cases past their SLA", { sla: "breached" }) +
          att("orange", ICONS.alert, sla.unassigned_critical, "critical cases with no owner", { severity: "critical", assignee: "none" }) +
          att("blue", ICONS.inbox, sla.due_soon, "due in the next 72 hours", { sla: "due_soon", sort: "due" }) +
          att("green", ICONS.user, sla.mine, "open cases assigned to you" + (sla.mine_breached ? " \u00b7 " + sla.mine_breached + " overdue" : ""), { assignee: "me" }) +
        "</div>" +

        '<section class="grid grid--kpi">' +
          kpi("Funds sanctioned", inr(k.sanctioned), inr(k.spent) + " utilised \u00b7 " + k.utilisation + "%", '<div class="meter"><span style="width:' + k.utilisation + '%"></span></div>') +
          kpi("Open risk signals", num(k.alerts), num(k.critical) + " critical \u00b7 " + num(k.high) + " high",
            '<div class="meter meter--stack">' + s.severity.map(function (d) { return '<span class="sev-' + d.key + '-bg" style="width:' + (d.value / sevTotal * 100) + '%"></span>'; }).join("") + "</div>") +
          kpi("Exposure under review", inr(k.amount_at_risk), "Sanction behind critical and high alerts", "", "spark") +
          kpi("SLA compliance", sla.compliance_pct + "%", num(sla.breached) + " breached of " + num(sla.breached + sla.due_soon + sla.on_track) + " active cases",
            '<div class="meter"><span style="width:' + sla.compliance_pct + "%;background:var(--" + (sla.compliance_pct >= 80 ? "ok" : sla.compliance_pct >= 60 ? "high" : "critical") + ')"></span></div>') +
        "</section>" +

        '<section class="grid grid--split">' +
          card("Spending trend", "Monthly expenditure recorded on sanctioned works", '<div id="chart-trend"></div>') +
          card("Severity mix", "All risk signals by score band", '<div id="chart-donut"></div><div class="legend">' +
            s.severity.map(function (d) { return '<span><i class="sev-' + d.key + '-bg"></i>' + d.key + " <b>" + d.value + "</b></span>"; }).join("") + "</div>") +
        "</section>" +

        '<section class="card card--flush"><div class="card__head"><div><h3>Top of the queue</h3><p>Highest-risk open cases. Select a row to open the case file.</p></div><a class="btn btn--ghost btn--sm" href="#/alerts">Open full queue</a></div>' +
          '<div class="table-wrap">' + alertTable(top.items, { compact: true }) + "</div></section>" +

        '<section class="grid grid--2">' +
          card("Why works are flagged", "Reason codes across all alerts \u00b7 select one to filter", '<div id="chart-reasons"></div>') +
          card("Districts needing attention", "Average risk score of alerts raised", '<div id="chart-top-districts"></div>', '<a class="btn btn--ghost btn--sm" href="#/districts">Risk map</a>') +
        "</section>";

      $("#chart-trend").appendChild(Charts.line(s.trend.map(function (t) { return { label: monthLabel(t.month), value: t.spent }; }), { format: inr }));
      $("#chart-donut").appendChild(Charts.donut(s.severity, { centerValue: k.alerts, centerLabel: "alerts" }));
      var sp = $("[data-spark]", view); if (sp) sp.appendChild(Charts.spark(s.trend.map(function (t) { return t.spent; })));
      $("#chart-reasons").appendChild(Charts.bars(s.reasons.slice(0, 7).map(function (r) {
        return { label: codeLabel(r.code), value: r.count, onClick: function () { goQueue({ code: r.code }); } };
      })));
      $("#chart-top-districts").appendChild(Charts.bars(s.districts.slice(0, 7).map(function (d) {
        return { label: d.district, value: d.avg_score, display: Math.round(d.avg_score) + " \u00b7 " + d.alerts + " alerts", tone: d.avg_score >= 55 ? "critical" : d.avg_score >= 45 ? "high" : "medium", onClick: function () { goQueue({ state: d.state, district: d.district }); } };
      }), { max: 100 }));
      bindCommon(view);
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  function monthLabel(m) { var d = new Date(m + "-01"); return isNaN(d) ? m : d.toLocaleDateString("en-IN", { month: "short" }) + " " + String(d.getFullYear()).slice(2); }
  function att(tone, icon, value, label, filters) {
    return "<button class=\"att\" data-q='" + esc(JSON.stringify(filters)) + "'><span class=\"att__icon att__icon--" + tone + '">' + svgIcon(icon) + "</span><div><strong>" + num(value) + "</strong><span>" + esc(label) + "</span></div></button>";
  }
  function kpi(label, value, sub, extra, spark) {
    return '<article class="card kpi"><div class="kpi__label">' + esc(label) + '</div><div class="kpi__value">' + value + '</div><div class="kpi__sub">' + sub + "</div>" + (extra || "") + (spark ? "<div data-spark></div>" : "") + "</article>";
  }
  function updateNavCounts(s) {
    $("#nav-alert-count").textContent = s.kpis.alerts || "";
    $("#nav-breach-count").textContent = s.sla && s.sla.breached ? s.sla.breached : "";
    var mini = $("#sla-mini");
    if (s.sla) mini.innerHTML = '<div class="sla-mini__top"><span class="muted">SLA compliance</span><strong>' + s.sla.compliance_pct + "%</strong></div>" +
      '<div class="meter" style="margin-top:0"><span style="width:' + s.sla.compliance_pct + "%;background:var(--" + (s.sla.compliance_pct >= 80 ? "ok" : s.sla.compliance_pct >= 60 ? "high" : "critical") + ')"></span></div>';
  }

  function alertTable(items, opts) {
    opts = opts || {};
    if (!items.length) return empty("No alerts match these filters", "Try widening the severity, SLA or jurisdiction filter.", ICONS.search);
    var sel = opts.selectable;
    return '<table class="responsive"><thead><tr>' +
      (sel ? '<th class="check"><input type="checkbox" id="check-all" aria-label="Select all" /></th>' : "") +
      "<th>Work</th><th>Risk</th><th>Top reason</th>" + (opts.compact ? "" : '<th class="num">Sanction</th>') + '<th class="num">Progress</th><th>Owner</th><th>SLA</th><th>Status</th><th></th>' +
      "</tr></thead><tbody>" +
      items.map(function (a, i) {
        return '<tr data-work="' + esc(a.work_id) + '" data-alert="' + a.id + '" data-index="' + i + '"' + (State.selected[a.id] ? ' class="is-selected"' : "") + ">" +
          (sel ? '<td class="check"><input type="checkbox" data-select="' + a.id + '"' + (State.selected[a.id] ? " checked" : "") + ' aria-label="Select" /></td>' : "") +
          '<td class="cell-main" data-label="Work"><div class="row">' + '<span class="sev-dot sev-' + esc(a.severity) + '-bg" title="' + esc(a.severity) + '"></span><strong class="truncate" style="max-width:420px">' + esc(a.work_name) + "</strong></div>" +
            '<div class="cell-sub"><span class="mono">' + esc(a.work_id) + "</span> \u00b7 " + esc(a.district) + ", " + esc(a.state) + "</div></td>" +
          '<td data-label="Risk">' + scoreCell(a.risk_score, a.severity) + "</td>" +
          '<td data-label="Top reason"><span class="tag tag--code">' + esc((a.reasons[0] || {}).code || "\u2014") + "</span>" + (a.reason_count > 1 ? ' <span class="tiny faint">+' + (a.reason_count - 1) + "</span>" : "") + "</td>" +
          (opts.compact ? "" : '<td class="num" data-label="Sanction">' + inr(a.sanction_amount) + "</td>") +
          '<td class="num" data-label="Progress">' + Number(a.physical_progress).toFixed(0) + "%</td>" +
          '<td data-label="Owner">' + avatar(a.assignee, a.assignee_name) + "</td>" +
          '<td data-label="SLA">' + slaChip(a.sla, a.sla_hours) + "</td>" +
          '<td data-label="Status">' + statusPill(a.status) + "</td>" +
          '<td data-label=""><button class="star' + (a.watching ? " is-on" : "") + '" data-star="' + esc(a.work_id) + '" title="Watch" aria-label="Watch">' + svgIcon(ICONS.star) + "</button></td>" +
          "</tr>";
      }).join("") + "</tbody></table>";
  }

  function bindCommon(root) {
    $$("tr[data-work], .list__item[data-work], .kcard[data-work]", root).forEach(function (row) {
      row.addEventListener("click", function (e) {
        if (e.target.closest("input, button, select, a")) return;
        openCase(row.dataset.work);
      });
    });
    $$("[data-star]", root).forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        api("/api/watchlist/toggle", { method: "POST", body: { work_id: b.dataset.star } }).then(function (r) {
          b.classList.toggle("is-on", r.watching);
          toast(r.watching ? "Added to your watchlist" : "Removed from watchlist", "success");
        });
      });
    });
    $$("[data-q]", root).forEach(function (b) { b.addEventListener("click", function () { goQueue(JSON.parse(b.dataset.q)); }); });
    $$("[data-go]", root).forEach(function (b) { b.addEventListener("click", function () { location.hash = "#/" + b.dataset.go; }); });
  }

  /* ----------------------------- alert queue ---------------------------- */
  function pill(key, label, values, current) {
    var isSet = current && current !== "all" && !(key === "sort");
    return '<label class="pill-select' + (isSet ? " is-set" : "") + '" title="' + esc(label) + '"><select data-filter="' + key + '" aria-label="' + esc(label) + '">' +
      values.map(function (v) {
        var val = Array.isArray(v) ? v[0] : v, text = Array.isArray(v) ? v[1] : (v === "all" ? label + ": All" : codeLabel(v));
        return '<option value="' + esc(val) + '"' + (String(val) === String(current) ? " selected" : "") + ">" + esc(text) + "</option>";
      }).join("") + "</select></label>";
  }

  function renderAlerts(view) {
    loading(view);
    Promise.all([loadOptions(), loadUsers(), api("/api/views")]).then(function (res) {
      var opts = res[0], users = res[1]; State.views = res[2].items;
      var f = State.filters;
      var districts = opts.districts.filter(function (d) { return f.state === "all" || d.state === f.state; });
      view.innerHTML =
        '<section class="card card--flush">' +
          '<div class="viewtabs" id="viewtabs">' +
            '<button class="viewtab' + (!State.activeView ? " is-active" : "") + '" data-view="">All alerts</button>' +
            State.views.map(function (v) {
              return '<button class="viewtab' + (State.activeView === v.id ? " is-active" : "") + '" data-view="' + v.id + '">' + esc(v.name) +
                (v.mine ? '<span class="x" data-del-view="' + v.id + '" title="Delete view">\u00d7</span>' : "") + "</button>";
            }).join("") +
            '<button class="viewtab" id="save-view" title="Save current filters as a view">+ Save view</button>' +
          "</div>" +
          '<div class="toolbar">' +
            '<div class="search-inline">' + svgIcon(ICONS.search) + '<input id="queue-search" type="search" placeholder="Search work, agency or MP" value="' + esc(f.q) + '" /></div>' +
            pill("severity", "Severity", ["all", "critical", "high", "medium", "low"], f.severity) +
            pill("status", "Status", ["all", ["open", "Open"], ["in_review", "In review"], ["actioned", "Escalated"], ["dismissed", "Closed"]], f.status) +
            pill("sla", "SLA", ["all", ["breached", "SLA breached"], ["due_soon", "Due in 72h"]], f.sla) +
            pill("assignee", "Owner", ["all", ["me", "Assigned to me"], ["none", "Unassigned"]].concat(users.map(function (u) { return [u.username, u.name]; })), f.assignee) +
            (opts.states.length > 1 ? pill("state", "State", ["all"].concat(opts.states.map(function (s) { return [s, s]; })), f.state) : "") +
            (districts.length > 1 ? pill("district", "District", ["all"].concat(districts.map(function (d) { return [d.district, d.district]; })), f.district) : "") +
            pill("category", "Category", ["all"].concat(opts.categories.map(function (c) { return [c, c]; })), f.category) +
            pill("code", "Reason", ["all"].concat(opts.reason_codes.map(function (r) { return [r.code, codeLabel(r.code)]; })), f.code) +
            '<span class="spacer"></span>' +
            pill("sort", "Sort", [["risk", "Sort: Risk score"], ["due", "Sort: SLA due"], ["amount", "Sort: Sanction"], ["progress", "Sort: Progress"], ["recent", "Sort: Newest"]], f.sort) +
            '<button class="btn btn--quiet btn--sm" id="reset-filters">Reset</button>' +
            '<button class="btn btn--ghost btn--sm" id="export-csv" title="Export the filtered queue as CSV">' + svgIcon(ICONS.download) + "Export</button>" +
          "</div>" +
          '<div id="alerts-table"><div class="skeleton skeleton--block" style="margin:14px"></div></div>' +
        "</section>" +
        '<p class="tiny faint">Tip: <kbd>j</kbd> <kbd>k</kbd> to move, <kbd>Enter</kbd> to open, <kbd>x</kbd> to select, <kbd>Ctrl K</kbd> to jump anywhere.</p>';

      $$("select[data-filter]", view).forEach(function (sel) {
        sel.addEventListener("change", function () {
          State.filters[sel.dataset.filter] = sel.value; State.filters.page = 1;
          if (sel.dataset.filter === "state") State.filters.district = "all";
          State.activeView = null; renderAlerts(view);
        });
      });
      var t; $("#queue-search").addEventListener("input", function (e) {
        clearTimeout(t); t = setTimeout(function () { State.filters.q = e.target.value; State.filters.page = 1; fetchAlerts(view); }, 280);
      });
      $("#reset-filters").addEventListener("click", function () { State.filters = Object.assign({}, DEFAULT_FILTERS); State.activeView = null; renderAlerts(view); });
      $("#export-csv").addEventListener("click", exportCsv);
      $$("[data-view]", view).forEach(function (b) {
        b.addEventListener("click", function (e) {
          if (e.target.dataset.delView) {
            api("/api/views/" + e.target.dataset.delView + "/delete", { method: "POST" }).then(function () { State.activeView = null; toast("View deleted"); renderAlerts(view); });
            return;
          }
          var v = State.views.filter(function (x) { return String(x.id) === b.dataset.view; })[0];
          State.filters = Object.assign({}, DEFAULT_FILTERS, v ? v.filters : {});
          State.activeView = v ? v.id : null; renderAlerts(view);
        });
      });
      $("#save-view").addEventListener("click", saveViewDialog);
      fetchAlerts(view);
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  function queryString(f, extra) {
    var q = Object.assign({}, f, extra || {});
    return Object.keys(q).filter(function (k) { return q[k] !== "" && q[k] != null; }).map(function (k) { return k + "=" + encodeURIComponent(q[k]); }).join("&");
  }

  function fetchAlerts(view) {
    api("/api/alerts?" + queryString(State.filters)).then(function (data) {
      var host = $("#alerts-table", view); if (!host) return;
      State.lastItems = data.items; State.focusRow = -1;
      var pages = Math.max(1, Math.ceil(data.total / data.limit));
      host.innerHTML = '<div class="table-wrap">' + alertTable(data.items, { selectable: true }) + "</div>" +
        '<div class="pagination"><span class="tiny muted">' + num(data.total) + " alerts \u00b7 page " + data.page + " of " + pages + "</span>" +
        '<span class="row"><button class="btn btn--ghost btn--sm" id="prev-page"' + (data.page <= 1 ? " disabled" : "") + '>Previous</button><button class="btn btn--ghost btn--sm" id="next-page"' + (data.page >= pages ? " disabled" : "") + ">Next</button></span></div>";
      var prev = $("#prev-page", host), next = $("#next-page", host);
      prev.addEventListener("click", function () { State.filters.page--; fetchAlerts(view); });
      next.addEventListener("click", function () { State.filters.page++; fetchAlerts(view); });
      $$("[data-select]", host).forEach(function (c) {
        c.addEventListener("change", function () { toggleSelect(+c.dataset.select, c.checked); });
      });
      var all = $("#check-all", host);
      if (all) all.addEventListener("change", function () { data.items.forEach(function (a) { toggleSelect(a.id, all.checked); }); $$("[data-select]", host).forEach(function (c) { c.checked = all.checked; }); });
      bindCommon(host);
    }).catch(function (err) { var h = $("#alerts-table", view); if (h) h.innerHTML = errorCard(err); });
  }

  function toggleSelect(id, on) {
    if (on) State.selected[id] = true; else delete State.selected[id];
    var row = $('tr[data-alert="' + id + '"]'); if (row) row.classList.toggle("is-selected", !!on);
    renderBulkbar();
  }

  function renderBulkbar() {
    var ids = Object.keys(State.selected), bar = $("#bulkbar");
    if (!ids.length) { bar.hidden = true; return; }
    bar.hidden = false;
    bar.innerHTML = "<strong>" + ids.length + " selected</strong>" +
      '<select id="bulk-assign"><option value="">Assign to\u2026</option>' + (State.users || []).map(function (u) { return '<option value="' + esc(u.username) + '">' + esc(u.name) + "</option>"; }).join("") + "</select>" +
      '<button class="btn btn--sm" data-bulk="in_review">Mark in review</button>' +
      '<button class="btn btn--sm" data-bulk="actioned">Escalate</button>' +
      '<button class="btn btn--sm" data-bulk="dismissed">Close</button>' +
      '<button class="btn btn--sm" id="bulk-clear" title="Clear selection">' + svgIcon(ICONS.close) + "</button>";
    function run(body, label) {
      body.ids = Object.keys(State.selected).map(Number);
      api("/api/alerts/bulk", { method: "POST", body: body }).then(function (r) {
        toast(label + " \u00b7 " + r.updated + " cases updated", "success");
        State.selected = {}; renderBulkbar(); router();
      }).catch(function (e) { toast(e.message, "error"); });
    }
    $("#bulk-assign").addEventListener("change", function (e) { if (e.target.value) run({ assignee: e.target.value }, "Assigned"); });
    $$("[data-bulk]", bar).forEach(function (b) { b.addEventListener("click", function () { run({ status: b.dataset.bulk }, statusLabel(b.dataset.bulk)); }); });
    $("#bulk-clear").addEventListener("click", function () { State.selected = {}; renderBulkbar(); $$("[data-select]").forEach(function (c) { c.checked = false; }); $$("tr.is-selected").forEach(function (r) { r.classList.remove("is-selected"); }); });
  }

  function exportCsv() {
    api("/api/alerts?" + queryString(State.filters, { page: 1, limit: 1000 })).then(function (data) {
      var cols = ["work_id", "work_name", "state", "district", "category", "agency", "mp_name", "risk_score", "severity", "status", "assignee", "due_at", "sla", "sanction_amount", "expenditure", "physical_progress", "top_reason"];
      var lines = [cols.join(",")].concat(data.items.map(function (a) {
        a.top_reason = (a.reasons[0] || {}).code || "";
        return cols.map(function (c) { var v = a[c] == null ? "" : String(a[c]); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(",");
      }));
      var blob = new Blob([lines.join("\n")], { type: "text/csv" });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob); link.download = "drishti-alerts-" + new Date().toISOString().slice(0, 10) + ".csv";
      document.body.appendChild(link); link.click(); link.remove();
      toast("Exported " + data.items.length + " alerts", "success");
    }).catch(function (e) { toast(e.message, "error"); });
  }

  function saveViewDialog() {
    openModal('<h3>Save this view</h3><p class="muted small">Saves the current filters and sort as a tab in the alert queue.</p>' +
      '<label class="field"><span>Name</span><input id="view-name" placeholder="e.g. Pune roads over 50 lakh" maxlength="60" /></label>' +
      '<label class="row small"><input type="checkbox" id="view-shared" /> Share with everyone in the workspace</label>' +
      '<div class="row" style="justify-content:flex-end"><button class="btn btn--quiet" data-close-modal>Cancel</button><button class="btn btn--primary" id="view-save">Save view</button></div>');
    $("#view-name").focus();
    $("#view-save").addEventListener("click", function () {
      var f = Object.assign({}, State.filters); delete f.page; delete f.limit;
      Object.keys(f).forEach(function (k) { if (f[k] === "all" || f[k] === "") delete f[k]; });
      api("/api/views", { method: "POST", body: { name: $("#view-name").value, filters: f, shared: $("#view-shared").checked } }).then(function (d) {
        State.views = d.items; State.activeView = d.items[d.items.length - 1].id;
        closeModals(); toast("View saved", "success"); router();
      }).catch(function (e) { toast(e.message, "error"); });
    });
  }

  /* ----------------------------- board ---------------------------------- */
  var BOARD_COLS = [["open", "Open"], ["in_review", "In review"], ["actioned", "Escalated"], ["dismissed", "Closed"]];

  function kcard(a) {
    return '<article class="kcard" draggable="true" data-work="' + esc(a.work_id) + '" data-id="' + a.id + '">' +
      '<div class="kcard__top">' + sevBadge(a.severity) + '<span class="tag tag--code">' + esc(a.top_reason || "") + '</span><span class="kcard__score">' + Number(a.risk_score).toFixed(0) + "</span></div>" +
      '<div class="kcard__title">' + esc(a.work_name) + "</div>" +
      '<div class="kcard__foot">' + avatar(a.assignee, a.assignee_name) + '<span class="truncate">' + esc(a.district) + "</span>" +
      slaChip(a.sla, a.sla_hours) +
      (a.comments ? '<span class="tiny faint">' + svgIcon(ICONS.chat).replace("icon", "icon icon--sm") + a.comments + "</span>" : "") + "</div></article>";
  }

  function renderBoard(view) {
    loading(view);
    api("/api/board").then(function (b) {
      view.innerHTML = '<p class="muted small">Drag a card between columns to change its status. Click a card to open the case.</p><div class="board">' +
        BOARD_COLS.map(function (c) {
          var items = b.columns[c[0]] || [];
          return '<section class="col" data-col="' + c[0] + '"><div class="col__head">' + statusPill(c[0]) + '<span class="count">' + (b.totals[c[0]] || 0) + "</span></div>" +
            '<div class="col__body">' + (items.length ? items.map(kcard).join("") : '<div class="tiny faint" style="padding:10px">Nothing here</div>') +
            (b.totals[c[0]] > items.length ? '<div class="col__more">Showing top ' + items.length + " of " + b.totals[c[0]] + "</div>" : "") + "</div></section>";
        }).join("") + "</div>";
      bindCommon(view);
      var dragging = null;
      $$(".kcard", view).forEach(function (k) {
        k.addEventListener("dragstart", function (e) { dragging = k; k.classList.add("is-dragging"); e.dataTransfer.effectAllowed = "move"; try { e.dataTransfer.setData("text/plain", k.dataset.id); } catch (x) {} });
        k.addEventListener("dragend", function () { k.classList.remove("is-dragging"); $$(".col", view).forEach(function (c) { c.classList.remove("is-over"); }); });
      });
      $$(".col", view).forEach(function (col) {
        col.addEventListener("dragover", function (e) { e.preventDefault(); col.classList.add("is-over"); });
        col.addEventListener("dragleave", function () { col.classList.remove("is-over"); });
        col.addEventListener("drop", function (e) {
          e.preventDefault(); col.classList.remove("is-over");
          if (!dragging) return;
          var id = dragging.dataset.id, target = col.dataset.col;
          api("/api/alerts/" + id + "/status", { method: "POST", body: { status: target, note: "Moved on case board" } })
            .then(function () { toast("Moved to " + statusLabel(target), "success"); renderBoard(view); })
            .catch(function (er) { toast(er.message, "error"); });
        });
      });
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  /* ----------------------------- risk map ------------------------------- */
  function renderDistricts(view) {
    loading(view);
    api("/api/summary").then(function (s) {
      view.innerHTML =
        card("District risk heat map", "Average risk score of alerts in each district. Click a district to open its alerts.", '<div id="heat"></div>') +
        '<div class="grid grid--2">' +
        card("Alert volume by district", "Number of works needing review", '<div id="chart-district-volume"></div>') +
        card("Exposure by district", "Sanction value behind flagged works", '<div id="chart-district-exposure"></div>') + "</div>";
      $("#heat").appendChild(Charts.heatGrid(s.districts.map(function (d) {
        return { label: d.district, state: d.state, value: d.avg_score, display: Number(d.avg_score).toFixed(0), sub: d.alerts + " alerts \u00b7 " + inr(d.exposure), raw: d };
      }), function (c) { goQueue({ state: c.raw.state, district: c.raw.district }); }));
      $("#chart-district-volume").appendChild(Charts.bars(s.districts.slice(0, 8).map(function (d) {
        return { label: d.district, value: d.alerts, display: d.alerts, onClick: function () { goQueue({ state: d.state, district: d.district }); } };
      })));
      $("#chart-district-exposure").appendChild(Charts.bars(s.districts.slice().sort(function (a, b) { return b.exposure - a.exposure; }).slice(0, 8).map(function (d) {
        return { label: d.district, value: d.exposure, display: inr(d.exposure), tone: "high", onClick: function () { goQueue({ state: d.state, district: d.district }); } };
      })));
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  /* ----------------------------- watchlist ------------------------------ */
  function renderWatchlist(view) {
    loading(view);
    api("/api/watchlist").then(function (d) {
      var items = d.items;
      if (!items.length) { view.innerHTML = '<div class="card">' + empty("Your watchlist is empty", "Click the star next to any work in the queue to follow it. You will be notified about comments and status changes.", ICONS.star) + "</div>"; return; }
      view.innerHTML = '<div class="card card--flush"><table class="responsive"><thead><tr><th>Work</th><th>Risk</th><th class="num">Sanction</th><th class="num">Progress</th><th>SLA</th><th>Status</th><th>Followed</th><th></th></tr></thead><tbody>' +
        items.map(function (w) {
          return '<tr data-work="' + esc(w.work_id) + '"><td class="cell-main" data-label="Work"><strong>' + esc(w.work_name) + '</strong><div class="cell-sub"><span class="mono">' + esc(w.work_id) + "</span> \u00b7 " + esc(w.district) + ", " + esc(w.state) + "</div></td>" +
            '<td data-label="Risk">' + (w.risk_score != null ? scoreCell(w.risk_score, w.severity) : '<span class="faint">No alert</span>') + "</td>" +
            '<td class="num" data-label="Sanction">' + inr(w.sanction_amount) + '</td><td class="num" data-label="Progress">' + Number(w.physical_progress).toFixed(0) + "%</td>" +
            '<td data-label="SLA">' + (w.sla ? slaChip(w.sla, w.sla_hours) : "\u2014") + '</td><td data-label="Status">' + (w.status ? statusPill(w.status) : "\u2014") + "</td>" +
            '<td class="tiny muted" data-label="Followed">' + ago(w.watched_at) + '</td><td><button class="star is-on" data-star="' + esc(w.work_id) + '" aria-label="Unwatch">' + svgIcon(ICONS.star) + "</button></td></tr>";
        }).join("") + "</tbody></table></div>";
      bindCommon(view);
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  /* ----------------------------- scorecards ----------------------------- */
  function renderScorecards(view) {
    var by = State.scoreBy || "agency";
    view.innerHTML = '<div class="row" style="justify-content:space-between;flex-wrap:wrap"><div class="seg" id="score-seg">' +
      [["agency", "Agencies"], ["mp", "MPs"], ["district", "Districts"]].map(function (t) { return '<button data-by="' + t[0] + '" class="' + (by === t[0] ? "is-active" : "") + '">' + t[1] + "</button>"; }).join("") +
      '</div><span class="muted small">Risk index blends alert rate, severity, overruns and stalled works. Lower is better.</span></div><div id="score-body"></div>';
    $$("#score-seg button", view).forEach(function (b) { b.addEventListener("click", function () { State.scoreBy = b.dataset.by; renderScorecards(view); }); });
    var host = $("#score-body", view); loading(host);
    api("/api/scorecards?by=" + by).then(function (d) {
      var items = d.items.slice().sort(function (a, b) { return b.risk_index - a.risk_index; });
      host.innerHTML = '<div class="card card--flush" style="margin-top:12px"><table class="responsive"><thead><tr><th>Grade</th><th>' + (by === "mp" ? "MP" : by === "district" ? "District" : "Agency") + '</th><th class="num">Works</th><th class="num">Sanctioned</th><th class="num">Utilisation</th><th class="num">Alerts</th><th class="num">Resolved</th><th>Risk index</th></tr></thead><tbody>' +
        items.slice(0, 60).map(function (r) {
          return '<tr class="clickable" data-entity="' + esc(r.entity) + '"><td data-label="Grade"><span class="grade grade--' + r.grade + '">' + r.grade + "</span></td>" +
            '<td class="cell-main" data-label="Name"><strong>' + esc(r.entity) + "</strong>" + (r.state ? '<div class="cell-sub">' + esc(r.state) + (r.house ? " \u00b7 " + esc(r.house) : "") + "</div>" : "") + "</td>" +
            '<td class="num" data-label="Works">' + r.works + '</td><td class="num" data-label="Sanctioned">' + inr(r.sanctioned) + '</td><td class="num" data-label="Utilisation">' + pct(r.utilisation) + "</td>" +
            '<td class="num" data-label="Alerts">' + r.alerts + ' <span class="tiny faint">(' + pct(r.alert_rate) + ')</span></td><td class="num" data-label="Resolved">' + pct(r.resolution_rate) + "</td>" +
            '<td data-label="Risk index"><span class="score">' + Number(r.risk_index).toFixed(0) + '<span class="score__bar"><span class="' + (r.risk_index >= d.portfolio_avg * 1.5 ? "sev-high-bg" : "sev-low-bg") + '" style="width:' + Math.min(100, r.risk_index) + '%"></span></span></span></td></tr>';
        }).join("") + '</tbody></table></div><p class="tiny muted" style="margin-top:8px">Portfolio average risk index: ' + Number(d.portfolio_avg).toFixed(1) + ". Click a row to filter the alert queue.</p>";
      $$("tr[data-entity]", host).forEach(function (tr) {
        tr.addEventListener("click", function () {
          var e = tr.dataset.entity;
          goQueue(by === "district" ? { q: e } : { q: e });
        });
      });
    }).catch(function (err) { host.innerHTML = errorCard(err); });
  }

  /* ----------------------------- analytics ------------------------------ */
  function renderAnalytics(view) {
    loading(view);
    Promise.all([api("/api/summary"), api("/api/actions")]).then(function (res) {
      var s = res[0], actions = res[1].items, k = s.kpis;
      view.innerHTML =
        '<section class="grid grid--kpi">' +
        kpi("Screening coverage", k.coverage + "%", "Every work scored on each run") +
        kpi("Data completeness", k.avg_completeness + "%", "Higher completeness means higher confidence") +
        kpi("Officer feedback", k.feedback_count ? k.feedback_useful_pct + "%" : "\u2014", k.feedback_count ? "rated useful across " + num(k.feedback_count) + " responses" : "No feedback yet") +
        kpi("Avg physical progress", k.avg_progress + "%", "Across all monitored works") + "</section>" +
        '<section class="grid grid--2">' +
        card("Detection mix", "How often each reason code fires", '<div id="chart-mix"></div>') +
        card("Alerts by category", "Where risk concentrates by work type", '<div id="chart-cat"></div>') + "</section>" +
        '<section class="grid grid--2">' +
        card("Works sanctioned per month", "Pipeline entering the monitoring system", '<div id="chart-works"></div>') +
        card("Recent officer actions", "Closing the loop on alerts",
          actions.length ? '<div class="list">' + actions.slice(0, 8).map(function (a) {
            return '<div class="list__item" data-work="' + esc(a.work_id) + '"><span class="tag">' + esc(String(a.action).replace(/_/g, " ")) + '</span><span class="grow truncate">' + esc(a.work_name) + '</span><span class="tiny muted">' + ago(a.created_at) + "</span></div>";
          }).join("") + "</div>" : empty("No actions recorded yet", "Open an alert and record a decision.")) + "</section>";
      $("#chart-mix").appendChild(Charts.bars(s.reasons.map(function (r) { return { label: codeLabel(r.code), value: r.count, display: r.count, onClick: function () { goQueue({ code: r.code }); } }; })));
      $("#chart-cat").appendChild(Charts.bars(s.categories.map(function (c) { return { label: c.category, value: c.alerts, display: c.alerts + " \u00b7 avg " + Number(c.avg_score).toFixed(0), tone: c.avg_score > 60 ? "critical" : "medium", onClick: function () { goQueue({ category: c.category }); } }; })));
      $("#chart-works").appendChild(Charts.line(s.trend.map(function (t) { return { label: monthLabel(t.month), value: t.works }; })));
      bindCommon(view);
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  /* ----------------------------- data quality --------------------------- */
  function renderQuality(view) {
    loading(view);
    Promise.all([api("/api/summary"), api("/api/data-quality")]).then(function (res) {
      var q = res[0].quality, items = res[1].items;
      view.innerHTML =
        '<section class="grid grid--kpi">' + kpi("Good records", num(q.good), "85%+ of key fields present") + kpi("Fair records", num(q.fair), "Scored, verify before acting") +
        kpi("Weak records", num(q.poor), "Score damped, flagged for correction") + kpi("Overdue works", num(q.overdue), "Past expected completion and still open") + "</section>" +
        card("Why this matters", "", '<p class="muted">DRISHTI never hides poor data behind a confident number. Where completeness is low the score is damped, the alert carries a <code>LOW_DATA_QUALITY</code> reason, and the record appears here so the district can fix the source entry.</p>') +
        '<div class="card card--flush"><div class="card__head" style="padding:16px 16px 0"><div><h3>Records needing correction</h3><p>Lowest completeness first</p></div></div><table class="responsive"><thead><tr><th>Work</th><th>District</th><th class="num">Completeness</th><th class="num">Sanction</th><th class="num">Progress</th></tr></thead><tbody>' +
        (items.length ? items.map(function (w) {
          return '<tr data-work="' + esc(w.work_id) + '"><td class="cell-main" data-label="Work"><strong>' + esc(w.work_name) + '</strong><div class="cell-sub mono">' + esc(w.work_id) + "</div></td><td data-label=\"District\">" + esc(w.district) + ", " + esc(w.state) + '</td><td class="num" data-label="Completeness">' + Math.round(w.completeness * 100) + '%</td><td class="num" data-label="Sanction">' + inr(w.sanction_amount) + '</td><td class="num" data-label="Progress">' + Number(w.physical_progress).toFixed(0) + "%</td></tr>";
        }).join("") : '<tr><td colspan="5">' + empty("All records are complete") + "</td></tr>") + "</tbody></table></div>";
      bindCommon(view);
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  /* ----------------------------- audit ---------------------------------- */
  function renderAudit(view) {
    loading(view);
    api("/api/audit").then(function (d) {
      view.innerHTML = '<div class="card card--flush"><div class="card__head" style="padding:16px 16px 0"><div><h3>Audit trail</h3><p>Log of every login, decision, assignment and policy change</p></div></div><table class="responsive"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead><tbody>' +
        (d.items.length ? d.items.map(function (r) {
          return '<tr><td data-label="Time">' + esc(new Date(r.ts).toLocaleString("en-IN")) + '</td><td data-label="User"><span class="tag">' + esc(r.username) + '</span></td><td data-label="Action" class="mono tiny">' + esc(r.action) + '</td><td data-label="Entity" class="mono tiny">' + esc(r.entity || "\u2014") + '</td><td data-label="Detail">' + esc(r.detail || "\u2014") + "</td></tr>";
        }).join("") : '<tr><td colspan="5">' + empty("No audit entries yet") + "</td></tr>") + "</tbody></table></div>";
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  /* ----------------------------- about ---------------------------------- */
  function renderAbout(view) {
    view.innerHTML =
      '<div class="grid grid--2"><div class="card prose"><h3>What DRISHTI does</h3><p>DRISHTI screens every MPLADS work against the funds released, physical progress and timelines recorded for it, and ranks the works that most need an officer\u2019s attention. Scores are risk signals for human review, never findings of wrongdoing.</p>' +
      "<p><strong>Problem statement:</strong> PS 26102 \u00b7 Smart India Hackathon 2026 \u00b7 MoSPI (DIID).</p></div>" +
      '<div class="card prose"><h3>Three detection layers</h3><ul><li><strong>Rules:</strong> cost overrun, payment without progress, stalled work, schedule overrun, spending bursts, rapid completion.</li><li><strong>Statistics:</strong> cost outliers against category peers and duplicate-work matching.</li><li><strong>Machine learning:</strong> an isolation-style anomaly score across the portfolio.</li></ul></div></div>' +
      '<div class="grid grid--2"><div class="card prose"><h3>Explainable by design</h3><p>Every alert lists the reason codes that fired, their contribution to the score, the evidence behind them, and a data-completeness confidence. Low-quality records are damped rather than hidden.</p></div>' +
      '<div class="card prose"><h3>Closing the loop</h3><p>Alerts flow through assignment, SLA-timed review, discussion and closure. Officer feedback and the audit trail record every decision, and ministry users can tune and version the detection policy.</p></div></div>' +
      '<p class="tiny muted">Developed by TEAM SYNTRIX</p>';
  }

  /* ----------------------------- policy studio -------------------------- */
  function renderPolicy(view) {
    loading(view);
    api("/api/policy").then(function (p) {
      var canPublish = State.user && State.user.role === "ministry";
      var draft = JSON.parse(JSON.stringify(p.active));
      var lastSim = null;
      view.innerHTML = '<div class="grid grid--policy"><div><section class="card"><div class="card__head"><div><h3>Reason weights</h3><p>Points each signal adds to the risk score (0\u201360)</p></div><button class="btn btn--quiet btn--sm" id="pol-reset">Reset to defaults</button></div>' +
        p.rules.map(function (r) {
          return '<div class="slider"><div class="slider__top"><span>' + esc(codeLabel(r.code)) + '</span><span class="val" data-val="w:' + r.code + '"></span></div><input type="range" min="0" max="60" step="1" data-w="' + r.code + '" /><small>' + esc(r.label) + "</small></div>";
        }).join("") + "</section>" +
        '<section class="card" style="margin-top:14px"><div class="card__head"><div><h3>Severity thresholds</h3><p>Minimum score for each band</p></div></div>' +
        [["critical", "Critical"], ["high", "High"], ["medium", "Medium"]].map(function (t) {
          return '<div class="slider"><div class="slider__top"><span>' + t[1] + '</span><span class="val" data-val="t:' + t[0] + '"></span></div><input type="range" min="5" max="95" step="1" data-t="' + t[0] + '" /></div>';
        }).join("") + "</section>" +
        '<section class="card" style="margin-top:14px"><div class="card__head"><div><h3>SLA (days to resolve)</h3><p>Deadline from alert creation</p></div></div>' +
        ["critical", "high", "medium", "low"].map(function (b) {
          return '<div class="slider"><div class="slider__top"><span style="text-transform:capitalize">' + b + '</span><span class="val" data-val="s:' + b + '"></span></div><input type="range" min="1" max="90" step="1" data-s="' + b + '" /></div>';
        }).join("") + "</section></div>" +
        '<div><section class="card"><div class="card__head"><div><h3>Impact preview</h3><p>What changes if this policy goes live</p></div><span class="muted small" id="pol-status"></span></div><div id="pol-sim"></div></section>' +
        '<section class="card" style="margin-top:14px"><div class="card__head"><div><h3>Publish</h3><p>Rescores every alert and notifies all users</p></div></div>' +
        (canPublish ? '<label class="field"><span>Change note</span><input id="pol-note" maxlength="200" placeholder="Why is this changing?" /></label><div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn btn--primary" id="pol-publish">Publish policy</button></div>' : '<p class="muted small">Only ministry users can publish. You can still simulate changes here.</p>') + "</section>" +
        '<section class="card" style="margin-top:14px"><div class="card__head"><div><h3>Version history</h3></div></div><div id="pol-versions"></div></section></div></div>';

      function paintVersions(versions) {
        $("#pol-versions").innerHTML = versions.length ? '<div class="list">' + versions.map(function (v) {
          return '<div class="list__item"><strong>v' + v.id + '</strong><span class="grow truncate">' + esc(v.note) + '</span><span class="tiny muted">' + esc(v.username) + " \u00b7 " + ago(v.created_at) + "</span></div>";
        }).join("") + "</div>" : '<p class="muted small">No policy versions yet. The built-in defaults are active.</p>';
      }
      paintVersions(p.versions);

      function sync() {
        $$("[data-w]", view).forEach(function (i) { i.value = draft.weights[i.dataset.w]; var v = $('[data-val="w:' + i.dataset.w + '"]', view); v.textContent = draft.weights[i.dataset.w]; v.classList.toggle("is-changed", draft.weights[i.dataset.w] !== p.defaults.weights[i.dataset.w]); });
        $$("[data-t]", view).forEach(function (i) { i.value = draft.thresholds[i.dataset.t]; var v = $('[data-val="t:' + i.dataset.t + '"]', view); v.textContent = draft.thresholds[i.dataset.t]; v.classList.toggle("is-changed", draft.thresholds[i.dataset.t] !== p.defaults.thresholds[i.dataset.t]); });
        $$("[data-s]", view).forEach(function (i) { i.value = draft.sla_days[i.dataset.s]; var v = $('[data-val="s:' + i.dataset.s + '"]', view); v.textContent = draft.sla_days[i.dataset.s] + "d"; v.classList.toggle("is-changed", draft.sla_days[i.dataset.s] !== p.defaults.sla_days[i.dataset.s]); });
      }
      function delta(n, invert) { if (!n) return '<span class="delta delta--flat">0</span>'; return '<span class="delta delta--' + (n > 0 ? "up" : "down") + '">' + (n > 0 ? "\u25b2" : "\u25bc") + Math.abs(n) + "</span>"; }
      function paint(sim) {
        lastSim = sim;
        var sevs = ["critical", "high", "medium", "low"];
        $("#pol-sim").innerHTML =
          '<div class="compare">' + sevs.map(function (s) { return "<div><span>" + s + " " + delta(sim.after[s] - sim.before[s]) + "</span><strong>" + sim.after[s] + '</strong><span class="tiny">was ' + sim.before[s] + "</span></div>"; }).join("") + "</div>" +
          '<p class="small" style="margin:12px 0"><strong>' + sim.changed + "</strong> of " + sim.total + " alerts change severity. Exposure in flagged works: " + inr(sim.exposure_before) + " \u2192 <strong>" + inr(sim.exposure_after) + "</strong>.</p>" +
          '<h4 class="small muted" style="margin:10px 0 6px">Severity transitions (rows: today, columns: proposed)</h4><div class="matrix"><div class="mh"></div>' + sevs.map(function (s) { return '<div class="mh">' + s + "</div>"; }).join("") +
          sevs.map(function (r) {
            return '<div class="mh">' + r + "</div>" + sevs.map(function (c) {
              var cls = r === c ? "is-diag" : sevs.indexOf(c) < sevs.indexOf(r) && sim.matrix[r][c] ? "is-up" : sim.matrix[r][c] ? "is-down" : "";
              return '<div class="mc ' + cls + '">' + sim.matrix[r][c] + "</div>";
            }).join("");
          }).join("") + "</div>" +
          (sim.movers && sim.movers.length ? '<h4 class="small muted" style="margin:14px 0 6px">Biggest movers</h4><div class="list">' + sim.movers.slice(0, 6).map(function (m) {
            return '<div class="list__item" data-work="' + esc(m.work_id) + '"><span class="grow truncate">' + esc(m.work_name || m.work_id) + "</span>" + sevBadge(m.before) + "<span>\u2192</span>" + sevBadge(m.after) + "</div>";
          }).join("") + "</div>" : "");
        bindCommon($("#pol-sim"));
        $("#pol-status").textContent = "";
      }
      var timer;
      function simulate() {
        clearTimeout(timer); $("#pol-status").textContent = "Simulating\u2026";
        timer = setTimeout(function () {
          api("/api/policy/simulate", { method: "POST", body: draft }).then(paint).catch(function (e) { $("#pol-status").textContent = e.message; });
        }, 250);
      }
      $$("input[type=range]", view).forEach(function (i) {
        i.addEventListener("input", function () {
          var v = Number(i.value);
          if (i.dataset.w) draft.weights[i.dataset.w] = v; else if (i.dataset.t) draft.thresholds[i.dataset.t] = v; else draft.sla_days[i.dataset.s] = v;
          sync(); simulate();
        });
      });
      $("#pol-reset").addEventListener("click", function () { draft = JSON.parse(JSON.stringify(p.defaults)); sync(); simulate(); });
      var pub = $("#pol-publish");
      if (pub) pub.addEventListener("click", function () {
        var body = Object.assign({}, draft, { note: $("#pol-note").value });
        pub.disabled = true;
        api("/api/policy/publish", { method: "POST", body: body }).then(function (np) {
          p = np; draft = JSON.parse(JSON.stringify(np.active)); paintVersions(np.versions); sync(); simulate();
          $("#pol-note").value = ""; State.options = null; toast("Policy published. Alerts rescored.", "success"); refreshNotifications();
        }).catch(function (e) { toast(e.message, "error"); }).then(function () { pub.disabled = false; });
      });
      sync(); simulate();
    }).catch(function (err) { view.innerHTML = errorCard(err); });
  }

  /* ----------------------------- modal / drawer ------------------------- */
  function openModal(html) { $("#modal-body").innerHTML = html; $("#modal").hidden = false; }
  function closeModals() { $("#modal").hidden = true; $("#palette").hidden = true; }
  function closeDrawer() { $("#case-drawer").hidden = true; $("#case-body").innerHTML = ""; document.body.classList.remove("no-scroll"); State.openWork = null; }

  function mentionize(text) {
    return esc(text).replace(/@([a-z0-9._]+)/gi, '<span class="mention">@$1</span>');
  }

  function openCase(workId, tab) {
    State.openWork = workId; State.caseTab = tab || "overview";
    $("#case-drawer").hidden = false; document.body.classList.add("no-scroll");
    $("#case-body").innerHTML = '<div class="case"><div class="skeleton skeleton--row" style="width:60%"></div><div class="skeleton skeleton--row"></div><div class="skeleton skeleton--row"></div></div>';
    Promise.all([api("/api/works/" + encodeURIComponent(workId)), loadUsers()]).then(function (res) {
      if (State.openWork !== workId) return;
      paintCase(res[0]);
    }).catch(function (e) { $("#case-body").innerHTML = '<div class="case">' + errorCard(e) + "</div>"; });
  }

  function briefText(w, a) {
    var top = a.reason_codes[0];
    var parts = ["<b>" + esc(w.work_name) + "</b> in " + esc(w.district) + " (" + esc(w.agency) + ") is rated <b>" + esc(a.severity) + "</b> at " + Number(a.risk_score).toFixed(0) + "/100"];
    var e = a.evidence || {};
    parts.push(": " + inr(e.expenditure) + " spent against a sanction of " + inr(e.sanction_amount) + " (" + Number(e.utilisation_pct || 0).toFixed(0) + "% used) with " + Number(e.physical_progress || 0).toFixed(0) + "% physical progress.");
    if (top) parts.push(" Main concern: " + esc(top.label || codeLabel(top.code)) + ".");
    return parts.join("");
  }

  function paintCase(d) {
    var w = d.work, a = d.alert, canAct = !!a;
    var body = $("#case-body");
    var reasons = a ? a.reason_codes : [];
    var totalContribution = reasons.reduce(function (s, r) { return s + Number(r.contribution || r.impact || 0); }, 0) || 1;
    var next = reasons.length ? (REASON_NEXT[reasons[0].code] || "Review the evidence and record a decision.") : "";
    var users = State.users || [];
    var e = a ? a.evidence : {};
    var html = '<div class="case__bar"><div class="case__crumb"><span class="mono">' + esc(w.work_id) + "</span></div><span class=\"spacer\"></span>" +
      '<button class="btn btn--ghost btn--sm' + (d.watching ? " is-on" : "") + '" id="c-watch">' + svgIcon(ICONS.star) + '<span>' + (d.watching ? "Watching" : "Watch") + "</span></button>" +
      '<button class="btn btn--ghost btn--sm" id="c-memo">' + svgIcon(ICONS.print) + "<span>Inspection memo</span></button>" +
      '<button class="icon-btn icon-btn--ghost" data-close-drawer aria-label="Close">' + svgIcon(ICONS.close) + "</button></div>" +
      '<div class="case"><div class="case__title"><h2>' + esc(w.work_name) + '</h2><div class="case__meta">' +
      (a ? sevBadge(a.severity) + statusPill(a.status) + slaChip(a.sla, a.sla_hours) : '<span class="badge badge--ok">No active alert</span>') +
      '<span class="tag">' + esc(w.category) + '</span><span class="tag">' + esc(w.district) + ", " + esc(w.state) + '</span><span class="tag">' + esc(w.mp_name) + "</span></div></div>";
    if (a) {
      html += '<div class="brief"><div>' + svgIcon(ICONS.sparkle) + '</div><div><div class="brief__label">Auto case brief</div><div class="brief__text">' + briefText(w, a) + "</div>" +
        (next ? '<div class="brief__text" style="margin-top:6px"><b>Suggested next step:</b> ' + esc(next) + "</div>" : "") + "</div></div>";
      html += '<div style="display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center"><div class="props">' +
        "<span>Assignee</span><div><select id=\"c-assignee\"><option value=\"\">Unassigned</option>" + users.map(function (u) { return '<option value="' + esc(u.username) + '"' + (u.username === a.assignee ? " selected" : "") + ">" + esc(u.name) + "</option>"; }).join("") + "</select></div>" +
        "<span>Status</span><div><select id=\"c-status\">" + [["open", "Open"], ["in_review", "In review"], ["actioned", "Escalated"], ["dismissed", "Closed"]].map(function (s) { return '<option value="' + s[0] + '"' + (s[0] === a.status ? " selected" : "") + ">" + s[1] + "</option>"; }).join("") + "</select></div>" +
        "<span>SLA due</span><div>" + dateFmt(a.due_at) + " " + slaChip(a.sla, a.sla_hours) + "</div>" +
        "<span>Confidence</span><div>" + Math.round((a.confidence || 0) * 100) + "% data completeness</div>" +
        "<span>Raised</span><div>" + ago(a.created_at) + '</div></div><div style="justify-self:center" id="c-gauge"></div></div>';
    }
    html += '<div class="tabs" id="c-tabs">' + [["overview", "Overview"], ["timeline", "Timeline"], ["discussion", "Discussion", d.comments.length], ["activity", "Activity", a ? a.actions.length : 0]].map(function (t) {
      return '<button class="tab' + (State.caseTab === t[0] ? " is-active" : "") + '" data-tab="' + t[0] + '">' + t[1] + (t[2] ? ' <span class="n">' + t[2] + "</span>" : "") + "</button>";
    }).join("") + '</div><div id="c-pane"></div>';
    if (a) {
      html += '<section class="card"><div class="card__head"><div><h3>Record a decision</h3><p>Every action is written to the audit trail</p></div></div>' +
        '<label class="field"><span>Note (optional)</span><input id="c-note" maxlength="300" placeholder="Reason or instruction" /></label>' +
        '<div class="decision" style="margin-top:10px"><button class="btn btn--primary btn--sm" data-action="assign_inspection">Assign inspection</button><button class="btn btn--ghost btn--sm" data-action="acknowledge">Acknowledge</button><button class="btn btn--ghost btn--sm" data-action="seek_clarification">Seek clarification</button><button class="btn btn--ghost btn--sm" data-action="escalate">Escalate</button><button class="btn btn--danger btn--sm" data-action="dismiss">Dismiss</button></div>' +
        '<div class="row small" style="margin-top:12px"><span class="muted">Was this alert useful?</span><button class="btn btn--quiet btn--sm" data-fb="1">Yes</button><button class="btn btn--quiet btn--sm" data-fb="0">No</button></div></section>';
    }
    html += "</div>";
    body.innerHTML = html;
    if (a) $("#c-gauge").appendChild(Charts.gauge(Math.round(a.risk_score), a.severity));

    function pane() {
      var t = State.caseTab, host = $("#c-pane"), h = "";
      if (t === "overview") {
        if (a) {
          h += '<section class="card"><div class="card__head"><div><h3>Why it was flagged</h3><p>' + reasons.length + " signal" + (reasons.length === 1 ? "" : "s") + " contributed to the score</p></div></div>" +
            reasons.map(function (r) {
              var share = Math.round(Number(r.contribution || r.impact || 0) / totalContribution * 100);
              return '<div class="reason"><div class="reason__top"><span class="tag tag--code">' + esc(r.code) + "</span><strong>" + esc(r.label || codeLabel(r.code)) + '</strong><span class="tiny faint">' + esc(r.layer || "") + '</span><span class="reason__pct">' + share + '%</span></div><div class="small muted">' + esc(r.detail || "") + '</div><div class="reason__bar"><span style="width:' + share + '%"></span></div></div>';
            }).join("") + "</section>";
          h += '<section class="card"><div class="card__head"><div><h3>Fund flow</h3><p>Money against progress</p></div></div><div class="flow">' +
            flowRow("Sanctioned", e.sanction_amount, e.sanction_amount, "var(--low)") + flowRow("Estimate", e.estimate_amount, e.sanction_amount, "var(--medium)") +
            flowRow("Spent", e.expenditure, Math.max(e.sanction_amount, e.expenditure), (e.expenditure > e.sanction_amount ? "var(--critical)" : "var(--accent)")) +
            '<div class="flow__row"><span>Progress</span><div class="flow__bar"><span style="width:' + Math.min(100, e.physical_progress) + '%;background:var(--ok)"></span></div><strong>' + Number(e.physical_progress).toFixed(0) + "%</strong></div></div></section>";
          h += '<div class="stat-list">' + [["Idle days", e.idle_days], ["Payments", e.payment_count], ["Largest payment", inr(e.largest_payment)], ["Category median", inr(e.category_median_sanction)], ["Beneficiaries", num(w.beneficiaries)], ["Completeness", Math.round((e.completeness || 0) * 100) + "%"]].map(function (s) { return '<div class="stat"><span>' + s[0] + "</span><strong>" + (s[1] == null ? "\u2014" : s[1]) + "</strong></div>"; }).join("") + "</div>";
        }
        h += '<section class="card"><div class="card__head"><div><h3>Work details</h3></div></div><div class="props"><span>Agency</span><div>' + esc(w.agency) + "</div><span>MP</span><div>" + esc(w.mp_name) + " (" + esc(w.house) + ")</div><span>Recommended</span><div>" + dateFmt(w.recommended_date) + "</div><span>Sanctioned</span><div>" + dateFmt(w.sanction_date) + "</div><span>Expected completion</span><div>" + dateFmt(w.expected_completion) + "</div><span>Status</span><div>" + esc(w.status) + "</div></div></section>";
        if (d.peers && d.peers.length) h += '<section class="card"><div class="card__head"><div><h3>Peer works</h3><p>Same category, same district. Average sanction ' + inr(d.peer_avg_sanction) + '</p></div></div><div class="list">' + d.peers.map(function (p) { return '<div class="list__item" data-peer="' + esc(p.work_id) + '"><span class="grow truncate">' + esc(p.work_name) + '</span><span class="tiny muted">' + inr(p.sanction_amount) + "</span></div>"; }).join("") + "</div></section>";
      } else if (t === "timeline") {
        var ev = [];
        (a && a.evidence.timeline || []).forEach(function (x) { ev.push({ date: x.date, text: x.event, cls: "" }); });
        (d.payments || []).forEach(function (p) { ev.push({ date: p.pay_date, text: "Payment " + inr(p.amount) + " at " + Number(p.progress_at_payment).toFixed(0) + "% progress (" + p.voucher + ")", cls: "is-pay" }); });
        (d.progress || []).forEach(function (p) { ev.push({ date: p.update_date, text: "Progress " + Number(p.progress).toFixed(0) + "%: " + (p.remark || ""), cls: "" }); });
        ev.sort(function (x, y) { return String(x.date).localeCompare(String(y.date)); });
        h = ev.length ? '<ul class="timeline">' + ev.map(function (x) { return '<li class="' + x.cls + '"><time>' + dateFmt(x.date) + "</time>" + esc(x.text) + "</li>"; }).join("") + "</ul>" : empty("No timeline events");
      } else if (t === "discussion") {
        h = (d.comments.length ? d.comments.map(function (c) { return '<div class="comment">' + avatar(c.username, c.name) + '<div><div class="comment__meta"><b>' + esc(c.name) + "</b> \u00b7 " + ago(c.created_at) + '</div><div class="comment__body">' + mentionize(c.body) + "</div></div></div>"; }).join("") : empty("No discussion yet", "Start the conversation. Use @username to notify a colleague.", ICONS.chat)) +
          '<div class="composer"><textarea id="c-comment" rows="3" placeholder="Write a comment. Mention with @username"></textarea><div class="row" style="justify-content:space-between"><span class="composer__hint">Try ' + users.slice(0, 3).map(function (u) { return "@" + u.username; }).join(", ") + '</span><button class="btn btn--primary btn--sm" id="c-post">Post comment</button></div></div>';
      } else {
        var acts = a ? a.actions : [];
        h = acts.length ? '<ul class="timeline is-done">' + acts.map(function (x) { return '<li class="is-done"><time>' + ago(x.created_at) + " \u00b7 " + esc(x.username) + "</time><strong>" + esc(codeLabel(x.action)) + "</strong>" + (x.note ? ": " + esc(x.note) : "") + "</li>"; }).join("") + "</ul>" : empty("No actions recorded", "Decisions and status changes will appear here.");
      }
      host.innerHTML = h;
      $$("[data-peer]", host).forEach(function (n) { n.addEventListener("click", function () { openCase(n.dataset.peer); }); });
      var post = $("#c-post");
      if (post) post.addEventListener("click", function () {
        var v = $("#c-comment").value.trim(); if (!v) return;
        post.disabled = true;
        api("/api/works/" + encodeURIComponent(w.work_id) + "/comments", { method: "POST", body: { body: v } }).then(function (r) {
          d.comments = r.items; State.caseTab = "discussion"; paintCase(d); toast("Comment posted", "success");
        }).catch(function (er) { toast(er.message, "error"); post.disabled = false; });
      });
    }
    function flowRow(label, v, max, color) { return '<div class="flow__row"><span>' + label + '</span><div class="flow__bar"><span style="width:' + Math.min(100, (v || 0) / Math.max(max || 1, 1) * 100) + "%;background:" + color + '"></span></div><strong>' + inr(v) + "</strong></div>"; }
    pane();

    $$("#c-tabs .tab", body).forEach(function (b) { b.addEventListener("click", function () { State.caseTab = b.dataset.tab; $$("#c-tabs .tab", body).forEach(function (x) { x.classList.toggle("is-active", x === b); }); pane(); }); });
    $$("[data-close-drawer]", body).forEach(function (b) { b.addEventListener("click", closeDrawer); });
    $("#c-watch").addEventListener("click", function () {
      api("/api/watchlist/toggle", { method: "POST", body: { work_id: w.work_id } }).then(function (r) { d.watching = r.watching; paintCase(d); toast(r.watching ? "Added to your watchlist" : "Removed from watchlist", "success"); });
    });
    $("#c-memo").addEventListener("click", function () { printMemo(d); });
    function refresh(msg) { toast(msg, "success"); api("/api/works/" + encodeURIComponent(w.work_id)).then(paintCase); if (location.hash === "#/alerts" || location.hash === "#/board" || location.hash === "#/dashboard") softRefresh(); }
    if (a) {
      $("#c-assignee").addEventListener("change", function (ev) { api("/api/alerts/" + a.id + "/assign", { method: "POST", body: { assignee: ev.target.value } }).then(function () { refresh("Assignee updated"); }).catch(function (er) { toast(er.message, "error"); }); });
      $("#c-status").addEventListener("change", function (ev) { api("/api/alerts/" + a.id + "/status", { method: "POST", body: { status: ev.target.value } }).then(function () { refresh("Status updated"); }).catch(function (er) { toast(er.message, "error"); }); });
      $$("[data-action]", body).forEach(function (b) {
        b.addEventListener("click", function () {
          api("/api/alerts/" + a.id + "/action", { method: "POST", body: { action: b.dataset.action, note: $("#c-note").value } }).then(function () { State.caseTab = "activity"; refresh("Decision recorded"); }).catch(function (er) { toast(er.message, "error"); });
        });
      });
      $$("[data-fb]", body).forEach(function (b) { b.addEventListener("click", function () { api("/api/alerts/" + a.id + "/feedback", { method: "POST", body: { useful: b.dataset.fb === "1" } }).then(function () { toast("Thanks for the feedback", "success"); }); }); });
    }
  }

  function softRefresh() { var h = location.hash.replace("#/", ""); if (h === "board" || h === "dashboard") router(); else if (h === "alerts") { var v = $("#view"); if (v && $("#alerts-table", v)) fetchAlerts(v); } }

  /* ----------------------------- printable memo ------------------------- */
  function printMemo(d) {
    var w = d.work, a = d.alert, e = a ? a.evidence : {};
    var host = document.createElement("div"); host.className = "memo-host";
    host.innerHTML = '<div class="memo"><div class="memo__head"><strong>DRISHTI \u00b7 Inspection memo</strong><span>' + new Date().toLocaleDateString("en-IN", { dateStyle: "long" }) + "</span></div>" +
      "<h1>" + esc(w.work_name) + "</h1><p>" + esc(w.work_id) + " \u00b7 " + esc(w.district) + ", " + esc(w.state) + " \u00b7 " + esc(w.category) + " \u00b7 Agency: " + esc(w.agency) + "</p>" +
      (a ? "<h2>Risk assessment</h2><p>Risk score <b>" + Number(a.risk_score).toFixed(0) + "/100 (" + esc(a.severity) + ")</b>, confidence " + Math.round(a.confidence * 100) + "%. Status: " + statusLabel(a.status) + ". Owner: " + esc(a.assignee_name || "Unassigned") + ". Due " + dateFmt(a.due_at) + ".</p>" +
        "<h2>Reasons flagged</h2><table><thead><tr><th>Signal</th><th>Detail</th></tr></thead><tbody>" + a.reason_codes.map(function (r) { return "<tr><td>" + esc(r.label || r.code) + "</td><td>" + esc(r.detail || "") + "</td></tr>"; }).join("") + "</tbody></table>" +
        "<h2>Key figures</h2><table><tbody><tr><td>Sanctioned</td><td>" + inr(e.sanction_amount) + "</td><td>Spent</td><td>" + inr(e.expenditure) + "</td></tr><tr><td>Physical progress</td><td>" + Number(e.physical_progress).toFixed(0) + "%</td><td>Idle days</td><td>" + (e.idle_days == null ? "\u2014" : e.idle_days) + "</td></tr></tbody></table>" +
        "<h2>Points to verify on site</h2><ul>" + a.reason_codes.slice(0, 4).map(function (r) { return "<li>" + esc(REASON_NEXT[r.code] || "Verify records against the site.") + "</li>"; }).join("") + "</ul>" : "<p>No active alert.</p>") +
      '<h2>Inspection findings</h2><p style="height:90px;border-bottom:1px solid #999"></p><div class="sign"><span>Inspecting officer</span><span>Date</span></div>' +
      '<p style="margin-top:20px;font-size:9pt;color:#555">Generated by DRISHTI (Developed by TEAM SYNTRIX). Risk signals are for human review and are not findings of wrongdoing.</p></div>';
    document.body.appendChild(host); document.body.classList.add("printing-memo");
    var cleanup = function () { document.body.classList.remove("printing-memo"); host.remove(); window.removeEventListener("afterprint", cleanup); };
    window.addEventListener("afterprint", cleanup);
    setTimeout(function () { window.print(); setTimeout(cleanup, 1500); }, 100);
  }

  /* ----------------------------- notifications -------------------------- */
  function refreshNotifications() {
    if (!State.token) return Promise.resolve();
    return api("/api/notifications").then(function (d) {
      State.notif = d;
      var c = $("#notif-count"); c.hidden = !d.unread; c.textContent = d.unread > 9 ? "9+" : d.unread;
      if (!$("#notif-pop").hidden) paintNotifications();
    }).catch(function () {});
  }
  function paintNotifications() {
    var d = State.notif; if (!d) return;
    var pop = $("#notif-pop"), s = d.sla || {};
    pop.innerHTML = '<div class="notif__head"><strong>Notifications</strong><button class="btn btn--quiet btn--sm" id="notif-read">Mark all read</button></div>' +
      '<div class="notif__sla"><div data-nf="breached"><strong>' + (s.breached || 0) + '</strong>Overdue</div><div data-nf="due_soon"><strong>' + (s.due_soon || 0) + '</strong>Due soon</div><div data-nf="mine"><strong>' + (s.mine || 0) + "</strong>Assigned to me</div></div>" +
      '<div class="notif__list">' + (d.items.length ? d.items.map(function (n) {
        return '<div class="notif' + (n.read_at ? "" : " is-unread") + '" data-nwork="' + esc(n.work_id || "") + '"><span class="notif__icon notif__icon--' + esc(n.kind) + '">' + svgIcon(n.kind === "mention" ? ICONS.chat : n.kind === "sla" ? ICONS.clock : ICONS.policy) + '</span><div><div class="notif__title">' + esc(n.title) + '</div><div class="notif__body">' + esc(n.body || "") + '</div><div class="notif__time">' + ago(n.created_at) + "</div></div></div>";
      }).join("") : empty("You are all caught up")) + "</div>";
    $("#notif-read").addEventListener("click", function () { api("/api/notifications/read", { method: "POST", body: {} }).then(refreshNotifications); });
    $$("[data-nwork]", pop).forEach(function (n) { n.addEventListener("click", function () { pop.hidden = true; if (n.dataset.nwork) openCase(n.dataset.nwork, "discussion"); }); });
    $$("[data-nf]", pop).forEach(function (n) {
      n.addEventListener("click", function () { pop.hidden = true; var k = n.dataset.nf; goQueue(k === "mine" ? { assignee: "me" } : { sla: k }); });
    });
  }

  /* ----------------------------- command palette ------------------------ */
  var Palette = { items: [], idx: 0 };
  function openPalette() {
    if (!State.token) return;
    $("#palette").hidden = false; $("#modal").hidden = true;
    var i = $("#palette-input"); i.value = ""; i.focus(); buildPalette("");
  }
  function buildPalette(q) {
    var ql = q.toLowerCase(), items = [];
    Object.keys(ROUTES).forEach(function (k) { if (!ql || ROUTES[k].title.toLowerCase().indexOf(ql) >= 0) items.push({ group: "Go to", label: ROUTES[k].title, hint: "g " + k[0], run: function () { location.hash = "#/" + k; } }); });
    [["Toggle dark mode", toggleTheme], ["Show keyboard shortcuts", showShortcuts], ["Sign out", function () { signOut(); }]].forEach(function (c) { if (!ql || c[0].toLowerCase().indexOf(ql) >= 0) items.push({ group: "Commands", label: c[0], run: c[1] }); });
    [["Critical alerts", { severity: "critical" }], ["Overdue (SLA breached)", { sla: "breached" }], ["Assigned to me", { assignee: "me" }], ["Unassigned", { assignee: "none" }]].forEach(function (c) { if (!ql || c[0].toLowerCase().indexOf(ql) >= 0) items.push({ group: "Quick filters", label: c[0], run: function () { goQueue(c[1]); } }); });
    Palette.items = items; Palette.idx = 0; paintPalette();
    if (ql.length >= 2) {
      var token = ++Palette.token || (Palette.token = 1);
      api("/api/alerts?limit=8&q=" + encodeURIComponent(q)).then(function (r) {
        if (token !== Palette.token) return;
        r.items.forEach(function (a) { Palette.items.push({ group: "Works", label: a.work_name, hint: a.work_id, run: function () { openCase(a.work_id); } }); });
        paintPalette();
      }).catch(function () {});
    }
  }
  function paintPalette() {
    var list = $("#palette-list"), last = "", h = "";
    Palette.items.forEach(function (it, i) {
      if (it.group !== last) { h += '<div class="pal-group">' + it.group + "</div>"; last = it.group; }
      h += '<div class="pal-item' + (i === Palette.idx ? " is-active" : "") + '" data-i="' + i + '"><span class="truncate">' + esc(it.label) + "</span>" + (it.hint ? '<span class="hint">' + esc(it.hint) + "</span>" : "") + "</div>";
    });
    list.innerHTML = h || empty("No results");
    $$(".pal-item", list).forEach(function (n) { n.addEventListener("click", function () { runPalette(+n.dataset.i); }); });
    var act = $(".pal-item.is-active", list); if (act && act.scrollIntoView) act.scrollIntoView({ block: "nearest" });
  }
  function runPalette(i) { var it = Palette.items[i]; if (!it) return; $("#palette").hidden = true; it.run(); }

  function showShortcuts() {
    openModal('<h3>Keyboard shortcuts</h3><div class="shortcuts">' + [["Command palette", "Ctrl / \u2318 K"], ["This help", "?"], ["Next / previous alert", "j / k"], ["Open focused alert", "Enter"], ["Select focused alert", "x"], ["Go to overview / alerts / board", "g d / g a / g b"], ["Go to scorecards / policy", "g s / g p"], ["Close panels", "Esc"]].map(function (s) { return "<span>" + s[0] + "</span><span><kbd>" + s[1] + "</kbd></span>"; }).join("") + '</div><div class="row" style="justify-content:flex-end"><button class="btn btn--primary" data-close-modal>Done</button></div>');
  }

  /* ----------------------------- router --------------------------------- */
  function router() {
    var hash = location.hash.replace(/^#\/?/, "").split("?")[0];
    if (!hash) hash = State.token ? "dashboard" : "home";
    if (hash === "home" || hash === "landing") { screen("landing"); return; }
    if (hash === "login") { if (State.token) { location.hash = "#/dashboard"; return; } screen("login"); return; }
    if (!ROUTES[hash]) hash = "dashboard";
    if (!State.token) { sessionStorage.setItem("drishti-next", "#/" + hash); screen("login"); return; }
    screen("app"); hydrateUser();
    var r = ROUTES[hash];
    $("#page-title").textContent = r.title; $("#page-subtitle").textContent = r.subtitle;
    document.title = r.title + " \u00b7 DRISHTI";
    $$(".nav__item").forEach(function (n) { n.classList.toggle("is-active", n.dataset.route === hash); });
    $("#app").classList.remove("nav-open");
    var view = $("#view"); view.scrollTop = 0;
    view.classList.remove("view-in"); void view.offsetWidth; view.classList.add("view-in");
    r.render(view);
    animateView(view);
    if (!State.slaLoaded && hash !== "dashboard") { State.slaLoaded = true; api("/api/summary").then(updateNavCounts).catch(function () {}); }
    refreshNotifications();
  }

  /* ----------------------------- motion --------------------------------- */
  function countUp(el) {
    var txt = el.textContent, m = txt.match(/\d[\d,]*\.?\d*/);
    if (!m || el.dataset.counted || el.children.length) return; el.dataset.counted = "1";
    var raw = m[0], dec = (raw.split(".")[1] || "").length, target = parseFloat(raw.replace(/,/g, ""));
    if (!isFinite(target) || target === 0) return;
    var pre = txt.slice(0, m.index), post = txt.slice(m.index + raw.length), t0 = null, dur = 900;
    function fmt(v) { var s = v.toFixed(dec); if (raw.indexOf(",") >= 0 || target >= 1000) s = Number(s).toLocaleString("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec }); return pre + s + post; }
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    function step(ts) { if (!t0) t0 = ts; var p = Math.min(1, (ts - t0) / dur), e = 1 - Math.pow(1 - p, 3); el.textContent = fmt(target * e); if (p < 1) requestAnimationFrame(step); else el.textContent = txt; }
    el.textContent = fmt(0); requestAnimationFrame(step);
  }
  function animateView(view) {
    var tries = 0;
    (function tick() {
      var cards = $$(".card, .att, .col, .kcard, .hello, .compare > div", view);
      if (!cards.length && tries++ < 20) { setTimeout(tick, 60); return; }
      cards.forEach(function (c, i) { if (c.dataset.in) return; c.dataset.in = "1"; c.classList.add("reveal"); c.style.animationDelay = Math.min(i, 14) * 45 + "ms"; });
      $$(".kpi__value, .att strong", view).forEach(countUp);
    })();
  }

  /* ----------------------------- boot ----------------------------------- */
  function boot() {
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (t.closest("[data-theme-toggle]")) { toggleTheme(); return; }
      var sc = t.closest("[data-scroll]");
      if (sc) { e.preventDefault(); var target = document.getElementById(sc.getAttribute("href").slice(1)); if (target) target.scrollIntoView({ behavior: "smooth" }); return; }
      var ln = t.closest("[data-launch]");
      if (ln) { e.preventDefault(); location.hash = State.token ? "#/dashboard" : "#/login"; if (State.token) router(); return; }
      if (t.closest("[data-close-drawer]")) { closeDrawer(); return; }
      if (t.closest("[data-close-modal]")) { closeModals(); return; }
      if (t.closest("[data-open-sidebar]")) { $("#app").classList.add("nav-open"); return; }
      if (t.closest("[data-close-sidebar]")) { $("#app").classList.remove("nav-open"); return; }
      if (t.closest("[data-open-palette]")) { openPalette(); return; }
      if (t.closest("[data-open-shortcuts]")) { $("#user-pop").hidden = true; showShortcuts(); return; }
      if (t.closest("#notif-btn")) { var np = $("#notif-pop"); np.hidden = !np.hidden; $("#user-pop").hidden = true; if (!np.hidden) { paintNotifications(); } return; }
      if (t.closest("#user-btn")) { var up = $("#user-pop"); up.hidden = !up.hidden; $("#notif-pop").hidden = true; return; }
      if (t.closest("#logout-side")) { signOut(); return; }
      if (t.closest("#logout")) { $("#user-pop").hidden = true; signOut(); return; }
      if (!t.closest(".popover")) { $("#notif-pop").hidden = true; $("#user-pop").hidden = true; }
    });

    $$("[data-demo]").forEach(function (b) {
      b.addEventListener("click", function () {
        $("#login-username").value = b.dataset.demo; $("#login-password").value = "drishti";
        $$("[data-demo]").forEach(function (x) { x.classList.toggle("is-active", x === b); });
        if (typeof b.blur === "function") b.blur();
      });
    });
    $("#login-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var err = $("#login-error"); err.hidden = true;
      signIn($("#login-username").value.trim(), $("#login-password").value).catch(function (er) { err.textContent = er.message; err.hidden = false; });
    });
    $("#rerun-detection").addEventListener("click", function () {
      var b = $("#rerun-detection"); b.disabled = true;
      api("/api/detect/run", { method: "POST", body: {} }).then(function (r) { toast("Detection complete. " + (r.alerts != null ? r.alerts + " alerts." : ""), "success"); State.options = null; router(); })
        .catch(function (er) { toast(er.message, "error"); }).then(function () { b.disabled = false; });
    });
    $("#palette-input").addEventListener("input", function (e) { buildPalette(e.target.value); });
    $("#palette-input").addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); Palette.idx = Math.min(Palette.items.length - 1, Palette.idx + 1); paintPalette(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); Palette.idx = Math.max(0, Palette.idx - 1); paintPalette(); }
      else if (e.key === "Enter") { e.preventDefault(); runPalette(Palette.idx); }
    });

    var gPending = false, gTimer;
    document.addEventListener("keydown", function (e) {
      var tag = (e.target.tagName || "").toLowerCase(), typing = tag === "input" || tag === "textarea" || tag === "select";
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); if ($("#palette").hidden) openPalette(); else $("#palette").hidden = true; return; }
      if (e.key === "Escape") {
        if (!$("#palette").hidden || !$("#modal").hidden) closeModals(); else if (!$("#case-drawer").hidden) closeDrawer();
        $("#notif-pop").hidden = true; $("#user-pop").hidden = true; return;
      }
      if (typing || e.ctrlKey || e.metaKey || e.altKey || !State.token || $("#app").hidden) return;
      if (e.key === "?") { showShortcuts(); return; }
      if (e.key === "/") { e.preventDefault(); openPalette(); return; }
      if (gPending) {
        gPending = false; clearTimeout(gTimer);
        var m = { d: "dashboard", a: "alerts", b: "board", s: "scorecards", p: "policy", w: "watchlist", m: "districts" }[e.key];
        if (m) location.hash = "#/" + m; return;
      }
      if (e.key === "g") { gPending = true; gTimer = setTimeout(function () { gPending = false; }, 900); return; }
      var rows = $$("#view tr[data-work]");
      if (!rows.length || !$("#case-drawer").hidden) return;
      if (e.key === "j" || e.key === "k") {
        State.focusRow = Math.max(0, Math.min(rows.length - 1, State.focusRow + (e.key === "j" ? 1 : -1)));
        rows.forEach(function (r, i) { r.classList.toggle("is-focus", i === State.focusRow); });
        rows[State.focusRow].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && rows[State.focusRow]) openCase(rows[State.focusRow].dataset.work);
      else if (e.key === "x" && rows[State.focusRow]) { var c = $("[data-select]", rows[State.focusRow]); if (c) { c.checked = !c.checked; toggleSelect(+c.dataset.select, c.checked); rows[State.focusRow].classList.toggle("is-selected", c.checked); } }
    });

    window.addEventListener("hashchange", router);
    setInterval(refreshNotifications, 60000);
    router();
  }

  boot();
})();
