'use strict';

const CHART_COLORS = [
  '#2563eb','#16a34a','#dc2626','#d97706','#7c3aed',
  '#0891b2','#be185d','#65a30d','#ea580c','#0f766e',
  '#4338ca','#b91c1c','#a16207','#6d28d9','#0369a1',
  '#94a3b8',  // "Other" — neutral grey
];

let overlapChart = null;
let allStocks    = [];

function fmt(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function calculate() {
  const btn    = document.getElementById('calcBtn');
  const status = document.getElementById('statusMsg');

  btn.disabled    = true;
  btn.textContent = 'Calculating…';
  status.className     = 'alert';
  status.style.display = 'block';
  status.textContent   = 'Fetching ETF compositions from Yahoo Finance — this may take a moment…';

  document.getElementById('resultsSection').style.display = 'none';

  try {
    const res  = await fetch('/api/overlap');
    const data = await res.json();

    if (!res.ok) {
      status.classList.add('alert-danger');
      status.textContent = data.error ?? 'Failed to calculate overlap.';
      return;
    }

    status.style.display = 'none';
    allStocks = data.stocks;
    renderResults(data);

  } catch (err) {
    status.classList.add('alert-danger');
    status.textContent = `Request failed: ${err.message}`;
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Recalculate';
  }
}

function renderResults(data) {
  const { stocks, total, errors } = data;

  // Summary cards
  const equityStocks = stocks.filter(s => s.ticker !== '__OTHER__' && s.ticker !== '__BOND_FI__');
  const top1 = equityStocks[0] ?? stocks[0];
  const top1ticker = top1 ? (top1.ticker === '__OTHER__' ? top1.name : top1.ticker) : '—';
  const top1label  = top1 ? top1.percentage.toFixed(2) + '%' : '';
  const errColor   = errors.length ? 'var(--danger)' : 'var(--success)';

  document.getElementById('summaryCards').innerHTML = `
    <div class="card" style="overflow:hidden">
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:var(--bg)">
            <th style="padding:0.75rem 1.5rem;text-align:center;font-family:Georgia,serif;font-size:0.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);border-bottom:1px solid var(--border);border-right:1px solid var(--border)">Stocks Identified</th>
            <th style="padding:0.75rem 1.5rem;text-align:center;font-family:Georgia,serif;font-size:0.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);border-bottom:1px solid var(--border);border-right:1px solid var(--border)">Total Analysed Value</th>
            <th style="padding:0.75rem 1.5rem;text-align:center;font-family:Georgia,serif;font-size:0.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);border-bottom:1px solid var(--border);border-right:1px solid var(--border)">Largest Holding</th>
            <th style="padding:0.75rem 1.5rem;text-align:center;font-family:Georgia,serif;font-size:0.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);border-bottom:1px solid var(--border)">ETF Lookup Errors</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="padding:1rem 1.5rem;text-align:center;border-right:1px solid var(--border)">
              <div style="font-family:Georgia,serif;font-size:2rem;font-weight:700;color:var(--text)">${equityStocks.length}</div>
            </td>
            <td style="padding:1rem 1.5rem;text-align:center;border-right:1px solid var(--border)">
              <div style="font-family:Georgia,serif;font-size:2rem;font-weight:700;color:var(--text)">${fmt(total)}</div>
            </td>
            <td style="padding:1rem 1.5rem;text-align:center;border-right:1px solid var(--border)">
              <div style="font-family:Georgia,serif;font-size:2rem;font-weight:700;color:var(--text)">${esc(top1ticker)}</div>
              <div style="font-size:0.9rem;color:var(--text-muted);margin-top:0.1rem">${top1label}</div>
            </td>
            <td style="padding:1rem 1.5rem;text-align:center">
              <div style="font-family:Georgia,serif;font-size:2rem;font-weight:700;color:${errColor}">${errors.length}</div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>`;

  // Build top-15 for chart; group the rest as "Other" if needed
  const TOP_N = 15;
  const top   = stocks.slice(0, TOP_N);
  const rest  = stocks.slice(TOP_N);
  const restValue = rest.reduce((s, r) => s + r.value, 0);

  const labels = top.map(s => s.ticker === '__OTHER__' ? 'Other' : s.ticker === '__BOND_FI__' ? 'Bond/FI' : s.ticker);
  const values = top.map(s => s.value);
  const colors = top.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);

  if (restValue > 0) {
    labels.push('Other');
    values.push(restValue);
    colors.push('#94a3b8');
  }

  // Pie chart
  const ctx = document.getElementById('overlapChart').getContext('2d');
  if (overlapChart) overlapChart.destroy();
  overlapChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: colors, borderWidth: 2 }],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${fmt(ctx.parsed)}  (${((ctx.parsed / total) * 100).toFixed(2)}%)`,
          },
        },
      },
      cutout: '55%',
    },
  });

  // Side legend
  const legendItems = top.map((s, i) => `
    <div style="display:flex;align-items:center;gap:0.5rem;padding:0.2rem 0;font-size:0.88rem">
      <span style="width:12px;height:12px;border-radius:2px;background:${colors[i]};flex-shrink:0"></span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(s.name)}">
        <strong>${esc(s.ticker === '__OTHER__' ? 'Other' : s.ticker === '__BOND_FI__' ? 'Bond/FI' : s.ticker)}</strong> ${esc(s.name)}
      </span>
      <span style="white-space:nowrap;color:var(--text-muted)">${s.percentage.toFixed(2)}%</span>
    </div>`).join('');
  document.getElementById('legendList').innerHTML = legendItems +
    (restValue > 0 ? `<div style="font-size:0.82rem;color:var(--text-muted);margin-top:0.5rem">+ ${rest.length} more — see table below</div>` : '');

  // Table
  renderTable('');

  // Other Holdings breakdown
  const otherSection = document.getElementById('otherBreakdownSection');
  const breakdown = data.other_breakdown ?? [];
  if (breakdown.length) {
    document.getElementById('otherBreakdownBody').innerHTML = breakdown.map(b => {
      const srcLabel = b.source === 'fmp' ? 'FMP' : 'yfinance';
      const srcColor = b.source === 'fmp' ? 'var(--success)' : 'var(--text-muted)';
      return `<tr>
        <td><strong>${esc(b.ticker)}</strong></td>
        <td>${esc(b.name)}</td>
        <td class="text-right">${b.covered_pct.toFixed(1)}%</td>
        <td class="text-right text-muted">${b.other_pct.toFixed(1)}%</td>
        <td class="text-right">${fmt(b.other_value)}</td>
        <td style="color:${srcColor};font-size:0.85rem">${srcLabel}</td>
      </tr>`;
    }).join('');
    otherSection.style.display = 'block';
  } else {
    otherSection.style.display = 'none';
  }

  // Errors
  const errSection = document.getElementById('errorSection');
  if (errors.length) {
    document.getElementById('errorList').innerHTML =
      errors.map(e => `<li><strong>${esc(e.ticker)}</strong>: ${esc(e.error)}</li>`).join('');
    errSection.style.display = 'block';
  } else {
    errSection.style.display = 'none';
  }

  document.getElementById('resultsSection').style.display = 'block';
}

function renderTable(query) {
  const q = (query ?? '').trim().toLowerCase();
  const filtered = q
    ? allStocks.filter(s =>
        s.ticker.toLowerCase().includes(q) || s.name.toLowerCase().includes(q))
    : allStocks;

  const tbody = document.getElementById('overlapBody');
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted" style="padding:2rem">No results match your search.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map((s, i) => {
    const label = s.ticker === '__OTHER__' ? '—' : s.ticker === '__BOND_FI__' ? '—' : esc(s.ticker);
    return `<tr>
      <td class="text-muted">${i + 1}</td>
      <td><strong>${label}</strong></td>
      <td>${esc(s.name)}</td>
      <td class="text-right">${fmt(s.value)}</td>
      <td class="text-right">${s.percentage.toFixed(2)}%</td>
    </tr>`;
  }).join('');
}

// ── FMP key settings ─────────────────────────────────────────────────────────

async function loadFmpKeyStatus() {
  const res  = await fetch('/api/settings');
  const data = await res.json();
  const el   = document.getElementById('fmpKeyStatus');
  el.textContent = data.fmp_api_key_set
    ? 'FMP key saved — will use Financial Modeling Prep (full holdings)'
    : 'No FMP key — will use yfinance (top holdings only)';
  el.style.color = data.fmp_api_key_set ? 'var(--success)' : 'var(--text-muted)';
}

async function saveFmpKey() {
  const key = document.getElementById('fmpKeyInput').value.trim();
  if (!key) { alert('Enter an API key first.'); return; }
  await fetch('/api/settings', {
    method:  'PUT',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ fmp_api_key: key }),
  });
  document.getElementById('fmpKeyInput').value = '';
  loadFmpKeyStatus();
}

async function clearFmpKey() {
  await fetch('/api/settings', {
    method:  'PUT',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ fmp_api_key: '' }),
  });
  loadFmpKeyStatus();
}

document.addEventListener('DOMContentLoaded', () => {
  loadFmpKeyStatus();
  document.getElementById('overlapSearch').addEventListener('input', e => {
    renderTable(e.target.value);
  });
});
