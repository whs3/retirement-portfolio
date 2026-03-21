'use strict';

let lookupChart  = null;
let indicesChart = null;

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

    results.forEach((data, i) => {
      const s    = INDEX_SYMBOLS[i];
      const isUp = data.change >= 0;
      const sign = isUp ? '+' : '';
      document.getElementById(`indexStats_${i}`).innerHTML = `
        <div style="font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em">${esc(s.label)}</div>
        <div style="font-size:1.4rem;font-weight:700;color:${s.color}">${fmtPrice(data.current_price)}</div>
        <div style="font-size:0.9rem;font-weight:600" class="${isUp ? 'text-success' : 'text-danger'}">${sign}${fmtPrice(data.change)} (${sign}${data.change_pct.toFixed(2)}%)</div>`;
    });

    renderIndicesChart(results);

  } catch (err) {
    statusEl.classList.add('alert-danger');
    statusEl.textContent = `Failed to load indices: ${err.message}`;
  }
}

function renderIndicesChart(results) {
  // Align to common trading days
  const dateSets    = results.map(d => new Set(d.dates));
  const commonDates = results[0].dates.filter(d => dateSets.every(s => s.has(d)));

  // Normalize each series to % change from first common date
  const datasets = results.map((data, i) => {
    const s        = INDEX_SYMBOLS[i];
    const priceMap = new Map(data.dates.map((d, j) => [d, data.prices[j]]));
    const prices   = commonDates.map(d => priceMap.get(d));
    const base     = prices[0];
    return {
      label:           s.label,
      data:            prices.map(p => ((p - base) / base) * 100),
      borderColor:     s.color,
      borderWidth:     2,
      backgroundColor: 'transparent',
      fill:            false,
      pointRadius:     0,
      pointHoverRadius: 4,
      tension:         0.3,
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

  const status  = document.getElementById('statusMsg');
  const results = document.getElementById('resultsSection');

  status.className     = 'alert';
  status.textContent   = `Fetching data for ${ticker}…`;
  status.style.display = 'block';
  results.style.display = 'none';

  try {
    const res  = await fetch(`/api/lookup/${encodeURIComponent(ticker)}`);
    const data = await res.json();

    if (!res.ok) {
      status.classList.add('alert-danger');
      status.textContent = data.error ?? `Could not load data for ${ticker}.`;
      return;
    }

    status.style.display = 'none';
    renderResults(data);

  } catch (err) {
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
  document.getElementById('chartTitle').textContent   = `${data.symbol} — Price, Past 12 Months`;

  document.getElementById('currentPrice').textContent = fmtPrice(data.current_price);

  const changeEl = document.getElementById('priceChange');
  changeEl.textContent = `${sign}${fmtPrice(data.change)} (${sign}${data.change_pct.toFixed(2)}%)`;
  changeEl.className   = cls;

  document.getElementById('week52High').textContent =
    data.week52_high != null ? fmtPrice(data.week52_high) : '—';
  document.getElementById('week52Low').textContent =
    data.week52_low  != null ? fmtPrice(data.week52_low)  : '—';

  renderChart(data.symbol, data.dates, data.prices);
  renderHoldings(data);

  document.getElementById('resultsSection').style.display = '';
}

function renderChart(symbol, dates, prices) {
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
