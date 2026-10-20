/* 因子看板交互：分组图、覆盖率分布、因子预览与可筛选清单。 */
(function () {
  "use strict";

  var DATA = window.PAGE_DATA;
  var THEME = {
    text: "#26201a",
    muted: "#75695f",
    surface: "#fffdf7",
    grid: "#eadfcb",
    orange: "#ff5c2b",
    yellow: "#ffd84d",
    pink: "#ffb9cc",
    blue: "#a5dcff",
    green: "#b9e6b1"
  };

  var state = { query: "", group: "全部", status: "全部", page: 1, pageSize: 20 };
  var filtered = [];

  if (!DATA) {
    document.querySelector("main").innerHTML =
      '<div class="loading">未找到 window.PAGE_DATA，请先运行 <code>python main.py</code> 生成数据。</div>';
    return;
  }

  function $(id) { return document.getElementById(id); }

  function fmt(value, digits) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    var abs = Math.abs(value);
    if (abs !== 0 && (abs >= 1e6 || abs < 1e-3)) return value.toExponential(2);
    return Number(value).toFixed(digits === undefined ? 4 : digits);
  }

  function pct(value) { return (value * 100).toFixed(1) + "%"; }

  function renderHeader() {
    var counts = DATA.meta.counts;
    $("run-pill").textContent = "RUN " + (DATA.meta.run_id || "—");
    $("sticker-implemented").textContent = counts.implemented;
    $("sticker-unsupported").textContent = counts.unsupported;
    $("pill-dates").textContent =
      (DATA.meta.dates.start || "—") + " → " + (DATA.meta.dates.end || "—");
    $("pill-count").textContent = counts.total + " FACTORS";
    $("footer-run").textContent =
      "RUN " + (DATA.meta.run_id || "—") + " · " + (DATA.meta.universe.index_code || "") +
      " · " + counts.total + " 因子";

    var metrics = [
      { label: "因子总数", value: counts.total, note: "聚宽因子库全量" },
      { label: "已实现", value: counts.implemented, note: "含量价 / 财务 / 风格" },
      { label: "覆盖率中位数", value: pct(counts.coverage_median), note: "非空单元格占比" },
      { label: "股票 × 交易日", value: (DATA.meta.universe.n_stocks || 0) + " × " + (DATA.meta.dates.trading_days || 0), note: "本次计算面板" }
    ];
    $("metrics").innerHTML = metrics.map(function (item) {
      return '<div class="metric"><div class="label">' + item.label + '</div>' +
        '<div class="value">' + item.value + '</div>' +
        '<div class="note">' + item.note + '</div></div>';
    }).join("");
  }

  function baseGrid() {
    return { left: 8, right: 16, top: 34, bottom: 8, containLabel: true };
  }

  function renderGroupChart() {
    var node = $("chart-groups");
    if (!window.echarts || !node) return;
    var chart = echarts.init(node, null, { renderer: "canvas" });
    var groups = DATA.groups.map(function (g) { return g.name; });
    var series = [
      { name: "已实现", color: THEME.green, key: "implemented" },
      { name: "未实现", color: THEME.pink, key: "unsupported" },
      { name: "计算失败", color: THEME.orange, key: "failed" }
    ];
    chart.setOption({
      backgroundColor: THEME.surface,
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { bottom: 0, textStyle: { color: THEME.text, fontSize: 12 } },
      grid: { left: 8, right: 16, top: 16, bottom: 36, containLabel: true },
      xAxis: {
        type: "category",
        data: groups,
        axisLine: { lineStyle: { color: THEME.text, width: 2 } },
        axisLabel: { color: THEME.text, fontSize: 12 }
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: THEME.grid } },
        axisLabel: { color: THEME.muted }
      },
      series: series.map(function (item) {
        return {
          name: item.name,
          type: "bar",
          stack: "total",
          barWidth: "48%",
          itemStyle: { color: item.color, borderColor: THEME.text, borderWidth: 1.5 },
          data: DATA.groups.map(function (g) { return g[item.key]; })
        };
      })
    });
    window.addEventListener("resize", function () { chart.resize(); });
  }

  function renderCoverageChart() {
    var node = $("chart-coverage");
    if (!window.echarts || !node) return;
    var chart = echarts.init(node, null, { renderer: "canvas" });
    var lowest = DATA.factors
      .filter(function (item) { return item.status === "implemented"; })
      .sort(function (a, b) { return a.coverage - b.coverage; })
      .slice(0, 15)
      .reverse();

    chart.setOption({
      backgroundColor: THEME.surface,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: function (params) {
          var item = params[0];
          return item.name + "<br/>覆盖率 " + (item.value * 100).toFixed(1) + "%";
        }
      },
      grid: { left: 8, right: 46, top: 8, bottom: 8, containLabel: true },
      xAxis: {
        type: "value",
        max: 1,
        splitLine: { lineStyle: { color: THEME.grid } },
        axisLabel: { color: THEME.muted, formatter: function (v) { return (v * 100).toFixed(0) + "%"; } }
      },
      yAxis: {
        type: "category",
        data: lowest.map(function (item) { return item.name; }),
        axisLine: { lineStyle: { color: THEME.text, width: 2 } },
        axisLabel: { color: THEME.text, fontSize: 10.5, fontFamily: "monospace" }
      },
      series: [{
        type: "bar",
        data: lowest.map(function (item) { return item.coverage; }),
        barWidth: "62%",
        itemStyle: { color: THEME.pink, borderColor: THEME.text, borderWidth: 1.2 },
        label: {
          show: true,
          position: "right",
          color: THEME.muted,
          fontSize: 10.5,
          formatter: function (params) { return (params.value * 100).toFixed(1) + "%"; }
        }
      }]
    });
    window.addEventListener("resize", function () { chart.resize(); });
  }

  function renderSeries() {
    var node = $("chart-series");
    var select = $("series-select");
    if (!DATA.series.length) {
      node.innerHTML = '<div class="loading">本次运行没有可预览的因子序列。</div>';
      return;
    }
    select.innerHTML = DATA.series.map(function (item, index) {
      return '<option value="' + index + '">' + item.factor + '</option>';
    }).join("");
    if (!window.echarts) return;

    var chart = echarts.init(node, null, { renderer: "canvas" });
    function draw(index) {
      var item = DATA.series[index];
      var stats = $("series-stats");
      var last = item.median.filter(function (v) { return v !== null; }).pop();
      stats.textContent = "LATEST MEDIAN " + fmt(last, 4);
      chart.setOption({
        backgroundColor: THEME.surface,
        tooltip: { trigger: "axis" },
        legend: { top: 0, textStyle: { color: THEME.text } },
        grid: { left: 12, right: 18, top: 42, bottom: 56, containLabel: true },
        xAxis: {
          type: "category",
          data: item.dates,
          axisLine: { lineStyle: { color: THEME.text, width: 2 } },
          axisLabel: { color: THEME.muted, hideOverlap: true }
        },
        yAxis: {
          type: "value",
          scale: true,
          splitLine: { lineStyle: { color: THEME.grid } },
          axisLabel: { color: THEME.muted, formatter: function (v) { return fmt(v, 3); } }
        },
        dataZoom: [
          { type: "inside", start: 0, end: 100 },
          { type: "slider", height: 18, bottom: 8, borderColor: THEME.text, fillerColor: "rgba(255,92,43,0.12)" }
        ],
        series: [
          { name: "P25", type: "line", data: item.p25, showSymbol: false, lineStyle: { color: THEME.blue, width: 1.5, type: "dashed" }, itemStyle: { color: THEME.blue } },
          { name: "P75", type: "line", data: item.p75, showSymbol: false, lineStyle: { color: THEME.pink, width: 1.5, type: "dashed" }, itemStyle: { color: THEME.pink } },
          { name: "中位数", type: "line", data: item.median, showSymbol: false, lineStyle: { color: THEME.orange, width: 2.6 }, itemStyle: { color: THEME.orange }, areaStyle: { color: "rgba(255,92,43,0.10)" } }
        ]
      }, true);
    }
    draw(0);
    select.addEventListener("change", function () { draw(Number(select.value)); });
    window.addEventListener("resize", function () { chart.resize(); });
  }

  function buildChips(containerId, values, key) {
    var container = $(containerId);
    container.innerHTML = values.map(function (value) {
      return '<button type="button" class="chip" data-value="' + value + '" aria-pressed="' +
        (state[key] === value) + '">' + value + "</button>";
    }).join("");
    container.querySelectorAll(".chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        state[key] = chip.dataset.value;
        state.page = 1;
        container.querySelectorAll(".chip").forEach(function (other) {
          other.setAttribute("aria-pressed", String(other.dataset.value === state[key]));
        });
        updateTable();
      });
    });
  }

  function applyFilters() {
    var query = state.query.trim().toLowerCase();
    filtered = DATA.factors.filter(function (item) {
      if (state.group !== "全部" && item.group !== state.group) return false;
      if (state.status === "已实现" && item.status !== "implemented") return false;
      if (state.status === "未实现" && item.status !== "unsupported") return false;
      if (state.status === "有值" && !(item.coverage > 0)) return false;
      if (!query) return true;
      return (item.name + " " + item.intro + " " + item.formula).toLowerCase().indexOf(query) >= 0;
    });
  }

  function updateTable() {
    applyFilters();
    var totalPages = Math.max(1, Math.ceil(filtered.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    var start = (state.page - 1) * state.pageSize;
    var rows = filtered.slice(start, start + state.pageSize);

    $("table-body").innerHTML = rows.map(function (item) {
      var statusClass = item.status === "implemented" ? (item.coverage > 0 ? "ok" : "fail") : "no";
      var statusText = item.status === "implemented" ? (item.coverage > 0 ? "已实现" : "无数据") : "未实现";
      var note = item.status === "implemented"
        ? (item.error ? item.error : (item.formula || "—"))
        : item.reason;
      return "<tr>" +
        '<td><span class="factor-name">' + item.name + "</span></td>" +
        "<td>" + (item.intro || "—") + "</td>" +
        '<td><span class="pill mono">' + item.group + "</span></td>" +
        '<td class="num">' + pct(item.coverage) + "</td>" +
        '<td class="num">' + fmt(item.latest_mean, 4) + "</td>" +
        '<td class="num">' + item.stocks_with_value + "</td>" +
        '<td><span class="status ' + statusClass + '">' + statusText + "</span>" +
        '<div class="formula">' + (note || "") + "</div></td>" +
        "</tr>";
    }).join("") || '<tr><td colspan="7" style="padding:28px;text-align:center;color:#75695f;">没有匹配的因子</td></tr>';

    $("pager-info").textContent = "第 " + state.page + " / " + totalPages + " 页 · 共 " + filtered.length + " 个";
    $("prev-page").disabled = state.page <= 1;
    $("next-page").disabled = state.page >= totalPages;
  }

  function exportCsv() {
    var header = ["factor", "intro", "group", "status", "coverage", "latest_mean", "stocks_with_value", "formula", "reason"];
    var lines = [header.join(",")];
    filtered.forEach(function (item) {
      var row = [item.name, item.intro, item.group, item.status, item.coverage,
        item.latest_mean === null ? "" : item.latest_mean, item.stocks_with_value,
        (item.formula || "").replace(/"/g, '""'), (item.reason || "").replace(/"/g, '""')];
      lines.push(row.map(function (cell) {
        return typeof cell === "string" && /[",\n]/.test(cell) ? '"' + cell + '"' : cell;
      }).join(","));
    });
    var blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = "factor_filtered.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function bindControls() {
    var groups = ["全部"].concat(DATA.groups.map(function (g) { return g.name; }));
    buildChips("group-chips", groups, "group");
    buildChips("status-chips", ["全部", "已实现", "未实现", "有值"], "status");

    var search = $("search");
    var timer = null;
    search.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        state.query = search.value;
        state.page = 1;
        updateTable();
      }, 160);
    });
    $("prev-page").addEventListener("click", function () { state.page -= 1; updateTable(); });
    $("next-page").addEventListener("click", function () { state.page += 1; updateTable(); });
    $("export-csv").addEventListener("click", exportCsv);
  }

  renderHeader();
  renderGroupChart();
  renderCoverageChart();
  renderSeries();
  bindControls();
  updateTable();
})();
