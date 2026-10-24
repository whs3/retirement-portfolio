'use strict';

let perfChart       = null;
let categoriesChart = null;
let holdingsChart   = null;
let benchmarkChart  = null;
let _perfFullData = null;
let _activePerfPeriod = '12m';
let _activeBenchmark  = '';   // ticker, or '' for none
let _benchmarkCache   = {};   // ticker -> { dates, prices, name }
let _benchmarkSeq     = 0;    // discards stale fetches when the selection changes fast

const BENCHMARK_LABELS = {
  '^GSPC': 'S&P 500',
  '^IXIC': 'NASDAQ',
  '^RUT':  'Russell 2000',
  '^MID':  'S&P MidCap 400',
  'SHY':   'Short-Term Treasuries (SHY)',
};

const _PERF_PERIOD_LABELS = {
  '3m':  'Past 3 Months',
  '6m':  'Past 6 Months',
  '12m': 'Past 12 Months',
  'ytd': 'YTD',
};

const _PERIOD_START_LABELS = {
  '3m':  'Value 3 Months Ago',
  '6m':  'Value 6 Months Ago',
  '12m': 'Value 12 Months Ago',
  'ytd': 'Value at Jan 1',
};

const _PERIOD_GAIN_LABELS = {
  '3m':  '3-Month Investment Gain / Loss',
  '6m':  '6-Month Investment Gain / Loss',
  '12m': '12-Month Investment Gain / Loss',
  'ytd': 'YTD Investment Gain / Loss',
};

const FLOW_SOURCES = {
  manual:          'Manual',
  holding_add:     'Added holding',
  holding_edit:    'Share change',
  holding_delete:  'Removed holding',
  sell_all:        'Sold all',
  import:          'CSV import',
};

const HOLDING_COLORS = [
  '#2563eb','#d97706','#16a34a','#7c3aed','#db2777',
  '#0891b2','#ea580c','#65a30d','#9333ea','#0284c7',
];

function fmt(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function fmtK(n) {
  if (Math.abs(n) >= 1_000_000) return '$' + (n / 1_000_000).toFixed(2) + 'M';
  if (Math.abs(n) >= 1_000)     return '$' + (n / 1_000).toFixed(1) + 'K';
  return fmt(n);
}

function fmtSigned(n) {
  return (n > 0 ? '+' : '') + fmt(n);
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadPerformance() {
  const loading = document.getElementById('loadingMsg');
  loading.className     = 'alert';
  loading.textContent   = 'Loading performance…';
  loading.style.display = 'block';

  ['summaryCards','perfPeriodRow','chartCard','benchmarkChartCard','categoriesChartCard','holdingsChartCard','monthlyCard','untrackedNotice'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });

  try {
    const res  = await fetch('/api/performance');
    const data = await res.json();

    loading.style.display = 'none';

    if (!res.ok) {
      loading.classList.add('alert-danger');
      loading.textContent   = data.error ?? 'Failed to load performance data.';
      loading.style.display = 'block';
      return;
    }

    if (!data.dates || !data.dates.length) {
      loading.classList.add('alert-danger');
      loading.textContent   = 'No price history available. Add holdings with ticker symbols to see performance.';
      loading.style.display = 'block';
      return;
    }

    document.getElementById('asOfDate').textContent =
      'As of ' + new Date().toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short', timeZone: document.querySelector('meta[name="server-timezone"]').content });

    _perfFullData = data;
    _perfFullData.cash_flows = data.cash_flows || [];
    const dateInput = document.getElementById('cashFlowDate');
    if (dateInput && !dateInput.value && data.dates.length) {
      dateInput.value = data.dates[data.dates.length - 1];
    }
    document.getElementById('perfPeriodRow').style.display = 'flex';
    setPerfPeriod('12m');

    if (data.untracked && data.untracked.length) {
      const msg = document.getElementById('untrackedMsg');
      const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      msg.innerHTML = `<strong>Note:</strong> The following tickers had no price history and are included at their current value: ${data.untracked.map(t => `<strong>${esc(t)}</strong>`).join(', ')}.`;
      document.getElementById('untrackedNotice').style.display = 'block';
    }

  } catch (err) {
    loading.classList.add('alert-danger');
    loading.textContent   = `Request failed: ${err.message}`;
    loading.style.display = 'block';
  }
}

// ── Period selector ───────────────────────────────────────────────────────────

function setPerfPeriod(period) {
  _activePerfPeriod = period;
  _updatePerfPeriodBtns();
  const sliced = _slicePerfData(_perfFullData, period);
  const flows  = _perfFullData.cash_flows || [];
  renderSummary(_summarize(sliced.dates, sliced.values, flows), period);
  renderChart(sliced.dates, sliced.values);
  renderCategoriesChart(sliced.dates, sliced.categories_series || []);
  renderHoldingsChart(sliced.dates, sliced.holdings_series || []);
  renderMonthly(_monthlyFromSeries(sliced.dates, sliced.values, flows));
  renderBenchmarkChart(sliced.dates, _twrIndex(sliced.dates, sliced.values, flows));
  renderCashFlows(sliced.dates, flows);
}

function _updatePerfPeriodBtns() {
  [['3m','perfBtn3M'],['6m','perfBtn6M'],['ytd','perfBtnYTD'],['12m','perfBtn12M']].forEach(([key, id]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    const active = key === _activePerfPeriod;
    btn.style.background = active ? 'var(--primary, #2563eb)' : 'transparent';
    btn.style.color      = active ? '#fff' : 'var(--text-muted, #64748b)';
    btn.style.fontWeight = active ? '600' : '400';
  });
}

function _slicePerfData(data, period) {
  const dates = data.dates;
  if (period === '12m' || !dates.length) return data;

  let cutoffStr;
  if (period === 'ytd') {
    const year = new Date(dates[dates.length - 1] + 'T00:00:00').getFullYear();
    cutoffStr = `${year}-01-01`;
  } else {
    const months = period === '3m' ? 3 : 6;
    const last   = new Date(dates[dates.length - 1] + 'T00:00:00');
    last.setMonth(last.getMonth() - months);
    cutoffStr = last.toISOString().slice(0, 10);
  }

  const idx = dates.findIndex(d => d >= cutoffStr);
  if (idx === -1) return data;

  return {
    ...data,
    dates:           dates.slice(idx),
    values:          data.values.slice(idx),
    holdings_series:   (data.holdings_series   || []).map(h => ({
      ...h,
      values: h.values.slice(idx),
      prices: (h.prices || []).slice(idx),
    })),
    categories_series: (data.categories_series || []).map(c => ({ ...c, values: c.values.slice(idx) })),
  };
}

// Attribute each flow to the snapshot that first includes the money. Flows on
// or before the first day are already inside the starting value.
function _flowsBySnapshot(dates, flows) {
  const totals = {};
  if (!dates.length) return totals;
  const start = dates[0];
  const end = dates[dates.length - 1];
  for (const flow of flows || []) {
    const flowDate = flow.flow_date;
    if (!flowDate || flowDate <= start || flowDate > end) continue;
    const target = dates.find(day => day >= flowDate);
    if (!target || target <= start) continue;
    totals[target] = (totals[target] || 0) + Number(flow.amount);
  }
  return totals;
}

function _round2(n) {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}

// Matches portfolio.services.cash_flows.period_return.
function _periodReturn(dates, values, flows) {
  if (!dates.length || !values.length) {
    return { value_change: 0, net_flow: 0, gain: 0, gain_pct: 0 };
  }
  const start = dates[0];
  const end = dates[dates.length - 1];
  let net = 0;
  for (const flow of flows || []) {
    if (flow.flow_date > start && flow.flow_date <= end) net += Number(flow.amount);
  }
  net = _round2(net);
  const valueChange = _round2(values[values.length - 1] - values[0]);
  const gain = _round2(valueChange - net);
  const byDay = _flowsBySnapshot(dates, flows);
  let factor = 1;
  for (let i = 1; i < dates.length; i++) {
    const begin = Number(values[i - 1]);
    const market = (Number(values[i]) - begin) - (byDay[dates[i]] || 0);
    if (Math.abs(begin) > 0.01) factor *= 1 + market / begin;
  }
  return {
    value_change: valueChange,
    net_flow: net,
    gain: gain,
    gain_pct: Math.round((factor - 1) * 10000) / 100,
  };
}

function _summarize(dates, values, flows) {
  if (!dates.length || !values.length) return {};
  return {
    start_value: values[0],
    end_value: values[values.length - 1],
    peak_value: Math.max(...values),
    ..._periodReturn(dates, values, flows),
  };
}

function _monthlyFromSeries(dates, values, flows) {
  const groups = new Map();
  dates.forEach((day, i) => {
    const ym = day.slice(0, 7);
    if (!groups.has(ym)) groups.set(ym, []);
    groups.get(ym).push(i);
  });
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const rows = [];
  for (const [ym, idxs] of groups) {
    const monthDates = idxs.map(i => dates[i]);
    const monthValues = idxs.map(i => values[i]);
    const [year, month] = ym.split('-');
    rows.push({
      month: `${months[Number(month) - 1]} ${year}`,
      start: monthValues[0],
      end: monthValues[monthValues.length - 1],
      ..._periodReturn(monthDates, monthValues, flows),
    });
  }
  return rows;
}

// Growth of 100 with deposits removed, so the line matches gain_pct.
function _twrIndex(dates, values, flows) {
  if (!values.length) return [];
  const byDay = _flowsBySnapshot(dates, flows);
  const index = [100];
  for (let i = 1; i < values.length; i++) {
    const begin = Number(values[i - 1]);
    const market = (Number(values[i]) - begin) - (byDay[dates[i]] || 0);
    const r = Math.abs(begin) > 0.01 ? market / begin : 0;
    index.push(index[i - 1] * (1 + r));
  }
  return index;
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderSummary(s, period) {
  if (!s || s.start_value == null) return;

  const pos = s.gain >= 0;
  document.getElementById('startValueLabel').textContent = _PERIOD_START_LABELS[period] || 'Value at Start';
  document.getElementById('gainLabel').textContent       = _PERIOD_GAIN_LABELS[period]  || 'Investment Gain / Loss';

  document.getElementById('startValue').textContent = fmt(s.start_value);
  document.getElementById('endValue').textContent   = fmt(s.end_value);
  document.getElementById('peakValue').textContent  = fmt(s.peak_value);

  const gainEl = document.getElementById('gainValue');
  const pctEl  = document.getElementById('gainPct');
  gainEl.textContent = (pos ? '+' : '') + fmt(s.gain);
  gainEl.className   = 'card-value ' + (pos ? 'text-success' : 'text-danger');
  pctEl.textContent  = (pos ? '+' : '') + s.gain_pct.toFixed(2) + '% time-weighted';
  pctEl.className    = 'card-sub '    + (pos ? 'text-success' : 'text-danger');

  const flowEl = document.getElementById('netFlowValue');
  flowEl.textContent = fmtSigned(s.net_flow || 0);
  flowEl.className = 'card-value';
  document.getElementById('valueChangeSub').textContent =
    'Value change ' + fmtSigned(s.value_change || 0);

  document.getElementById('summaryCards').style.display = '';
}

function renderChart(dates, values) {
  const canvas = document.getElementById('performanceChart');
  const ctx    = canvas.getContext('2d');

  const isUp  = values[values.length - 1] >= values[0];
  const color = isUp ? '#16a34a' : '#dc2626';

  const monthStarts = new Set();
  const seenMonths  = new Set();
  for (const d of dates) {
    const ym = d.slice(0, 7);
    if (!seenMonths.has(ym)) { seenMonths.add(ym); monthStarts.add(d); }
  }

  const gradient = ctx.createLinearGradient(0, 0, 0, 320);
  gradient.addColorStop(0, color + '33');
  gradient.addColorStop(1, color + '00');

  const monthGridPlugin = {
    id: 'monthGrid',
    afterDraw(chart) {
      const xScale = chart.scales.x;
      const { top, bottom } = chart.chartArea;
      const c = chart.ctx;
      c.save();
      c.strokeStyle = 'rgba(100,116,139,0.35)';
      c.lineWidth   = 1;
      for (const d of monthStarts) {
        const idx = dates.indexOf(d);
        if (idx === -1) continue;
        const x = xScale.getPixelForValue(idx);
        c.beginPath(); c.moveTo(x, top); c.lineTo(x, bottom); c.stroke();
      }
      c.restore();
    },
  };

  const titleLabel = _activePerfPeriod === 'ytd'
    ? 'Portfolio Value — YTD'
    : `Portfolio Value — ${_PERF_PERIOD_LABELS[_activePerfPeriod]}`;
  document.getElementById('perfChartTitle').textContent = titleLabel;

  if (perfChart) perfChart.destroy();

  perfChart = new Chart(ctx, {
    type:    'line',
    plugins: [monthGridPlugin],
    data: {
      labels: dates,
      datasets: [{
        data:             values,
        borderColor:      color,
        borderWidth:      2,
        backgroundColor:  gradient,
        fill:             true,
        pointRadius:      0,
        pointHoverRadius: 4,
        tension:          0.3,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: ctx => ctx[0].label,
            label: ctx => ' Portfolio Value: ' + fmt(ctx.parsed.y),
          },
        },
      },
      scales: {
        x: {
          type: 'category',
          ticks: {
            autoSkip: false, maxRotation: 0,
            callback(val) {
              const d = this.getLabelForValue(val);
              if (!d || !monthStarts.has(d)) return null;
              return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
            },
          },
          grid: { display: false },
        },
        y: {
          ticks: { callback: v => fmtK(v) },
          grid:  { color: '#f1f5f9' },
        },
      },
    },
  });

  document.getElementById('chartCard').style.display = '';
}

function renderCategoriesChart(dates, categoriesSeries) {
  const card = document.getElementById('categoriesChartCard');

  if (!categoriesSeries || !categoriesSeries.length) {
    card.style.display = 'none';
    if (categoriesChart) { categoriesChart.destroy(); categoriesChart = null; }
    return;
  }

  const monthStarts = new Set();
  const seenMonths  = new Set();
  for (const d of dates) {
    const ym = d.slice(0, 7);
    if (!seenMonths.has(ym)) { seenMonths.add(ym); monthStarts.add(d); }
  }

  const datasets = categoriesSeries.map((cat, i) => ({
    label:            cat.category,
    data:             cat.values,
    borderColor:      HOLDING_COLORS[i % HOLDING_COLORS.length],
    backgroundColor:  HOLDING_COLORS[i % HOLDING_COLORS.length] + 'bb',
    fill:             true,
    pointRadius:      0,
    pointHoverRadius: 4,
    borderWidth:      1,
    tension:          0.3,
  }));

  const monthGridPlugin = {
    id: 'catMonthGrid',
    afterDraw(chart) {
      const xScale = chart.scales.x;
      const { top, bottom } = chart.chartArea;
      const c = chart.ctx;
      c.save();
      c.strokeStyle = 'rgba(100,116,139,0.25)';
      c.lineWidth   = 1;
      for (const d of monthStarts) {
        const idx = dates.indexOf(d);
        if (idx === -1) continue;
        const x = xScale.getPixelForValue(idx);
        c.beginPath(); c.moveTo(x, top); c.lineTo(x, bottom); c.stroke();
      }
      c.restore();
    },
  };

  // Plugin: draw percentage labels on the right side at each category's midpoint
  const pctLabelsPlugin = {
    id: 'catPctLabels',
    afterDraw(chart) {
      const { ctx, chartArea: { right }, scales: { y } } = chart;
      const ds      = chart.data.datasets;
      const lastIdx = chart.data.labels.length - 1;

      // Total of visible datasets at the last point
      let total = 0;
      ds.forEach((d, i) => {
        if (chart.getDatasetMeta(i).visible) total += (Number(d.data[lastIdx]) || 0);
      });
      if (!total) return;

      ctx.save();
      ctx.font         = '600 11px system-ui, sans-serif';
      ctx.textAlign    = 'left';
      ctx.textBaseline = 'middle';

      let cumulative = 0;
      const MIN_BAND_PX = 14;   // skip label if band is too narrow to read

      ds.forEach((d, i) => {
        if (!chart.getDatasetMeta(i).visible) return;
        const val  = Number(d.data[lastIdx]) || 0;
        const mid  = cumulative + val / 2;
        cumulative += val;

        const topPx = y.getPixelForValue(cumulative);
        const botPx = y.getPixelForValue(cumulative - val);
        if (Math.abs(botPx - topPx) < MIN_BAND_PX) return;   // band too thin

        const pct  = (val / total * 100).toFixed(1);
        const yPx  = y.getPixelForValue(mid);
        ctx.fillStyle = d.borderColor;
        ctx.fillText(`${pct}%`, right + 6, yPx);
      });

      ctx.restore();
    },
  };

  const titleLabel = _activePerfPeriod === 'ytd'
    ? 'Portfolio Value by Category — YTD'
    : `Portfolio Value by Category — ${_PERF_PERIOD_LABELS[_activePerfPeriod]}`;
  document.getElementById('categoriesChartTitle').textContent = titleLabel;

  if (categoriesChart) categoriesChart.destroy();

  categoriesChart = new Chart(document.getElementById('categoriesChart').getContext('2d'), {
    type:    'line',
    plugins: [monthGridPlugin, pctLabelsPlugin],
    data:    { labels: dates, datasets },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      layout:              { padding: { right: 52 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'top' },
        tooltip: {
          callbacks: {
            title: ctx => ctx[0].label,
            label: ctx => {
              const total = ctx.chart.data.datasets.reduce(
                (sum, ds) => sum + (Number(ds.data[ctx.dataIndex]) || 0), 0
              );
              const pct = total ? (ctx.parsed.y / total * 100).toFixed(1) : '0.0';
              return ` ${ctx.dataset.label}: ${fmtK(ctx.parsed.y)} (${pct}%)`;
            },
            footer: ctx => {
              const total = ctx.reduce(
                (sum, item) => sum + (Number(item.parsed.y) || 0), 0
              );
              return `Total: ${fmtK(total)}`;
            },
          },
        },
      },
      scales: {
        x: {
          type: 'category',
          ticks: {
            autoSkip: false, maxRotation: 0,
            callback(val) {
              const d = this.getLabelForValue(val);
              if (!d || !monthStarts.has(d)) return null;
              return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
            },
          },
          grid: { display: false },
        },
        y: {
          stacked: true,
          min:     0,
          ticks:   { callback: v => fmtK(v) },
          grid:    { color: '#f1f5f9' },
        },
      },
    },
  });

  card.style.display = '';
}

function renderHoldingsChart(dates, holdingsSeries) {
  const card = document.getElementById('holdingsChartCard');

  if (!holdingsSeries || !holdingsSeries.length) {
    card.style.display = 'none';
    if (holdingsChart) { holdingsChart.destroy(); holdingsChart = null; }
    return;
  }

  const monthStarts = new Set();
  const seenMonths  = new Set();
  for (const d of dates) {
    const ym = d.slice(0, 7);
    if (!seenMonths.has(ym)) { seenMonths.add(ym); monthStarts.add(d); }
  }

  // Each line is % change in per-share price from the first day the holding
  // is held in the period, so buying or selling shares is not drawn as a gain
  // or loss, and a holding bought mid-period still appears. Days not held are
  // null. A holding with no stored price on its first day falls back to value.
  const isSignificant = v => Math.abs(Math.round(Number(v) * 100) / 100) > 0.01;
  const chartable = [];
  for (const h of holdingsSeries) {
    if (!h.values || !h.values.length) continue;
    // Closed by the end of the period: leave it off, as before.
    if (!isSignificant(h.values[h.values.length - 1])) continue;
    const start = h.values.findIndex(isSignificant);
    if (start === -1) continue;
    const prices  = h.prices || [];
    const usePrice = prices[start] != null && prices[start] > 0;
    const basis   = usePrice ? prices : h.values;
    const base    = basis[start];
    const pct = h.values.map((v, i) => {
      if (i < start || !isSignificant(v) || basis[i] == null) return null;
      return +((basis[i] - base) / base * 100).toFixed(4);
    });
    let last = null;
    for (let i = pct.length - 1; i >= 0; i--) {
      if (pct[i] != null) { last = pct[i]; break; }
    }
    if (last == null) continue;
    chartable.push({ ticker: h.ticker, pct, last });
  }

  if (!chartable.length) {
    card.style.display = 'none';
    if (holdingsChart) { holdingsChart.destroy(); holdingsChart = null; }
    return;
  }

  // Sort by end-of-period % change (highest first) before assigning colors so
  // tooltip order and line colors stay in sync without Chart.js itemSort.
  const sortedSeries = [...chartable].sort((a, b) => b.last - a.last);

  const datasets = sortedSeries.map((h, i) => {
    return {
      label:            h.ticker,
      data:             h.pct,
      lastPct:          h.last,
      spanGaps:         true,
      borderColor:      HOLDING_COLORS[i % HOLDING_COLORS.length],
      borderWidth:      1.5,
      backgroundColor:  'transparent',
      fill:             false,
      pointRadius:      0,
      pointHoverRadius: 4,
      tension:          0.3,
    };
  });

  const monthGridPlugin = {
    id: 'holdingsMonthGrid',
    afterDraw(chart) {
      const xScale = chart.scales.x;
      const { top, bottom } = chart.chartArea;
      const c = chart.ctx;
      c.save();
      c.strokeStyle = 'rgba(100,116,139,0.35)';
      c.lineWidth   = 1;
      for (const d of monthStarts) {
        const idx = dates.indexOf(d);
        if (idx === -1) continue;
        const x = xScale.getPixelForValue(idx);
        c.beginPath(); c.moveTo(x, top); c.lineTo(x, bottom); c.stroke();
      }
      c.restore();
    },
  };

  const titleLabel = _activePerfPeriod === 'ytd'
    ? 'Individual Holdings — YTD % Change'
    : `Individual Holdings — ${_PERF_PERIOD_LABELS[_activePerfPeriod]} % Change`;
  document.getElementById('holdingsChartTitle').textContent = titleLabel;

  if (holdingsChart) holdingsChart.destroy();

  holdingsChart = new Chart(document.getElementById('holdingsChart').getContext('2d'), {
    type:    'line',
    plugins: [monthGridPlugin],
    data:    { labels: dates, datasets },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            generateLabels(chart) {
              return chart.data.datasets.map((ds, i) => {
                const last = ds.lastPct;
                const sign = last >= 0 ? '+' : '';
                return {
                  text:        `${ds.label} (${sign}${last.toFixed(2)}%)`,
                  fillStyle:   ds.borderColor,
                  strokeStyle: ds.borderColor,
                  lineWidth:   0,
                  hidden:      !chart.getDatasetMeta(i).visible,
                  datasetIndex: i,
                };
              });
            },
          },
        },
        tooltip: {
          // Days before a holding was bought are null; leave them out.
          filter: item => item.parsed.y != null,
          callbacks: {
            title:      ctx => ctx[0].label,
            label:      ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`,
            labelColor: ctx => ({ borderColor: ctx.dataset.borderColor, backgroundColor: ctx.dataset.borderColor }),
          },
        },
      },
      scales: {
        x: {
          type: 'category',
          ticks: {
            autoSkip: false, maxRotation: 0,
            callback(val) {
              const d = this.getLabelForValue(val);
              if (!d || !monthStarts.has(d)) return null;
              return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
            },
          },
          grid: { display: false },
        },
        y: {
          ticks: { callback: v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%' },
          grid:  { color: '#f1f5f9' },
        },
      },
    },
  });

  card.style.display = '';
}

function renderMonthly(monthly) {
  if (!monthly || !monthly.length) {
    document.getElementById('monthlyCard').style.display = 'none';
    return;
  }

  document.getElementById('monthlyBody').innerHTML = [...monthly].reverse().map(m => {
    const pos = m.gain >= 0;
    const cls = pos ? 'text-success' : 'text-danger';
    return `<tr>
      <td>${m.month}</td>
      <td class="text-right">${fmt(m.start)}</td>
      <td class="text-right">${fmt(m.end)}</td>
      <td class="text-right">${fmtSigned(m.net_flow || 0)}</td>
      <td class="text-right ${cls}">${pos ? '+' : ''}${fmt(m.gain)}</td>
      <td class="text-right ${cls}">${pos ? '+' : ''}${m.gain_pct.toFixed(2)}%</td>
    </tr>`;
  }).join('');

  document.getElementById('monthlyCard').style.display = '';
}

// ── Benchmark comparison ──────────────────────────────────────────────────────

function setBenchmark(ticker) {
  _activeBenchmark = ticker;
  const sliced = _slicePerfData(_perfFullData, _activePerfPeriod);
  renderBenchmarkChart(
    sliced.dates,
    _twrIndex(sliced.dates, sliced.values, _perfFullData.cash_flows || []),
  );
}

async function _fetchBenchmark(ticker) {
  const statusEl = document.getElementById('benchmarkStatus');
  const seq = ++_benchmarkSeq;
  statusEl.textContent = `Fetching ${BENCHMARK_LABELS[ticker] || ticker}…`;

  try {
    const res  = await fetch(`/api/lookup/${encodeURIComponent(ticker)}`);
    const data = await res.json();
    if (seq !== _benchmarkSeq) return;  // a newer selection has since taken over

    if (!res.ok) {
      statusEl.textContent = data.error || `Failed to load ${ticker}.`;
      return;
    }
    _benchmarkCache[ticker] = { dates: data.dates, prices: data.prices };
    statusEl.textContent = '';
    if (_activeBenchmark === ticker) {
      const sliced = _slicePerfData(_perfFullData, _activePerfPeriod);
      renderBenchmarkChart(
        sliced.dates,
        _twrIndex(sliced.dates, sliced.values, _perfFullData.cash_flows || []),
      );
    }
  } catch (err) {
    if (seq !== _benchmarkSeq) return;
    statusEl.textContent = `Request failed: ${err.message}`;
  }
}

// Benchmark prices only exist for trading days; carry the last known close
// forward onto the portfolio's calendar-day dates (weekends/holidays) so the
// two series line up point-for-point.
function _alignBenchmark(portfolioDates, benchDates, benchPrices) {
  const priceByDate = {};
  benchDates.forEach((d, i) => { priceByDate[d] = benchPrices[i]; });

  const aligned = [];
  let last = null;
  for (const d of portfolioDates) {
    if (priceByDate[d] != null) last = priceByDate[d];
    aligned.push(last);
  }
  // Back-fill any leading gap (portfolio history starts before the benchmark's
  // earliest trading day) with the first price we do have.
  const firstKnown = aligned.find(v => v != null);
  return aligned.map(v => (v == null ? firstKnown : v));
}

function renderBenchmarkChart(dates, values) {
  const card     = document.getElementById('benchmarkChartCard');
  const statusEl = document.getElementById('benchmarkStatus');

  if (!_activeBenchmark) {
    card.style.display = 'none';
    if (benchmarkChart) { benchmarkChart.destroy(); benchmarkChart = null; }
    return;
  }

  card.style.display = '';

  const cached = _benchmarkCache[_activeBenchmark];
  if (!cached) {
    if (benchmarkChart) { benchmarkChart.destroy(); benchmarkChart = null; }
    _fetchBenchmark(_activeBenchmark);
    return;
  }

  if (!dates.length || !values.length || cached.dates == null || !cached.dates.length) {
    statusEl.textContent = 'No overlapping price history to compare.';
    if (benchmarkChart) { benchmarkChart.destroy(); benchmarkChart = null; }
    return;
  }

  const alignedBench = _alignBenchmark(dates, cached.dates, cached.prices);
  const portfolioBase = values[0];
  const benchBase     = alignedBench[0];

  const portfolioPct = values.map(v => portfolioBase ? +((v - portfolioBase) / portfolioBase * 100).toFixed(4) : 0);
  const benchPct     = alignedBench.map(v => benchBase ? +((v - benchBase) / benchBase * 100).toFixed(4) : 0);

  statusEl.textContent = 'Portfolio line is investment return, with deposits and withdrawals removed.';

  const label = BENCHMARK_LABELS[_activeBenchmark] || _activeBenchmark;
  const titleLabel = _activePerfPeriod === 'ytd'
    ? `Portfolio vs ${label} — YTD % Change`
    : `Portfolio vs ${label} — ${_PERF_PERIOD_LABELS[_activePerfPeriod]} % Change`;
  document.getElementById('benchmarkChartTitle').textContent = titleLabel;

  const monthStarts = new Set();
  const seenMonths  = new Set();
  for (const d of dates) {
    const ym = d.slice(0, 7);
    if (!seenMonths.has(ym)) { seenMonths.add(ym); monthStarts.add(d); }
  }

  const monthGridPlugin = {
    id: 'benchmarkMonthGrid',
    afterDraw(chart) {
      const xScale = chart.scales.x;
      const { top, bottom } = chart.chartArea;
      const c = chart.ctx;
      c.save();
      c.strokeStyle = 'rgba(100,116,139,0.35)';
      c.lineWidth   = 1;
      for (const d of monthStarts) {
        const idx = dates.indexOf(d);
        if (idx === -1) continue;
        const x = xScale.getPixelForValue(idx);
        c.beginPath(); c.moveTo(x, top); c.lineTo(x, bottom); c.stroke();
      }
      c.restore();
    },
  };

  if (benchmarkChart) benchmarkChart.destroy();

  benchmarkChart = new Chart(document.getElementById('benchmarkChart').getContext('2d'), {
    type:    'line',
    plugins: [monthGridPlugin],
    data: {
      labels: dates,
      datasets: [
        {
          label:            'Portfolio',
          data:             portfolioPct,
          borderColor:      '#2563eb',
          borderWidth:      2,
          backgroundColor:  'transparent',
          fill:             false,
          pointRadius:      0,
          pointHoverRadius: 4,
          tension:          0.3,
        },
        {
          label:            label,
          data:             benchPct,
          borderColor:      '#94a3b8',
          borderWidth:      2,
          borderDash:       [4, 3],
          backgroundColor:  'transparent',
          fill:             false,
          pointRadius:      0,
          pointHoverRadius: 4,
          tension:          0.3,
        },
      ],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            generateLabels(chart) {
              return chart.data.datasets.map((ds, i) => {
                const last = ds.data[ds.data.length - 1];
                const sign = last >= 0 ? '+' : '';
                return {
                  text:        `${ds.label} (${sign}${last.toFixed(2)}%)`,
                  fillStyle:   ds.borderColor,
                  strokeStyle: ds.borderColor,
                  lineWidth:   0,
                  hidden:      !chart.getDatasetMeta(i).visible,
                  datasetIndex: i,
                };
              });
            },
          },
        },
        tooltip: {
          callbacks: {
            title:      ctx => ctx[0].label,
            label:      ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`,
            labelColor: ctx => ({ borderColor: ctx.dataset.borderColor, backgroundColor: ctx.dataset.borderColor }),
          },
        },
      },
      scales: {
        x: {
          type: 'category',
          ticks: {
            autoSkip: false, maxRotation: 0,
            callback(val) {
              const d = this.getLabelForValue(val);
              if (!d || !monthStarts.has(d)) return null;
              return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
            },
          },
          grid: { display: false },
        },
        y: {
          ticks: { callback: v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%' },
          grid:  { color: '#f1f5f9' },
        },
      },
    },
  });
}

// ── Select / unselect all datasets ───────────────────────────────────────────

function selectAllCategories(visible) {
  if (!categoriesChart) return;
  categoriesChart.data.datasets.forEach((_, i) =>
    categoriesChart.setDatasetVisibility(i, visible)
  );
  categoriesChart.update();
}

function selectAllHoldings(visible) {
  if (!holdingsChart) return;
  holdingsChart.data.datasets.forEach((_, i) =>
    holdingsChart.setDatasetVisibility(i, visible)
  );
  holdingsChart.update();
}

function renderCashFlows(dates, flows) {
  const card = document.getElementById('cashFlowCard');
  if (!card) return;
  card.style.display = '';
  const start = dates && dates.length ? dates[0] : '';
  const end = dates && dates.length ? dates[dates.length - 1] : '';
  const rows = flows || [];
  const outside = start
    ? rows.filter(f => f.flow_date < start || f.flow_date > end).length
    : 0;
  const msg = document.getElementById('cashFlowMsg');
  if (msg && !msg.classList.contains('text-danger')) {
    msg.className = 'text-muted';
    msg.textContent = outside
      ? `${outside} cash flow${outside === 1 ? ' is' : 's are'} outside this period, so ${outside === 1 ? 'it is' : 'they are'} not part of the gain above.`
      : '';
  }
  const body = document.getElementById('cashFlowBody');
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding:1rem">
      No cash flows yet.</td></tr>`;
    return;
  }
  body.innerHTML = [...rows].reverse().map(f => {
    const account = [f.owner, f.account_type].filter(Boolean).join(' · ') || '—';
    const source = FLOW_SOURCES[f.source] || f.source || '';
    const note = f.note ? esc(f.note) : esc(source);
    const sourceSuffix = f.note && source
      ? ` <span class="text-muted">(${esc(source)})</span>`
      : '';
    return `<tr>
      <td>${esc(f.flow_date)}</td>
      <td>${esc(account)}</td>
      <td>${esc(f.ticker || '—')}</td>
      <td>${note}${sourceSuffix}</td>
      <td class="text-right">${fmtSigned(Number(f.amount))}</td>
      <td class="text-right">
        <button type="button" class="btn btn-sm btn-danger" onclick="deleteCashFlow(${Number(f.id)})">Delete</button>
      </td>
    </tr>`;
  }).join('');
}

async function addCashFlow(event) {
  event.preventDefault();
  const msg = document.getElementById('cashFlowMsg');
  msg.className = '';
  msg.textContent = '';
  const body = {
    flow_date: document.getElementById('cashFlowDate').value,
    amount: document.getElementById('cashFlowAmount').value,
    owner: document.getElementById('cashFlowOwner').value,
    account_type: document.getElementById('cashFlowAccount').value,
    ticker: document.getElementById('cashFlowTicker').value,
    note: document.getElementById('cashFlowNote').value,
  };
  try {
    const created = await apiFetch('/api/cash-flows', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    _perfFullData.cash_flows = _perfFullData.cash_flows || [];
    _perfFullData.cash_flows.push(created);
    _perfFullData.cash_flows.sort((a, b) => a.flow_date.localeCompare(b.flow_date) || a.id - b.id);
    document.getElementById('cashFlowAmount').value = '';
    document.getElementById('cashFlowTicker').value = '';
    document.getElementById('cashFlowNote').value = '';
    setPerfPeriod(_activePerfPeriod);
  } catch (err) {
    msg.className = 'text-danger';
    msg.textContent = err.message;
  }
}

async function deleteCashFlow(id) {
  const msg = document.getElementById('cashFlowMsg');
  msg.className = '';
  msg.textContent = '';
  try {
    await apiFetch('/api/cash-flows/' + id, { method: 'DELETE' });
    _perfFullData.cash_flows = (_perfFullData.cash_flows || []).filter(f => f.id !== id);
    setPerfPeriod(_activePerfPeriod);
  } catch (err) {
    msg.className = 'text-danger';
    msg.textContent = err.message;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('cashFlowForm');
  if (form) form.addEventListener('submit', addCashFlow);
  loadPerformance();
});
