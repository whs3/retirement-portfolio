'use strict';

let lookupChart   = null;
let indicesChart  = null;
let _lookupSeq    = 0;   // incremented on every lookup; stale responses are ignored

const _PERIOD_LABELS  = { 1: '1 Month', 3: '3 Months', 6: '6 Months', ytd: 'YTD', 12: '12 Months' };
const _CHANGE_LABELS  = { 1: '1-Month Change', 3: '3-Month Change', 6: '6-Month Change', ytd: 'YTD Change', 12: '12-Month Change' };

// ── Market Indices (auto-loaded on page open) ─────────────────────────────────

const INDEX_SYMBOLS = [
  { symbol: '^GSPC', label: 'S&P 500',  color: '#2563eb' },
  { symbol: '^IXIC', label: 'NASDAQ',   color: '#d97706' },
];

async function loadMarketIndices() {
  const statusEl  = document.getElementById('indicesStatus');
  const sectionEl = document.getElementById('indicesSection');

  statusEl.className   = 'alert';
  statusEl.textContent = 'Loading market indices…';
  statusEl.style.display = 'block';

  try {
    const results = await Promise.all(
      INDEX_SYMBOLS.map(s =>
        fetch(`/api/lookup/${encodeURIComponent(s.symbol)}`).then(r => r.json())
      )
    );

    statusEl.style.display = 'none';
    sectionEl.style.display = '';

    renderIndicesChart(results);

  } catch (err) {
    statusEl.classList.add('alert-danger');
    statusEl.textContent = `Failed to load indices: ${err.message}`;
  }
}

let _indicesFullResults  = null;
let _activeIndicesPeriod = 12;

function renderIndicesChart(results) {
  _indicesFullResults  = results;
  _activeIndicesPeriod = 12;
  _drawIndicesChart(results, 12);
  document.getElementById('indicesPeriodBtns').style.display = '';
  _updateIndicesPeriodBtns();
  _updateIndexStats(results, 12);
}

function setIndicesPeriod(months) {
  if (!_indicesFullResults) return;
  _activeIndicesPeriod = months;
  _drawIndicesChart(_indicesFullResults, months);
  _updateIndicesPeriodBtns();
  _updateIndexStats(_indicesFullResults, months);
}

function _updateIndexStats(results, months) {
  // Find the cutoff date for the selected period (same logic as _drawIndicesChart)
  const dateSets    = results.map(d => new Set(d.dates));
  let   commonDates = results[0].dates.filter(d => dateSets.every(s => s.has(d)));

  let cutoffStr = null;
  if (months !== 12) {
    if (months === 'ytd') {
      const year = new Date(commonDates[commonDates.length - 1] + 'T00:00:00').getFullYear();
      cutoffStr = `${year}-01-01`;
    } else {
      const last   = new Date(commonDates[commonDates.length - 1] + 'T00:00:00');
      const cutoff = new Date(last);
      cutoff.setMonth(cutoff.getMonth() - months);
      cutoffStr = cutoff.toISOString().slice(0, 10);
    }
  }
  if (cutoffStr) {
    const idx = commonDates.findIndex(d => d >= cutoffStr);
    if (idx !== -1) commonDates = commonDates.slice(idx);
  }

  results.forEach((data, i) => {
    const s        = INDEX_SYMBOLS[i];
    const priceMap = new Map(data.dates.map((d, j) => [d, data.prices[j]]));
    const startPrice   = priceMap.get(commonDates[0]);
    const currentPrice = data.current_price;
    const change       = currentPrice - startPrice;
    const changePct    = (change / startPrice) * 100;
    const isUp         = change >= 0;
    const sign         = isUp ? '+' : '';
    document.getElementById(`indexStats_${i}`).innerHTML = `
      <div style="font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em">${esc(s.label)}</div>
      <div style="font-size:1.4rem;font-weight:700;color:${s.color}">${fmtPrice(currentPrice)}</div>
      <div style="font-size:0.9rem;font-weight:600" class="${isUp ? 'text-success' : 'text-danger'}">${sign}${fmtPrice(change)} (${sign}${changePct.toFixed(2)}%)</div>`;
  });
}

function _updateIndicesPeriodBtns() {
  [1, 3, 6, 'ytd', 12].forEach(m => {
    const id  = `indicesBtn${m === 'ytd' ? 'YTD' : m + 'M'}`;
    const btn = document.getElementById(id);
    if (!btn) return;
    const active = m === _activeIndicesPeriod;
    btn.style.background = active ? 'var(--primary, #2563eb)' : 'transparent';
    btn.style.color      = active ? '#fff' : 'var(--text-muted, #64748b)';
    btn.style.fontWeight = active ? '600' : '400';
  });
  const label = _activeIndicesPeriod === 'ytd'
    ? 'Market Indices — YTD'
    : `Market Indices — Past ${_PERIOD_LABELS[_activeIndicesPeriod]}`;
  document.getElementById('indicesChartTitle').textContent = label;
}

function _drawIndicesChart(results, months) {
  // Align to common trading days (full 12-month intersection)
  const dateSets    = results.map(d => new Set(d.dates));
  let   commonDates = results[0].dates.filter(d => dateSets.every(s => s.has(d)));

  // Slice to selected period
  if (months !== 12) {
    let cutoffStr;
    if (months === 'ytd') {
      const year = new Date(commonDates[commonDates.length - 1] + 'T00:00:00').getFullYear();
      cutoffStr = `${year}-01-01`;
    } else {
      const last   = new Date(commonDates[commonDates.length - 1] + 'T00:00:00');
      const cutoff = new Date(last);
      cutoff.setMonth(cutoff.getMonth() - months);
      cutoffStr = cutoff.toISOString().slice(0, 10);
    }
    const idx = commonDates.findIndex(d => d >= cutoffStr);
    if (idx !== -1) commonDates = commonDates.slice(idx);
  }

  // Normalize each series to % change from the first date in the sliced window
  const datasets = results.map((data, i) => {
    const s        = INDEX_SYMBOLS[i];
    const priceMap = new Map(data.dates.map((d, j) => [d, data.prices[j]]));
    const prices   = commonDates.map(d => priceMap.get(d));
    const base     = prices[0];
    return {
      label:            s.label,
      data:             prices.map(p => ((p - base) / base) * 100),
      borderColor:      s.color,
      borderWidth:      2,
      backgroundColor:  'transparent',
      fill:             false,
      pointRadius:      0,
      pointHoverRadius: 4,
      tension:          0.3,
    };
  });

  // Month boundary markers
  const monthStarts = new Set();
  const seenMonths  = new Set();
  for (const d of commonDates) {
    const ym = d.slice(0, 7);
    if (!seenMonths.has(ym)) { seenMonths.add(ym); monthStarts.add(d); }
  }

  const monthGridPlugin = {
    id: 'indicesMonthGrid',
    afterDraw(chart) {
      const xScale = chart.scales.x;
      const { top, bottom } = chart.chartArea;
      const c = chart.ctx;
      c.save();
      c.strokeStyle = 'rgba(100,116,139,0.35)';
      c.lineWidth   = 1;
      for (const d of monthStarts) {
        const idx = commonDates.indexOf(d);
        if (idx === -1) continue;
        const x = xScale.getPixelForValue(idx);
        c.beginPath(); c.moveTo(x, top); c.lineTo(x, bottom); c.stroke();
      }
      c.restore();
    },
  };

  const canvas = document.getElementById('indicesChart');
  if (indicesChart) indicesChart.destroy();

  indicesChart = new Chart(canvas.getContext('2d'), {
    type:    'line',
    plugins: [monthGridPlugin],
    data:    { labels: commonDates, datasets },
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
              return chart.data.datasets.map((ds, i) => ({
                text:         ds.label,
                fillStyle:    ds.borderColor,
                strokeStyle:  ds.borderColor,
                lineWidth:    0,
                hidden:       !chart.getDatasetMeta(i).visible,
                datasetIndex: i,
              }));
            },
          },
        },
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
            autoSkip:    false,
            maxRotation: 0,
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

function fmtPrice(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(n);
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Portfolio dropdown ────────────────────────────────────────────────────────

async function loadPortfolioTickers() {
  const res      = await fetch('/api/holdings');
  const holdings = await res.json();

  // Unique tickers with names, sorted alphabetically by ticker
  const seen = new Map();
  for (const h of holdings) {
    if (h.ticker && !seen.has(h.ticker)) seen.set(h.ticker, h.name);
  }
  const sorted = [...seen.entries()].sort((a, b) => a[0].localeCompare(b[0]));

  const sel = document.getElementById('portfolioSelect');
  for (const [ticker, name] of sorted) {
    const opt = document.createElement('option');
    opt.value       = ticker;
    opt.textContent = `${ticker} — ${name}`;
    sel.appendChild(opt);
  }

  sel.addEventListener('change', () => {
    if (sel.value) {
      document.getElementById('tickerInput').value = '';
      lookupTicker(sel.value);
    }
  });
}

// ── Lookup ────────────────────────────────────────────────────────────────────

async function lookupTicker(symbol) {
  const input  = document.getElementById('tickerInput');
  const ticker = (symbol || input.value).trim().toUpperCase();
  if (!ticker) { alert('Enter a ticker symbol first.'); return; }

  const seq     = ++_lookupSeq;   // capture sequence number for this request
  const status  = document.getElementById('statusMsg');
  const results = document.getElementById('resultsSection');

  status.className     = 'alert';
  status.textContent   = `Fetching data for ${ticker}…`;
  status.style.display = 'block';
  results.style.display = 'none';
  document.getElementById('analystSection').style.display = 'none';
  document.getElementById('fundSection').style.display = 'none';

  try {
    const res  = await fetch(`/api/lookup/${encodeURIComponent(ticker)}`);
    const data = await res.json();

    if (seq !== _lookupSeq) return;   // a newer lookup has started — discard this response

    if (!res.ok) {
      status.classList.add('alert-danger');
      status.textContent = data.error ?? `Could not load data for ${ticker}.`;
      return;
    }

    status.style.display = 'none';
    renderResults(data);

  } catch (err) {
    if (seq !== _lookupSeq) return;
    status.classList.add('alert-danger');
    status.textContent = `Request failed: ${err.message}`;
  }
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderResults(data) {
  const isUp = data.change >= 0;
  const cls  = isUp ? 'text-success' : 'text-danger';
  const sign = isUp ? '+' : '';

  document.getElementById('symbolName').textContent   = data.name;
  document.getElementById('symbolTicker').textContent = data.symbol;

  document.getElementById('currentPrice').textContent = fmtPrice(data.current_price);

  const changeEl = document.getElementById('priceChange');
  changeEl.textContent = `${sign}${fmtPrice(data.change)} (${sign}${data.change_pct.toFixed(2)}%)`;
  changeEl.className   = cls;

  document.getElementById('week52High').textContent =
    data.week52_high != null ? fmtPrice(data.week52_high) : '—';
  document.getElementById('week52Low').textContent =
    data.week52_low  != null ? fmtPrice(data.week52_low)  : '—';

  renderChart(data.symbol, data.dates, data.prices);
  try { renderAnalyst(data); } catch (e) {
    console.error('renderAnalyst error:', e);
    document.getElementById('analystSection').style.display = 'none';
  }
  try { renderFundInfo(data); } catch (e) {
    console.error('renderFundInfo error:', e);
    document.getElementById('fundSection').style.display = 'none';
  }
  renderHoldings(data);

  document.getElementById('resultsSection').style.display = '';
}

let _fullChartData  = null;   // {symbol, dates, prices}
let _activePeriod   = 12;

function renderChart(symbol, dates, prices) {
  _fullChartData = { symbol, dates, prices };
  _activePeriod  = 12;
  _drawChart(symbol, dates, prices);
  document.getElementById('periodBtns').style.display = '';
  _updatePeriodBtns();
  _updatePriceChangeStat(prices);
}

function setChartPeriod(months) {
  if (!_fullChartData) return;
  _activePeriod = months;
  const { dates, prices } = _sliceByMonths(_fullChartData.dates, _fullChartData.prices, months);
  _drawChart(_fullChartData.symbol, dates, prices);
  _updatePeriodBtns();
  _updatePriceChangeStat(prices);
}

function _updatePriceChangeStat(slicedPrices) {
  if (!slicedPrices || slicedPrices.length < 2) return;
  const startPrice   = slicedPrices[0];
  const currentPrice = slicedPrices[slicedPrices.length - 1];
  const change       = currentPrice - startPrice;
  const changePct    = (change / startPrice) * 100;
  const isUp         = change >= 0;
  const sign         = isUp ? '+' : '';

  const labelEl  = document.getElementById('priceChangeLabel');
  const changeEl = document.getElementById('priceChange');
  if (labelEl)  labelEl.textContent  = _CHANGE_LABELS[_activePeriod] ?? '12-Month Change';
  if (changeEl) {
    changeEl.textContent = `${sign}${fmtPrice(change)} (${sign}${changePct.toFixed(2)}%)`;
    changeEl.className   = isUp ? 'text-success' : 'text-danger';
  }
}

function _sliceByMonths(dates, prices, months) {
  if (months === 12) return { dates, prices };
  let cutoffStr;
  if (months === 'ytd') {
    const year = new Date(dates[dates.length - 1] + 'T00:00:00').getFullYear();
    cutoffStr = `${year}-01-01`;
  } else {
    const last   = new Date(dates[dates.length - 1] + 'T00:00:00');
    const cutoff = new Date(last);
    cutoff.setMonth(cutoff.getMonth() - months);
    cutoffStr = cutoff.toISOString().slice(0, 10);
  }
  const idx = dates.findIndex(d => d >= cutoffStr);
  return idx === -1 ? { dates, prices } : { dates: dates.slice(idx), prices: prices.slice(idx) };
}

function _updatePeriodBtns() {
  [1, 3, 6, 'ytd', 12].forEach(m => {
    const id  = `btn${m === 'ytd' ? 'YTD' : m + 'M'}`;
    const btn = document.getElementById(id);
    if (!btn) return;
    const active = m === _activePeriod;
    btn.style.background = active ? 'var(--primary, #2563eb)' : 'transparent';
    btn.style.color      = active ? '#fff' : 'var(--text-muted, #64748b)';
    btn.style.fontWeight = active ? '600' : '400';
  });
  if (_fullChartData) {
    const label = _activePeriod === 'ytd'
      ? `${_fullChartData.symbol} — Price, YTD`
      : `${_fullChartData.symbol} — Price, Past ${_PERIOD_LABELS[_activePeriod]}`;
    document.getElementById('chartTitle').textContent = label;
  }
}

function _drawChart(symbol, dates, prices) {
  const canvas = document.getElementById('lookupChart');
  const ctx    = canvas.getContext('2d');

  const isUp  = prices[prices.length - 1] >= prices[0];
  const color = isUp ? '#16a34a' : '#dc2626';

  // First trading day of each month
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

  if (lookupChart) lookupChart.destroy();

  lookupChart = new Chart(ctx, {
    type:    'line',
    plugins: [monthGridPlugin],
    data: {
      labels: dates,
      datasets: [{
        data:             prices,
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
            label: ctx => ` ${symbol}: ${fmtPrice(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          type: 'category',
          ticks: {
            autoSkip:    false,
            maxRotation: 0,
            callback(val) {
              const d = this.getLabelForValue(val);
              if (!d || !monthStarts.has(d)) return null;
              return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
            },
          },
          grid: { display: false },
        },
        y: {
          ticks: { callback: v => fmtPrice(v) },
          grid:  { color: '#f1f5f9' },
        },
      },
    },
  });
}

// ── Analyst recommendations ───────────────────────────────────────────────────

const _REC_META = {
  strongbuy:  { label: 'Strong Buy',  bg: '#16a34a', fg: '#fff', pos: 0   },
  buy:        { label: 'Buy',         bg: '#4ade80', fg: '#14532d', pos: 25  },
  hold:       { label: 'Hold',        bg: '#fbbf24', fg: '#78350f', pos: 50  },
  sell:       { label: 'Sell',        bg: '#f87171', fg: '#7f1d1d', pos: 75  },
  strongsell: { label: 'Strong Sell', bg: '#dc2626', fg: '#fff', pos: 100 },
};

function renderAnalyst(data) {
  const section = document.getElementById('analystSection');
  const a = data.analyst;

  if (!a || !a.recommendation) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';
  document.getElementById('fundSection').style.display = 'none';

  const meta  = _REC_META[a.recommendation] || { label: a.recommendation, bg: '#94a3b8', fg: '#fff', pos: 50 };
  const price = data.current_price;

  // Badge
  const badge = document.getElementById('analystBadge');
  badge.textContent        = meta.label;
  badge.style.background   = meta.bg;
  badge.style.color        = meta.fg;

  // Meta line
  document.getElementById('analystMeta').textContent =
    a.num_analysts ? `Based on ${a.num_analysts} analyst${a.num_analysts !== 1 ? 's' : ''}` : '';

  // Scale marker (mean: 1=strong buy, 5=strong sell → 0–100%)
  const mean = a.recommendation_mean != null ? Number(a.recommendation_mean) : null;
  const pct  = mean != null ? ((mean - 1) / 4) * 100 : meta.pos;
  document.getElementById('analystScaleMarker').style.left = `${Math.max(0, Math.min(100, pct))}%`;
  document.getElementById('analystScoreLabel').textContent =
    mean != null ? `Score ${mean.toFixed(2)} / 5` : '';

  // Price targets
  const targetsEl = document.getElementById('analystTargets');
  if (a.target_mean != null) {
    const tMean     = Number(a.target_mean);
    const upside    = price ? ((tMean - price) / price * 100) : null;
    const upsideCls = upside != null ? (upside >= 0 ? 'text-success' : 'text-danger') : '';
    const upsideTxt = upside != null ? ` <span class="${upsideCls}">(${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%)</span>` : '';
    targetsEl.innerHTML = `
      <div style="font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:0.4rem">12-Month Price Targets</div>
      <table style="border-collapse:collapse;font-size:0.9rem">
        <tr><td style="color:var(--text-muted);padding-right:1.2rem">Mean</td>
            <td><strong>${fmtPrice(tMean)}</strong>${upsideTxt}</td></tr>
        ${a.target_high != null ? `<tr><td style="color:var(--text-muted);padding-right:1.2rem">High</td><td>${fmtPrice(Number(a.target_high))}</td></tr>` : ''}
        ${a.target_low  != null ? `<tr><td style="color:var(--text-muted);padding-right:1.2rem">Low</td><td>${fmtPrice(Number(a.target_low))}</td></tr>` : ''}
      </table>`;
  } else {
    targetsEl.innerHTML = '';
  }

  // Summary narrative
  const summaryEl = document.getElementById('analystSummary');
  const parts = [];
  if (a.num_analysts && a.recommendation) {
    parts.push(`${a.num_analysts} analyst${a.num_analysts !== 1 ? 's' : ''} currently cover <strong>${esc(data.symbol)}</strong>, with a consensus rating of <strong>${meta.label}</strong>.`);
  }
  if (a.target_mean != null && price) {
    const upside = ((Number(a.target_mean) - price) / price * 100);
    const dir    = upside >= 0 ? 'upside' : 'downside';
    const cls    = upside >= 0 ? 'text-success' : 'text-danger';
    parts.push(`The mean 12-month price target of <strong>${fmtPrice(a.target_mean)}</strong> implies <span class="${cls}">${Math.abs(upside).toFixed(1)}% ${dir}</span> from the current price of ${fmtPrice(price)}.`);
  }
  if (a.target_high != null && a.target_low != null) {
    parts.push(`Analyst targets range from ${fmtPrice(a.target_low)} to ${fmtPrice(a.target_high)}.`);
  }
  summaryEl.innerHTML = parts.join(' ');

  // Recent actions table
  const actionsWrap = document.getElementById('analystActionsWrap');
  const actionsBody = document.getElementById('analystActionsBody');
  if (a.recent_actions && a.recent_actions.length) {
    actionsBody.innerHTML = a.recent_actions.map(r => {
      const toGrade = esc(r.to_grade || '—');
      const fromGrade = esc(r.from_grade || '—');
      const gradeChanged = r.from_grade && r.to_grade && r.from_grade !== r.to_grade;
      const gradeCls = gradeChanged
        ? (_REC_META[r.to_grade.toLowerCase().replace(/ /g,'')] ? '' : '')
        : 'text-muted';
      const pt = r.price_target != null ? fmtPrice(r.price_target) : '—';
      return `<tr>
        <td class="text-muted">${esc(r.date)}</td>
        <td><strong>${esc(r.firm)}</strong></td>
        <td>${esc(r.action || '—')}</td>
        <td class="text-muted">${fromGrade}</td>
        <td class="${gradeChanged ? 'text-success' : ''}">${toGrade}</td>
        <td class="text-right">${pt}</td>
      </tr>`;
    }).join('');
    actionsWrap.style.display = '';
  } else {
    actionsWrap.style.display = 'none';
  }
}

// ── Fund info (ETF / mutual fund) ─────────────────────────────────────────────

function renderFundInfo(data) {
  const section = document.getElementById('fundSection');
  const fi = data.fund_info;

  if (!fi || !Object.values(fi).some(v => v != null)) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';
  document.getElementById('analystSection').style.display = 'none';

  const fmtAUM = n => {
    if (n == null) return null;
    n = Number(n);
    if (n >= 1e12) return '$' + (n / 1e12).toFixed(2) + 'T';
    if (n >= 1e9)  return '$' + (n / 1e9).toFixed(2)  + 'B';
    if (n >= 1e6)  return '$' + (n / 1e6).toFixed(2)  + 'M';
    return '$' + n.toLocaleString();
  };

  // ytdReturn is already a % value; three/fiveYearReturn are ratios (×100 to get %)
  const fmtPct  = (n, isRatio) => n != null ? (isRatio ? (Number(n) * 100) : Number(n)).toFixed(2) + '%' : null;
  const retCls  = n => n != null ? (Number(n) >= 0 ? 'text-success' : 'text-danger') : '';

  const metrics = [
    ['Fund Family',     fi.fund_family ? esc(fi.fund_family) : null,       null],
    ['Category',        fi.category    ? esc(fi.category)    : null,       null],
    ['AUM',             fmtAUM(fi.total_assets),                            null],
    ['Net Expense Ratio', fmtPct(fi.expense_ratio, false),                 null],
    ['YTD Return',      fmtPct(fi.ytd_return, false),                      retCls(fi.ytd_return)],
    ['3-Year Avg',      fmtPct(fi.three_year_return, true),                retCls(fi.three_year_return)],
    ['5-Year Avg',      fmtPct(fi.five_year_return, true),                 retCls(fi.five_year_return)],
  ].filter(([, v]) => v != null);

  document.getElementById('fundMetrics').innerHTML = metrics.map(([label, value, cls]) => `
    <div>
      <div style="font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em">${label}</div>
      <div style="font-weight:600;font-size:0.95rem" class="${cls || ''}">${value}</div>
    </div>`).join('');

  const descEl = document.getElementById('fundDescription');
  descEl.textContent = fi.description || '';
  descEl.style.display = fi.description ? '' : 'none';

  // Benchmark / tracked index
  const benchEl = document.getElementById('fundBenchmark');
  const bm = fi.benchmark;
  if (bm && bm.name) {
    const fmtRet = (n, label) => {
      if (n == null) return '';
      const sign = n >= 0 ? '+' : '';
      const cls  = n >= 0 ? 'text-success' : 'text-danger';
      return `<span style="margin-left:1.2rem;font-size:0.85rem;color:var(--text-muted)">${label}: <span class="${cls}" style="font-weight:600">${sign}${Number(n).toFixed(2)}%</span></span>`;
    };
    const returns = fmtRet(bm.ytd_return, 'YTD') + fmtRet(bm.one_year_return, '1-Year');
    benchEl.innerHTML = `<strong>${esc(bm.name)}</strong>${returns}`;
    benchEl.style.display = '';
  } else {
    benchEl.style.display = 'none';
  }
}

function renderHoldings(data) {
  const section = document.getElementById('holdingsSection');
  if (!data.top_holdings || !data.top_holdings.length) {
    section.style.display = 'none';
    return;
  }

  const label = data.quote_type === 'mutualfund' ? 'Mutual Fund' : 'ETF';
  document.getElementById('holdingsTitle').textContent =
    `Top ${data.top_holdings.length} Holdings — ${data.name} (${label})`;

  document.getElementById('holdingsBody').innerHTML = data.top_holdings.map((h, i) => `
    <tr>
      <td class="text-muted">${i + 1}</td>
      <td><strong>${esc(h.symbol)}</strong></td>
      <td>${esc(h.name)}</td>
      <td class="text-right">${h.weight.toFixed(2)}%</td>
    </tr>`).join('');

  section.style.display = '';
}

// ── Enter key on search field ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadPortfolioTickers();
  loadMarketIndices();
  document.getElementById('tickerInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') lookupTicker();
  });
});
