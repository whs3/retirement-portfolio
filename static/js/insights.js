'use strict';

let sentimentChart = null;
let _insightsData = null;
let _sortCol = 'value';
let _sortDir = 'desc';

const RATING_LABELS = {
  'strong_buy': 'Strong Buy',
  'buy': 'Buy',
  'hold': 'Hold',
  'sell': 'Sell',
  'strong_sell': 'Strong Sell',
};

const RATING_COLORS = {
  'strong_buy': '#16a34a',
  'buy': '#4ade80',
  'hold': '#f59e0b',
  'sell': '#f87171',
  'strong_sell': '#dc2626',
  'none': '#94a3b8',
};

const ACTION_COLORS = {
  'add': '#16a34a',
  'trim': '#dc2626',
  'monitor': '#64748b',
};

function fmt(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function fmtPct(n) {
  if (n === null || n === undefined) return '—';
  const s = n >= 0 ? '+' : '';
  return s + n.toFixed(1) + '%';
}

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function setStatus(msg, isError = false) {
  const el = document.getElementById('statusMsg');
  if (!msg) {
    el.style.display = 'none';
    return;
  }
  el.style.display = 'block';
  el.className = 'alert ' + (isError ? 'alert-danger' : '');
  el.textContent = msg;
}

async function loadInsights() {
  setStatus('');
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  btn.textContent = 'Refreshing…';

  const body = document.getElementById('insightsBody');
  body.innerHTML = '<tr><td colspan="12" class="text-center text-muted">Fetching analyst data from Yahoo Finance…</td></tr>';

  try {
    const data = await apiFetch('/api/insights');

    _insightsData = data;
    renderAll(data);

    const now = new Date();
    document.getElementById('lastUpdated').textContent =
      'Updated ' + now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  } catch (err) {
    setStatus('Failed to load insights: ' + err.message, true);
    body.innerHTML = '<tr><td colspan="12" class="text-center text-danger">Failed to load data. Try refreshing.</td></tr>';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh Data';
  }
}

function refreshInsights() {
  loadInsights();
}

function renderAll(data) {
  renderMarketSnapshot(data.market || []);
  renderSummaryCards(data);
  renderFundStats(data.fund_stats || {});
  renderSentimentChart(data.sentiment_breakdown || []);
  renderRecommendations(data.recommendations || []);
  renderTable(data.holdings || []);
}

function renderMarketSnapshot(market) {
  const container = document.getElementById('marketSnapshot');
  if (!market.length) {
    container.innerHTML = '<div class="text-center text-muted" style="padding:0.5rem">No market data available.</div>';
    return;
  }

  container.innerHTML = market.map(m => {
    const ch = m.change_pct || 0;
    const cls = ch >= 0 ? 'text-success' : 'text-danger';
    const priceStr = m.price != null ? m.price.toLocaleString() : '—';
    return `
      <div style="background:#f8fafc;border:1px solid var(--border);border-radius:6px;padding:0.6rem 0.75rem">
        <div style="font-size:0.8rem;color:var(--text-muted);font-weight:600">${esc(m.name)}</div>
        <div style="font-size:1.15rem;font-weight:700;margin:0.15rem 0">${priceStr}</div>
        <div class="${cls}" style="font-size:0.9rem;font-weight:600">${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%</div>
      </div>
    `;
  }).join('');

  // Optional note for VIX
  const vix = market.find(x => x.symbol === '^VIX');
  const noteEl = document.getElementById('marketNote');
  if (vix && vix.price != null) {
    let note = `VIX at ${vix.price.toFixed(1)} — `;
    if (vix.price < 15) note += 'very low volatility.';
    else if (vix.price < 20) note += 'low volatility environment.';
    else if (vix.price < 30) note += 'moderate volatility.';
    else note += 'elevated / high volatility.';
    noteEl.textContent = note;
  } else {
    noteEl.textContent = '';
  }
}

function renderSummaryCards(data) {
  document.getElementById('summaryCards').style.display = '';

  document.getElementById('totalValue').textContent = fmt(data.portfolio?.total_value || 0);
  document.getElementById('coveredValue').textContent = fmt(data.portfolio?.covered_value || 0);

  const up = data.portfolio?.avg_upside_pct;
  const upEl = document.getElementById('avgUpside');
  upEl.textContent = up != null ? fmtPct(up) : '—';
  upEl.className = 'card-value ' + (up != null && up >= 0 ? 'text-success' : up != null ? 'text-danger' : '');

  document.getElementById('coveredCount').textContent = `${data.portfolio?.num_analyst_holdings || 0} / ${data.portfolio?.total_holdings || 0}`;
}

function renderFundStats(stats) {
  // Insert or update a small fund characteristics summary row (only meaningful for ETF-heavy portfolios)
  let el = document.getElementById('fundStatsRow');
  if (!el) {
    const container = document.getElementById('summaryCards');
    if (!container) return;
    el = document.createElement('div');
    el.id = 'fundStatsRow';
    el.style.cssText = 'grid-column: 1 / -1; display:flex; gap:1rem; flex-wrap:wrap; margin-top:0.5rem';
    container.parentNode.insertBefore(el, container.nextSibling);
  }

  const parts = [];
  if (stats.weighted_avg_expense != null) {
    const exp = stats.weighted_avg_expense;
    let cls = exp > 0.12 ? 'text-danger' : (exp < 0.06 ? 'text-success' : '');
    parts.push(`<div style="background:#f8fafc;border:1px solid var(--border);padding:0.35rem 0.6rem;border-radius:4px;font-size:0.85rem">
      <strong>Avg Expense:</strong> <span class="${cls}">${exp.toFixed(2)}%</span>
    </div>`);
  }
  if (stats.weighted_avg_pe != null) {
    const pe = stats.weighted_avg_pe;
    let cls = pe > 26 ? 'text-danger' : (pe < 18 ? 'text-success' : '');
    parts.push(`<div style="background:#f8fafc;border:1px solid var(--border);padding:0.35rem 0.6rem;border-radius:4px;font-size:0.85rem">
      <strong>Equity P/E (wgt):</strong> <span class="${cls}">${pe}</span>
    </div>`);
  }
  if (stats.high_expense_count > 0) {
    const val = stats.high_expense_value ? '$' + stats.high_expense_value.toLocaleString() : '';
    parts.push(`<div style="background:#f8fafc;border:1px solid var(--border);padding:0.35rem 0.6rem;border-radius:4px;font-size:0.85rem">
      <span class="text-danger">${stats.high_expense_count} holdings</span> &gt; ~0.15% expense ${val}
    </div>`);
  }

  if (parts.length) {
    el.innerHTML = parts.join('');
    el.style.display = '';
  } else {
    el.style.display = 'none';
  }
}

function renderSentimentChart(breakdown) {
  let canvas = document.getElementById('sentimentChart');

  // Always destroy any previous chart instance first
  if (sentimentChart) {
    sentimentChart.destroy();
    sentimentChart = null;
  }

  // Recovery: if a previous no-data state replaced/destroyed the canvas, recreate it
  if (!canvas) {
    const container = document.getElementById('sentimentChartContainer');
    if (container) {
      container.innerHTML = '<canvas id="sentimentChart"></canvas>';
      canvas = document.getElementById('sentimentChart');
    }
  }

  if (!canvas) {
    // Nothing we can do — avoid throwing
    return;
  }

  const parent = canvas.parentElement;
  // Clean up any stale "no data" message from previous render
  const oldMsg = parent.querySelector('.no-sentiment-msg');
  if (oldMsg) oldMsg.remove();

  const hasData = Array.isArray(breakdown) && breakdown.length > 0;

  if (!hasData) {
    canvas.style.display = 'none';

    const msg = document.createElement('p');
    msg.className = 'text-muted text-center no-sentiment-msg';
    msg.style.paddingTop = '2rem';
    msg.textContent = 'No analyst-rated holdings.';
    parent.appendChild(msg);
    return;
  }

  // We have data — make sure the canvas is visible
  canvas.style.display = '';

  const ctx = canvas.getContext('2d');

  const labels = breakdown.map(b => RATING_LABELS[b.rating] || b.rating);
  const values = breakdown.map(b => b.value);
  const colors = breakdown.map(b => RATING_COLORS[b.rating] || '#94a3b8');

  sentimentChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderWidth: 2,
      }],
    },
    options: {
      cutout: '60%',
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12 } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const total = values.reduce((a, b) => a + b, 0);
              const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : '0';
              return ` ${fmt(ctx.parsed)} (${pct}%)`;
            }
          }
        }
      }
    }
  });
}

function renderRecommendations(recs) {
  const el = document.getElementById('recommendationsList');
  if (!recs.length) {
    el.innerHTML = '<p class="text-muted">No specific recommendations at this time.</p>';
    return;
  }
  el.innerHTML = recs.map(r => `
    <div style="padding:0.4rem 0;border-bottom:1px solid #f1f5f9;font-size:0.92rem">
      • ${esc(r)}
    </div>
  `).join('');
}

function updateSortIndicators() {
  document.querySelectorAll('.sort-indicator').forEach(el => {
    el.textContent = '';
    if (el.dataset.col === _sortCol) {
      el.textContent = _sortDir === 'asc' ? '▲' : '▼';
    }
  });
}

function renderTable(holdings) {
  const body = document.getElementById('insightsBody');

  const filtered = (holdings || []).filter(h => (h.current_value || 0) > 0);
  if (!filtered.length) {
    body.innerHTML = '<tr><td colspan="12" class="text-center text-muted">No holdings found.</td></tr>';
    return;
  }

  // Sort
  const numericCols = ['value', 'upside', 'num', 'expense', 'pe', 'yield', 'beta'];
  const sorted = [...filtered].sort((a, b) => {
    let va = a[_sortCol], vb = b[_sortCol];

    if (numericCols.includes(_sortCol)) {
      // pull from fund when needed
      if (_sortCol === 'expense') { va = (a.fund && a.fund.expense_ratio) || 0; vb = (b.fund && b.fund.expense_ratio) || 0; }
      else if (_sortCol === 'pe') { va = (a.fund && a.fund.trailing_pe) || 0; vb = (b.fund && b.fund.trailing_pe) || 0; }
      else if (_sortCol === 'yield') { va = (a.fund && a.fund.dividend_yield) || 0; vb = (b.fund && b.fund.dividend_yield) || 0; }
      else if (_sortCol === 'beta') { va = (a.fund && a.fund.beta_3y) || 0; vb = (b.fund && b.fund.beta_3y) || 0; }
      else if (_sortCol === 'num') { va = (a.analyst && a.analyst.num_analysts) || 0; vb = (b.analyst && b.analyst.num_analysts) || 0; }
      else if (_sortCol === 'upside') { va = (a.analyst && a.analyst.upside_pct) || 0; vb = (b.analyst && b.analyst.upside_pct) || 0; }
      va = va || 0; vb = vb || 0;
    } else if (_sortCol === 'value') {
      va = va || 0; vb = vb || 0;
    } else {
      va = (va || '').toString().toLowerCase();
      vb = (vb || '').toString().toLowerCase();
    }
    if (va < vb) return _sortDir === 'asc' ? -1 : 1;
    if (va > vb) return _sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  body.innerHTML = sorted.map(h => {
    const hasA = h.analyst && h.analyst.has_analyst;
    const rating = hasA ? (RATING_LABELS[h.analyst.recommendation] || h.analyst.recommendation) : 'N/A';
    const ratingColor = hasA ? (RATING_COLORS[h.analyst.recommendation] || '#64748b') : '#94a3b8';

    const num = hasA ? (h.analyst.num_analysts || '—') : '—';
    const tgt = hasA && h.analyst.target_mean ? h.analyst.target_mean.toFixed(2) : '—';
    const up = hasA && h.analyst.upside_pct != null ? h.analyst.upside_pct : null;

    let action = h.action || 'Monitor';
    let actionCls = 'text-muted';
    if (h.action_code === 'add') actionCls = 'text-success';
    else if (h.action_code === 'trim') actionCls = 'text-danger';

    const upStr = up != null ? fmtPct(up) : '—';
    const upCls = up != null && up > 5 ? 'text-success' : (up != null && up < -3 ? 'text-danger' : '');

    // Fund metrics (most relevant for ETF/mutual fund heavy portfolios)
    const f = h.fund || {};
    const exp = f.expense_ratio != null ? f.expense_ratio.toFixed(2) + '%' : '—';
    const pe = f.trailing_pe != null ? f.trailing_pe.toFixed(1) : '—';
    const yld = f.dividend_yield != null ? f.dividend_yield.toFixed(2) + '%' : '—';
    const beta = f.beta_3y != null ? f.beta_3y.toFixed(2) : '—';

    let expCls = '';
    if (f.expense_ratio != null) {
      if (f.expense_ratio > 0.15) expCls = 'text-danger';
      else if (f.expense_ratio < 0.06) expCls = 'text-success';
    }
    let peCls = '';
    if (f.trailing_pe != null) {
      if (f.trailing_pe > 26) peCls = 'text-danger';
      else if (f.trailing_pe < 18) peCls = 'text-success';
    }

    return `
      <tr>
        <td><strong>${esc(h.ticker || '—')}</strong></td>
        <td>${esc(h.name)}</td>
        <td class="text-right">${fmt(h.current_value)}</td>
        <td class="text-right ${expCls}">${exp}</td>
        <td class="text-right ${peCls}">${pe}</td>
        <td class="text-right">${yld}</td>
        <td class="text-right">${beta}</td>
        <td>
          <span style="display:inline-block;padding:1px 7px;border-radius:3px;background:${ratingColor};color:white;font-size:0.8rem;font-weight:600">
            ${esc(rating)}
          </span>
        </td>
        <td class="text-right">${num}</td>
        <td class="text-right">${tgt}</td>
        <td class="text-right ${upCls}">${upStr}</td>
        <td class="text-center" style="font-weight:600">
          <span class="${actionCls}">${esc(action)}</span>
        </td>
      </tr>
    `;
  }).join('');

  updateSortIndicators();
}

function sortInsights(col) {
  if (_sortCol === col) {
    _sortDir = _sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    _sortCol = col;
    _sortDir = (col === 'value' || col === 'upside') ? 'desc' : 'asc';
  }
  if (_insightsData) {
    renderTable(_insightsData.holdings || []);
  }
  updateSortIndicators();
}

// Auto-load on page open
document.addEventListener('DOMContentLoaded', () => {
  loadInsights();
});
