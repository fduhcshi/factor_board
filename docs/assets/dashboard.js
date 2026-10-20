/* 因子看板：285 个方块 + 悬停简介 + 点击详情图表 */
(function () {
  "use strict";

  var DATA = window.FACTOR_BOARD;
  if (!DATA) {
    document.getElementById("board").innerHTML =
      '<div class="empty">未找到 window.FACTOR_BOARD，请先运行 <code>python main.py</code>。</div>';
    return;
  }

  var C = {
    text: "#26201a",
    muted: "#75695f",
    surface: "#fffdf7",
    grid: "#eadfcb",
    neutral: "#f7efdd",
    orange: "#ff5c2b",
    yellow: "#ffd84d",
    pink: "#ffb9cc",
    blue: "#a5dcff",
    deepBlue: "#3b82c4"
  };

  var METRICS = [
    { id: "ic", label: "IC均值", short: "IC", get: function (f) { return f.ic; }, kind: "div", fmt: function (v) { return (v * 100).toFixed(1); } },
    { id: "ir", label: "IR", short: "IR", get: function (f) { return f.ir; }, kind: "div", fmt: function (v) { return v.toFixed(2); } },
    { id: "ls", label: "多空年化", short: "多空", get: function (f) { return f.ls[1]; }, kind: "div", fmt: pct1 },
    { id: "q1", label: "1分位年化", short: "1分位", get: function (f) { return f.q1[1]; }, kind: "div", fmt: pct1 },
    { id: "q5", label: "5分位年化", short: "5分位", get: function (f) { return f.q5[1]; }, kind: "div", fmt: pct1 },
    { id: "to", label: "多空换手", short: "换手", get: function (f) { return f.ls[4]; }, kind: "seq", fmt: pct1 },
    { id: "gi", label: "|IC|>0.02 占比", short: "IC占比", get: function (f) { return f.gi; }, kind: "seq", fmt: function (v) { return (v * 100).toFixed(0) + "%"; } }
  ];

  var GROUPS = ["量能", "价格技术", "财务", "风格", "未实现"];
  var bandInfo = [];

  var state = { metric: METRICS[0], query: "", layout: "global" };
  var tiles = [];        // { index, el, metricEl }
  var charts = [];       // modal chart instances
  var modalToken = 0;
  var seriesQueue = {};
  var tip = document.getElementById("tip");
  var modal = document.getElementById("modal");
  var modalBody = document.getElementById("modal-body");

  function pct1(v) { return (v * 100).toFixed(1) + "%"; }

  function $(id) { return document.getElementById(id); }

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ---------------- 颜色 ---------------- */
  var SCALE = [
    [0.0, "#2f7d43"],
    [0.25, "#8fcf8a"],
    [0.5, "#fff4dd"],
    [0.75, "#ffab86"],
    [1.0, "#c9331a"]
  ];

  function hexToRgb(hex) {
    var n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function mix(a, b, t) {
    var ca = hexToRgb(a), cb = hexToRgb(b);
    var r = Math.round(ca[0] + (cb[0] - ca[0]) * t);
    var g = Math.round(ca[1] + (cb[1] - ca[1]) * t);
    var bl = Math.round(ca[2] + (cb[2] - ca[2]) * t);
    return "rgb(" + r + "," + g + "," + bl + ")";
  }

  function scaleColor(t) {
    t = Math.min(1, Math.max(0, t));
    for (var i = 1; i < SCALE.length; i += 1) {
      if (t <= SCALE[i][0]) {
        var left = SCALE[i - 1], right = SCALE[i];
        var local = (t - left[0]) / (right[0] - left[0] || 1);
        return mix(left[1], right[1], local);
      }
    }
    return SCALE[SCALE.length - 1][1];
  }

  function luminance(rgbString) {
    var parts = rgbString.match(/\d+/g).map(Number);
    var channels = parts.map(function (value) {
      var v = value / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  }

  function metricValues(metric) {
    // 色阶只按已实现因子定范围，避免未实现因子改变同一数值的显示颜色
    return DATA.factors
      .filter(function (f) { return f.s; })
      .map(metric.get)
      .filter(function (v) { return v !== null && v !== undefined && isFinite(v); });
  }

  function colorFor(metric, value, range) {
    if (value === null || value === undefined || !isFinite(value)) return "#efe4d0";
    var span = range.max - range.min || 1;
    return scaleColor((value - range.min) / span);
  }

  function rangeFor(metric) {
    var values = metricValues(metric);
    if (!values.length) return { min: 0, max: 1 };
    return {
      min: values.reduce(function (a, b) { return Math.min(a, b); }, Infinity),
      max: values.reduce(function (a, b) { return Math.max(a, b); }, -Infinity)
    };
  }

  /* ---------------- 渲染 ---------------- */
  function renderHero() {
    var meta = DATA.meta;
    $("run-pill").textContent = "更新至 " + (meta.dates.end || "—");
    $("run-pill").title = "RUN " + meta.run_id + " · 生成于 " + meta.generated_at;
    var stats = [
      { k: "FACTORS", v: meta.total, n: "" },
      { k: "IMPLEMENTED", v: meta.implemented, n: "已接入 AKShare 数据" },
      { k: "MAX |IC|", v: (meta.strongest_ic.value * 100).toFixed(1), n: meta.strongest_ic.name },
      { k: "MAX LS", v: (meta.strongest_ls.value * 100).toFixed(1) + "%", n: meta.strongest_ls.name }
    ];
    $("hero-stats").innerHTML = stats.map(function (item) {
      return '<div class="hero-sticker"><div class="k">' + item.k + "</div>" +
        '<div class="v">' + item.v + "</div>" +
        (item.n ? '<div class="n" title="' + escapeHtml(item.n) + '">' + escapeHtml(item.n) + "</div>" : "") +
        "</div>";
    }).join("");

    $("footer-meta").textContent =
      "数据更新至 " + (meta.dates.end || "—") + " · " + (meta.universe.index_code || "") + " · " +
      (meta.dates.start || "") + " → " + (meta.dates.end || "") + " · " +
      (meta.implemented) + "/" + meta.total + " 已实现 · RUN " + meta.run_id;
  }

  function renderChips() {
    $("metric-chips").innerHTML = METRICS.map(function (metric) {
      return '<button type="button" class="mchip" data-id="' + metric.id + '" aria-pressed="' +
        (metric.id === state.metric.id) + '">' + metric.label + "</button>";
    }).join("");
    $("metric-chips").addEventListener("click", function (event) {
      var chip = event.target.closest(".mchip");
      if (!chip) return;
      var next = METRICS.filter(function (m) { return m.id === chip.dataset.id; })[0];
      if (!next || next.id === state.metric.id) return;
      state.metric = next;
      Array.prototype.forEach.call($("metric-chips").children, function (node) {
        node.setAttribute("aria-pressed", String(node.dataset.id === next.id));
      });
      renderBoard();
      applyMetric();
    });
  }

  function bindLayoutChips() {
    $("layout-chips").addEventListener("click", function (event) {
      var chip = event.target.closest(".lchip");
      if (!chip) return;
      var next = chip.dataset.layout;
      if (!next || next === state.layout) return;
      state.layout = next;
      Array.prototype.forEach.call($("layout-chips").children, function (node) {
        node.setAttribute("aria-pressed", String(node.dataset.layout === next));
      });
      renderBoard();
      applyMetric();
    });
  }

  function cardHtml(f, index) {
    return '<button type="button" class="fcard' + (f.s ? "" : " off") + '" data-i="' + index +
      '" aria-label="' + escapeHtml(f.i + " · " + f.n) + '">' +
      '<div class="fc-top"><span class="fc-group">' + escapeHtml(f.g) + "</span>" +
      '<span class="fc-metric"><i>' + state.metric.short + "</i><b></b></span></div>" +
      '<div class="fc-title">' + escapeHtml(f.i) + "</div>" +
      '<div class="fc-name">' + escapeHtml(f.n) + "</div>" +
      "</button>";
  }

  function sortItems(items) {
    return items.sort(function (a, b) {
      var left = state.metric.get(a.factor);
      var right = state.metric.get(b.factor);
      var leftEmpty = left === null || left === undefined || !isFinite(left);
      var rightEmpty = right === null || right === undefined || !isFinite(right);
      if (leftEmpty && rightEmpty) return a.index - b.index;
      if (leftEmpty) return 1;
      if (rightEmpty) return -1;
      return right - left;
    });
  }

  function gridHtml(items) {
    return '<div class="tiles">' +
      items.map(function (item) { return cardHtml(item.factor, item.index); }).join("") +
      "</div>";
  }

  function renderBoard() {
    bandInfo = [];
    var all = DATA.factors.map(function (factor, index) {
      return { factor: factor, index: index };
    });

    if (state.layout === "global") {
      var ordered = sortItems(all.filter(function (item) { return item.factor.s; }));
      bandInfo.push({
        group: "全部",
        indices: ordered.map(function (item) { return item.index; }),
        avgIc: ordered.reduce(function (acc, item) {
          return acc + (item.factor.ic === null ? 0 : Math.abs(item.factor.ic));
        }, 0) / ordered.length,
        fixedNote: "仅已实现 · 按指标值从大到小"
      });
      $("board").innerHTML = '<section class="band" data-group="全部">' +
        '<div class="band-head"><span class="band-name">已实现因子</span>' +
        '<span class="band-count">' + ordered.length + "</span>" +
        '<span class="band-note">仅已实现 · 按指标值从大到小</span></div>' +
        gridHtml(ordered) + "</section>";
    } else {
      var byGroup = {};
      GROUPS.forEach(function (g) { byGroup[g] = []; });
      all.forEach(function (item) {
        var group = byGroup[item.factor.g] ? item.factor.g : "未实现";
        byGroup[group].push(item);
      });
      $("board").innerHTML = GROUPS.map(function (group) {
        var items = byGroup[group];
        if (!items.length) return "";
        sortItems(items);
        var avgIc = items.reduce(function (acc, item) {
          return acc + (item.factor.ic === null ? 0 : Math.abs(item.factor.ic));
        }, 0) / items.length;
        bandInfo.push({
          group: group,
          indices: items.map(function (item) { return item.index; }),
          avgIc: avgIc
        });
        return '<section class="band" data-group="' + group + '">' +
          '<div class="band-head"><span class="band-name">' + group + "</span>" +
          '<span class="band-count">' + items.length + "</span>" +
          '<span class="band-note">平均 |IC| ' + (avgIc * 100).toFixed(2) + "</span></div>" +
          gridHtml(items) + "</section>";
      }).join("");
    }

    tiles = Array.prototype.map.call(document.querySelectorAll(".fcard"), function (el) {
      return {
        index: Number(el.dataset.i),
        el: el,
        metricEl: el.querySelector(".fc-metric b")
      };
    });
    bandInfo.forEach(function (band) {
      var node = document.querySelector('.band[data-group="' + band.group + '"]');
      band.noteEl = node ? node.querySelector(".band-note") : null;
    });
  }

  function updateBandNotes() {
    var metric = state.metric;
    bandInfo.forEach(function (band) {
      if (!band.noteEl) return;
      if (band.fixedNote) {
        band.noteEl.textContent = band.fixedNote;
        return;
      }
      if (metric.id === "ic") {
        band.noteEl.textContent = "平均 |IC| " + (band.avgIc * 100).toFixed(2);
        return;
      }
      var values = band.indices
        .map(function (index) { return metric.get(DATA.factors[index]); })
        .filter(function (value) { return value !== null && value !== undefined && isFinite(value); });
      if (!values.length) { band.noteEl.textContent = "—"; return; }
      var mean = values.reduce(function (a, b) { return a + b; }, 0) / values.length;
      band.noteEl.textContent = "均值 " + metric.fmt(mean);
    });
  }

  function applyMetric() {
    var metric = state.metric;
    var range = rangeFor(metric);
    tiles.forEach(function (tile) {
      var value = metric.get(DATA.factors[tile.index]);
      var background = colorFor(metric, value, range);
      tile.el.style.background = background;
      tile.el.style.color = luminance(background) < 0.42 ? "#fffdf7" : "#26201a";
      tile.metricEl.textContent = (value === null || value === undefined) ? "—" : metric.fmt(value);
      tile.el.querySelector(".fc-metric i").textContent = metric.short;
    });
    updateLegend(metric, range);
    updateBandNotes();
    applySearch();
    fillLastRow();
  }

  function fillLastRow() {
    document.querySelectorAll(".fcard.ghost").forEach(function (node) { node.remove(); });
    document.querySelectorAll(".tiles").forEach(function (grid) {
      var columns = getComputedStyle(grid).gridTemplateColumns.split(" ").length;
      if (!columns) return;
      var count = grid.querySelectorAll(".fcard:not(.ghost)").length;
      var remainder = count % columns;
      if (!remainder) return;
      for (var i = 0; i < columns - remainder; i += 1) {
        var ghost = document.createElement("div");
        ghost.className = "fcard ghost";
        ghost.setAttribute("aria-hidden", "true");
        grid.appendChild(ghost);
      }
    });
  }

  function applySearch() {
    var query = state.query;
    var hits = 0;
    tiles.forEach(function (tile) {
      var f = DATA.factors[tile.index];
      var matched = !query || (f.n + " " + f.i).toLowerCase().indexOf(query.toLowerCase()) >= 0;
      tile.el.classList.toggle("dim", !matched);
      tile.el.classList.toggle("hit", Boolean(query) && matched);
      if (matched) hits += 1;
    });
    var count = document.getElementById("match-count");
    if (count) {
      count.style.display = query ? "inline-flex" : "none";
      count.textContent = "命中 " + hits;
    }
  }

  function updateLegend(metric, range) {
    $("legend-bar").classList.remove("seq");
    $("legend-low").textContent = metric.fmt(range.min);
    $("legend-high").textContent = metric.fmt(range.max);
  }

  /* ---------------- 悬停提示 ---------------- */
  function tipHtml(f) {
    function row(label, value) {
      return '<div><div class="t-k">' + label + '</div><div class="t-v">' + value + "</div></div>";
    }
    function pct(value, digits) {
      return value === null || value === undefined ? "—" : (value * 100).toFixed(digits) + "%";
    }
    var note = "";
    if (f.ic !== null) {
      if (f.ic > 0.02) note = "IC 为正：因子值越大，未来收益倾向越高。";
      else if (f.ic < -0.02) note = "IC 为负：因子值越大，未来收益倾向越低，属反向因子。";
      else note = "|IC| 小于 0.02，预测能力偏弱，更适合作为组合的辅助项。";
    }
    return '<div class="t-name">' + escapeHtml(f.n) + "</div>" +
      '<div class="t-intro">' + escapeHtml(f.i) + "</div>" +
      '<div class="t-grid">' +
        row("IC均值", f.ic === null ? "—" : (f.ic * 100).toFixed(2)) +
        row("IR", f.ir === null ? "—" : f.ir.toFixed(2)) +
        row("多空年化", pct(f.ls[1], 1)) +
        row("多空换手", pct(f.ls[4], 1)) +
        row("1分位年化", pct(f.q1[1], 1)) +
        row("5分位年化", pct(f.q5[1], 1)) +
      "</div>" +
      (f.f
        ? '<div class="t-formula">' + escapeHtml(f.f) + "</div>"
        : '<div class="t-formula empty">聚宽未提供该因子的计算公式</div>') +
      '<div class="t-note">' + note + "</div>" +
      (f.s ? "" : '<div class="t-warn">未实现：' + escapeHtml(f.r || f.e) + "</div>") +
      '<div class="t-foot">点击查看全部指标与曲线 →</div>';
  }

  function showTip(event, factor) {
    tip.innerHTML = tipHtml(factor);
    tip.classList.add("show");
    moveTip(event);
  }

  function moveTip(event) {
    var rect = tip.getBoundingClientRect();
    var x = event.clientX + 16;
    var y = event.clientY + 16;
    if (x + rect.width > window.innerWidth - 10) x = event.clientX - rect.width - 16;
    if (y + rect.height > window.innerHeight - 10) y = event.clientY - rect.height - 16;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }

  function hideTip() { tip.classList.remove("show"); }

  /* ---------------- 详情弹窗 ---------------- */
  function barOption(categories, values, colors, unit, digits) {
    var scale = unit === "%" ? 100 : 1;
    var places = digits === undefined ? 1 : digits;
    var data = values.map(function (v) {
      return v === null || v === undefined ? null : Number((v * scale).toFixed(places + 1));
    });
    return {
      backgroundColor: C.surface,
      grid: { left: 6, right: 10, top: 20, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: function (params) {
          var p = params[0];
          return p.name + "<br/><b>" + (p.value === null ? "—" : p.value.toFixed(places) + unit) + "</b>";
        }
      },
      xAxis: {
        type: "category",
        data: categories,
        axisLine: { lineStyle: { color: C.text, width: 2 } },
        axisLabel: { color: C.text, fontSize: 10, interval: 0 }
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: C.grid } },
        axisLabel: { color: C.muted, fontSize: 9, formatter: function (v) { return v + unit; } }
      },
      series: [{
        type: "bar",
        data: data.map(function (v, i) { return { value: v, itemStyle: { color: colors[i] } }; }),
        barWidth: "56%",
        itemStyle: { borderColor: C.text, borderWidth: 1.4 },
        label: {
          show: true, position: "top", color: C.muted, fontSize: 9,
          formatter: function (p) { return p.value === null ? "" : p.value.toFixed(places) + unit; }
        }
      }]
    };
  }

  function metricTable(f, bm) {
    function cell(value, column) {
      if (value === null || value === undefined) return "<td>—</td>";
      if (column === 4) return "<td>" + value.toFixed(2) + "</td>";
      return "<td>" + (value * 100).toFixed(2) + "%</td>";
    }
    var rows = [
      ["1分位", [f.q1[0], f.q1[1], f.q1[2], f.q1[3], f.q1[4], f.q1[5]]],
      ["5分位", [f.q5[0], f.q5[1], f.q5[2], f.q5[3], f.q5[4], f.q5[5]]],
      ["多空", [f.ls[0], f.ls[1], null, f.ls[2], f.ls[3], f.ls[4]]],
      ["反向多空", [f.l2[0], f.l2[1], null, f.l2[2], f.l2[3], f.l2[4]]],
      ["基准", [null, bm, null, null, null, null]]
    ];
    return '<div class="m-table-wrap"><table class="m-table"><thead><tr>' +
      "<th>组合</th><th>累计收益</th><th>年化</th><th>超额年化</th><th>最大回撤</th><th>夏普</th><th>换手率</th>" +
      "</tr></thead><tbody>" +
      rows.map(function (row) {
        return "<tr><td>" + row[0] + "</td>" + row[1].map(cell).join("") + "</tr>";
      }).join("") +
      "</tbody></table></div>";
  }

  function openModal(index) {
    var f = DATA.factors[index];
    var bm = DATA.meta.benchmark;
    modalToken += 1;
    var token = modalToken;
    var pills = '<span class="pill mono">' + f.g + "</span>" +
      '<span class="pill mono ' + (f.s ? "green" : "pink") + '">' + (f.s ? "已实现" : "未实现") + "</span>" +
      (f.s ? '<span class="pill mono blue">覆盖率 ' + (f.c * 100).toFixed(1) + "%</span>" : "");

    var stat = function (k, v) {
      return '<div class="m-stat"><div class="k">' + k + '</div><div class="v">' + v + "</div></div>";
    };

    var formula = f.f ? f.f : "聚宽未提供该因子的计算公式。";
    var localBlock = f.s
      ? '<div class="m-block"><h4>实现说明</h4><p>覆盖率 ' + (f.c * 100).toFixed(1) +
        "% · 最新截面有效股票 " + f.k + " 只。因子值按公告日对齐，口径见 <code>report.md</code>。</p></div>"
      : '<div class="m-block warn"><h4>未实现原因</h4><p>' + escapeHtml(f.r || f.e || "未登记原因") + "</p></div>";

    modalBody.innerHTML =
      '<div class="m-eyebrow">' + f.g + " · FACTOR DETAIL</div>" +
      '<div class="m-title">' + escapeHtml(f.i) + "</div>" +
      '<div class="m-name">' + escapeHtml(f.n) + "</div>" +
      '<div class="m-pills">' + pills + "</div>" +
      '<div class="m-stats">' +
        stat("IC 均值", f.ic === null ? "—" : (f.ic * 100).toFixed(2)) +
        stat("IR", f.ir === null ? "—" : f.ir.toFixed(3)) +
        stat("|IC|>0.02", f.gi === null ? "—" : (f.gi * 100).toFixed(0) + "%") +
        stat("多空年化", f.ls[1] === null ? "—" : (f.ls[1] * 100).toFixed(1) + "%") +
      "</div>" +
      '<div class="m-series-card">' +
        "<h4>因子值 · 截面时间序列</h4>" +
        '<div class="m-series" id="mc-series"></div>' +
        '<h4 style="margin-top:6px">覆盖率</h4>' +
        '<div class="m-coverage" id="mc-coverage"></div>' +
        '<div class="m-hint" id="mc-hint">正在加载因子值序列…</div>' +
      "</div>" +
      '<div class="m-series-card"><h4>聚宽全指标</h4>' + metricTable(f, bm) + "</div>" +
      '<div class="m-charts">' +
        '<div class="m-chart-card"><h4>年化收益</h4><div class="m-chart" id="mc-return"></div></div>' +
        '<div class="m-chart-card"><h4>夏普比率</h4><div class="m-chart" id="mc-sharpe"></div></div>' +
        '<div class="m-chart-card"><h4>最大回撤</h4><div class="m-chart" id="mc-dd"></div></div>' +
        '<div class="m-chart-card"><h4>换手率</h4><div class="m-chart" id="mc-turnover"></div></div>' +
      "</div>" +
      '<div class="m-block"><h4>聚宽公式</h4><p>' + escapeHtml(formula) + "</p></div>" +
      localBlock;

    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    hideTip();
    drawCharts(f, bm);
    drawSeries(f, token);
    document.getElementById("modal-close").focus();
    setHash(f.n);
  }

  function setHash(name) {
    try {
      history.replaceState(null, "", "#f=" + encodeURIComponent(name));
    } catch (error) {
      /* file:// 下部分浏览器不允许 replaceState，忽略即可 */
    }
  }

  function clearHash() {
    try {
      history.replaceState(null, "", location.pathname);
    } catch (error) {
      /* 同上 */
    }
  }

  function openFromHash() {
    var match = /^#f=(.+)$/.exec(location.hash || "");
    if (!match) return;
    var name = decodeURIComponent(match[1]);
    var index = DATA.factors.findIndex(function (factor) { return factor.n === name; });
    if (index >= 0) openModal(index);
  }

  function drawCharts(f, bm) {
    charts.forEach(function (c) { c.dispose(); });
    charts = [];
    if (!window.echarts) return;

    var labels = ["1分位", "5分位", "多空", "反向多空"];
    var colors = [C.pink, C.blue, C.orange, C.yellow];

    var returns = [f.q1[1], f.q5[1], f.ls[1], f.l2[1]];
    var returnsCat = labels.concat(["基准"]);
    var returnsVal = returns.concat([bm]);
    var returnsColor = colors.concat(["#d9cdb8"]);

    var specs = [
      ["mc-return", barOption(returnsCat, returnsVal, returnsColor, "%", 1)],
      ["mc-sharpe", barOption(labels, [f.q1[4], f.q5[4], f.ls[3], f.l2[3]], colors, "", 2)],
      ["mc-dd", barOption(labels, [f.q1[3], f.q5[3], f.ls[2], f.l2[2]], colors, "%", 1)],
      ["mc-turnover", barOption(["1分位", "5分位", "多空"], [f.q1[5], f.q5[5], f.ls[4]], [C.pink, C.blue, C.orange], "%", 2)]
    ];

    specs.forEach(function (spec) {
      var node = document.getElementById(spec[0]);
      if (!node) return;
      var chart = echarts.init(node, null, { renderer: "canvas" });
      chart.setOption(spec[1]);
      charts.push(chart);
    });
  }

  function loadSeries(name, callback) {
    if (window.SERIES_POOL && window.SERIES_POOL[name]) {
      callback(window.SERIES_POOL[name]);
      return;
    }
    if (seriesQueue[name]) {
      seriesQueue[name].push(callback);
      return;
    }
    seriesQueue[name] = [callback];
    var script = document.createElement("script");
    script.src = "./data/series/" + name + ".js";
    script.onload = function () {
      var payload = (window.SERIES_POOL || {})[name] || null;
      (seriesQueue[name] || []).forEach(function (fn) { fn(payload); });
      delete seriesQueue[name];
    };
    script.onerror = function () {
      (seriesQueue[name] || []).forEach(function (fn) { fn(null); });
      delete seriesQueue[name];
    };
    document.head.appendChild(script);
  }

  function drawSeries(f, token) {
    var seriesEl = document.getElementById("mc-series");
    var coverageEl = document.getElementById("mc-coverage");
    var hint = document.getElementById("mc-hint");
    if (!seriesEl || !coverageEl || !hint) return;
    if (!f.s) {
      seriesEl.style.display = "none";
      coverageEl.style.display = "none";
      hint.className = "m-hint warn";
      hint.textContent = "该因子暂未实现，没有因子值序列，原因见页末。";
      return;
    }
    loadSeries(f.n, function (payload) {
      if (token !== modalToken) return;
      if (!payload) {
        seriesEl.style.display = "none";
        coverageEl.style.display = "none";
        hint.className = "m-hint warn";
        hint.textContent = "因子值序列加载失败，请确认 docs/data/series/ 目录存在。";
        return;
      }
      hint.className = "m-hint";
      hint.textContent = "曲线由 AKShare 行情与财报计算：每日截面中位数与 25/75 分位；下方为当日有值的股票占比。";
      var dates = DATA.meta.calendar;
      if (!window.echarts) return;

      var medianChart = echarts.init(seriesEl, null, { renderer: "canvas" });
      medianChart.setOption({
        backgroundColor: C.surface,
        tooltip: { trigger: "axis" },
        legend: { top: 0, textStyle: { fontSize: 10, color: C.text } },
        grid: { left: 8, right: 14, top: 30, bottom: 46, containLabel: true },
        xAxis: {
          type: "category",
          data: dates,
          axisLine: { lineStyle: { color: C.text, width: 1.5 } },
          axisLabel: { color: C.muted, fontSize: 9, hideOverlap: true }
        },
        yAxis: {
          type: "value",
          scale: true,
          splitLine: { lineStyle: { color: C.grid } },
          axisLabel: { color: C.muted, fontSize: 9 }
        },
        dataZoom: [
          { type: "inside", start: 0, end: 100 },
          { type: "slider", height: 14, bottom: 8, borderColor: C.text, fillerColor: "rgba(255,92,43,0.12)" }
        ],
        series: [
          { name: "P75", type: "line", data: payload.u, showSymbol: false, lineStyle: { color: "#ffb9cc", width: 1.2 }, itemStyle: { color: "#ffb9cc" } },
          { name: "中位数", type: "line", data: payload.m, showSymbol: false, lineStyle: { color: C.orange, width: 2.2 }, itemStyle: { color: C.orange }, areaStyle: { color: "rgba(255,92,43,0.07)" } },
          { name: "P25", type: "line", data: payload.l, showSymbol: false, lineStyle: { color: "#7fb8e0", width: 1.2 }, itemStyle: { color: "#7fb8e0" } }
        ]
      });
      charts.push(medianChart);

      var coverageChart = echarts.init(coverageEl, null, { renderer: "canvas" });
      coverageChart.setOption({
        backgroundColor: C.surface,
        tooltip: {
          trigger: "axis",
          formatter: function (params) {
            var p = params[0];
            return p.name + "<br/>覆盖率 <b>" + p.value + "%</b>";
          }
        },
        grid: { left: 8, right: 14, top: 8, bottom: 4, containLabel: true },
        xAxis: { type: "category", data: dates, show: false },
        yAxis: {
          type: "value", min: 0, max: 100,
          splitLine: { lineStyle: { color: C.grid } },
          axisLabel: { color: C.muted, fontSize: 8, formatter: "{value}%" }
        },
        series: [{
          type: "line",
          data: payload.c.map(function (v) { return v === null ? null : Number((v * 100).toFixed(1)); }),
          showSymbol: false,
          lineStyle: { color: "#4a9d5f", width: 1.4 },
          areaStyle: { color: "rgba(74,157,95,0.12)" }
        }]
      });
      charts.push(coverageChart);
    });
  }

  function closeModal() {
    modalToken += 1;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    charts.forEach(function (c) { c.dispose(); });
    charts = [];
    clearHash();
  }

  /* ---------------- 交互绑定 ---------------- */
  function bindBoard() {
    var board = $("board");
    board.addEventListener("mouseover", function (event) {
      var card = event.target.closest(".fcard");
      if (!card) return;
      showTip(event, DATA.factors[Number(card.dataset.i)]);
    });
    board.addEventListener("mousemove", function (event) {
      if (!tip.classList.contains("show")) return;
      moveTip(event);
    });
    board.addEventListener("mouseout", function (event) {
      if (!event.relatedTarget || !event.relatedTarget.closest(".fcard")) hideTip();
    });
    board.addEventListener("click", function (event) {
      var card = event.target.closest(".fcard");
      if (!card) return;
      openModal(Number(card.dataset.i));
    });
    board.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      var card = event.target.closest(".fcard");
      if (!card) return;
      event.preventDefault();
      openModal(Number(card.dataset.i));
    });
    window.addEventListener("scroll", hideTip, { passive: true });
  }

  function bindSearch() {
    var input = $("search");
    var count = document.createElement("span");
    count.className = "pill mono";
    count.id = "match-count";
    count.style.display = "none";
    input.parentNode.appendChild(count);

    var timer = null;
    input.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        state.query = input.value.trim();
        applySearch();
      }, 120);
    });
  }

  function bindModal() {
    $("modal-close").addEventListener("click", closeModal);
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeModal();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && modal.classList.contains("open")) closeModal();
    });
    window.addEventListener("resize", function () {
      charts.forEach(function (chart) { chart.resize(); });
    });
  }

  renderHero();
  renderChips();
  renderBoard();
  applyMetric();
  bindBoard();
  bindSearch();
  bindLayoutChips();
  bindModal();
  openFromHash();

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(fillLastRow, 150);
  });
})();
