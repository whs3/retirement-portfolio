'use strict';

let perfChart       = null;
let categoriesChart = null;
let holdingsChart   = null;
let _perfFullData = null;
let _activePerfPeriod = '12m';

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
  '3m':  '3-Month Gain / Loss',
  '6m':  '6-Month Gain / Loss',
  '12m': '12-Month Gain / Loss',
  'ytd': 'YTD Gain / Loss',
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

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadPerformance() {
  const loading = document.getElementById('loadingMsg');
  loading.className     = 'alert';
  loading.textContent   = 'Fetching 12 months of price history — this may take a moment…';
  loading.style.display = 'block';

  ['summaryCards','perfPeriodRow','chartCard','categoriesChartCard','holdingsChartCard','monthlyCard','untrackedNotice'].forEach(id => {
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
      'As of ' + new Date().toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });

    _perfFullData = data;
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
  const sliced  = _slicePerfData(_perfFullData, period);
  const summary = _computeSummary(sliced.values, _perfFullData.summary.end_value);
  renderSummary(summary, period);
  renderChart(sliced.dates, sliced.values);
  renderCategoriesChart(sliced.dates, sliced.categories_series || []);
  renderHoldingsChart(sliced.dates, sliced.holdings_series || []);
  renderMonthly(_filterMonthly(_perfFullData.monthly, sliced.dates));
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
    holdings_series:   (data.holdings_series   || []).map(h => ({ ...h, values: h.values.slice(idx) })),
    categories_series: (data.categories_series || []).map(c => ({ ...c, values: c.values.slice(idx) })),
  };
}

function _computeSummary(values, currentEndValue) {
  if (!values.length) return {};
  const startVal = values[0];
  const gain     = currentEndValue - startVal;
  return {
    start_value: startVal,
    end_value:   currentEndValue,
    gain:        gain,
    gain_pct:    startVal ? (gain / startVal * 100) : 0,
    peak_value:  Math.max(...values),
  };
}

function _filterMonthly(monthly, slicedDates) {
  if (!monthly || !slicedDates.length) return monthly || [];
  const startYM = slicedDates[0].slice(0, 7);  // "YYYY-MM"
  const MONTHS  = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return monthly.filter(m => {
    const [mon, yr] = m.month.split(' ');
    const monthNum  = String(MONTHS.indexOf(mon) + 1).padStart(2, '0');
    return `${yr}-${monthNum}` >= startYM;
  });
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderSummary(s, period) {
  if (!s || s.start_value == null) return;

  const pos = s.gain >= 0;
  document.getElementById('startValueLabel').textContent = _PERIOD_START_LABELS[period] || 'Value at Start';
  document.getElementById('gainLabel').textContent       = _PERIOD_GAIN_LABELS[period]  || 'Period Gain / Loss';

  document.getElementById('startValue').textContent = fmt(s.start_value);
  document.getElementById('endValue').textContent   = fmt(s.end_value);
  document.getElementById('peakValue').textContent  = fmt(s.peak_value);

  const gainEl = document.getElementById('gainValue');
  const pctEl  = document.getElementById('gainPct');
  gainEl.textContent = (pos ? '+' : '') + fmt(s.gain);
  gainEl.className   = 'card-value ' + (pos ? 'text-success' : 'text-danger');
  pctEl.textContent  = (pos ? '+' : '') + s.gain_pct.toFixed(2) + '%';
  pctEl.className    = 'card-sub '    + (pos ? 'text-success' : 'text-danger');

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

  const titleLabel = _activePerfPeriod === 'ytd'
    ? 'Portfolio Value by Category — YTD'
    : `Portfolio Value by Category — ${_PERF_PERIOD_LABELS[_activePerfPeriod]}`;
  document.getElementById('categoriesChartTitle').textContent = titleLabel;

  if (categoriesChart) categoriesChart.destroy();

  categoriesChart = new Chart(document.getElementById('categoriesChart').getContext('2d'), {
    type:    'line',
    plugins: [monthGridPlugin],
    data:    { labels: dates, datasets },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
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

  const datasets = holdingsSeries.map((h, i) => {
    const base = h.values[0] || 1;
    return {
      label:            h.ticker,
      data:             h.values.map(v => +((v - base) / base * 100).toFixed(4)),
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
        legend: { display: true, position: 'top' },
        tooltip: {
          callbacks: {
            title: ctx => ctx[0].label,
            label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`,
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
      <td class="text-right ${cls}">${pos ? '+' : ''}${fmt(m.gain)}</td>
      <td class="text-right ${cls}">${pos ? '+' : ''}${m.gain_pct.toFixed(2)}%</td>
    </tr>`;
  }).join('');

  document.getElementById('monthlyCard').style.display = '';
}

document.addEventListener('DOMContentLoaded', loadPerformance);
