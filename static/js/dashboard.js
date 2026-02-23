'use strict';

const TYPE_LABELS = {
  stock:       'Stock',
  bond:        'Bond',
  etf:         'ETF',
  mutual_fund: 'Mutual Fund',
};

const TYPE_COLORS = {
  stock:       '#2563eb',
  bond:        '#16a34a',
  etf:         '#d97706',
  mutual_fund: '#7c3aed',
};

let allocationChart = null;
let categoryChart = null;

// Palette for dynamically-generated category colors (cycles if more than 12 categories)
const CATEGORY_COLORS = [
  '#2563eb','#16a34a','#d97706','#7c3aed','#db2777','#0891b2',
  '#65a30d','#ea580c','#9333ea','#0284c7','#15803d','#b45309',
];

function fmt(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function fmtPct(n) {
  return n.toFixed(2) + '%';
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function loadSummary() {
  const res  = await fetch('/api/portfolio/summary');
  const data = await res.json();

  document.getElementById('totalValue').textContent   = fmt(data.total_value);
  document.getElementById('totalCost').textContent    = fmt(data.total_cost);
  document.getElementById('holdingCount').textContent = data.count;

  const glEl    = document.getElementById('gainLoss');
  const glPctEl = document.getElementById('gainLossPct');
  const pos     = data.gain_loss >= 0;

  glEl.textContent    = fmt(data.gain_loss);
  glEl.className      = 'card-value ' + (pos ? 'text-success' : 'text-danger');
  glPctEl.textContent = (pos ? '+' : '') + fmtPct(data.gain_loss_pct);
  glPctEl.className   = 'card-sub '   + (pos ? 'text-success' : 'text-danger');

  renderAllocationChart(data.allocation);
  renderAllocationTable(data.allocation);
  renderCategoryChart(data.category_allocation);
  renderCategoryTable(data.category_allocation);
}

function renderAllocationChart(allocation) {
  const canvas = document.getElementById('allocationChart');
  const ctx    = canvas.getContext('2d');

  if (allocationChart) allocationChart.destroy();

  if (!allocation.length) {
    canvas.parentElement.innerHTML = '<p class="text-muted text-center">No holdings yet.</p>';
    return;
  }

  allocationChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels:   allocation.map(a => TYPE_LABELS[a.asset_type] ?? a.asset_type),
      datasets: [{
        data:            allocation.map(a => a.value),
        backgroundColor: allocation.map(a => TYPE_COLORS[a.asset_type] ?? '#94a3b8'),
        borderWidth: 2,
        borderColor: '#fff',
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: {
            generateLabels: (chart) => {
              return chart.data.labels.map((label, i) => ({
                text: `${label} (${allocation[i].percentage.toFixed(1)}%)`,
                fillStyle: chart.data.datasets[0].backgroundColor[i],
                strokeStyle: '#fff',
                lineWidth: 2,
                hidden: false,
                index: i,
              }));
            },
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const a = allocation[ctx.dataIndex];
              return ` ${fmt(a.value)} (${fmtPct(a.percentage)})`;
            },
          },
        },
      },
    },
  });
}

function renderAllocationTable(allocation) {
  const tbody = document.getElementById('allocationBody');
  if (!allocation.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No holdings yet.</td></tr>';
    return;
  }
  tbody.innerHTML = allocation.map(a => `
    <tr>
      <td><span class="badge badge-${a.asset_type}">${TYPE_LABELS[a.asset_type] ?? a.asset_type}</span></td>
      <td class="text-right">${fmt(a.value)}</td>
      <td class="text-right">${fmtPct(a.percentage)}</td>
    </tr>
  `).join('');
}

function renderCategoryChart(categoryAllocation) {
  const canvas = document.getElementById('categoryChart');
  const ctx    = canvas.getContext('2d');

  if (categoryChart) categoryChart.destroy();

  if (!categoryAllocation || !categoryAllocation.length) {
    canvas.parentElement.innerHTML = '<p class="text-muted text-center">No holdings yet.</p>';
    return;
  }

  const colors = categoryAllocation.map((_, i) => CATEGORY_COLORS[i % CATEGORY_COLORS.length]);

  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels:   categoryAllocation.map(a => a.category),
      datasets: [{
        data:            categoryAllocation.map(a => a.value),
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: '#fff',
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: {
            generateLabels: (chart) => {
              return chart.data.labels.map((label, i) => ({
                text: `${label} (${categoryAllocation[i].percentage.toFixed(1)}%)`,
                fillStyle: chart.data.datasets[0].backgroundColor[i],
                strokeStyle: '#fff',
                lineWidth: 2,
                hidden: false,
                index: i,
              }));
            },
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const a = categoryAllocation[ctx.dataIndex];
              return ` ${fmt(a.value)} (${fmtPct(a.percentage)})`;
            },
          },
        },
      },
    },
  });
}

function renderCategoryTable(categoryAllocation) {
  const tbody = document.getElementById('categoryBody');
  if (!categoryAllocation || !categoryAllocation.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No holdings yet.</td></tr>';
    return;
  }
  tbody.innerHTML = categoryAllocation.map(a => `
    <tr>
      <td>${esc(a.category)}</td>
      <td class="text-right">${fmt(a.value)}</td>
      <td class="text-right">${fmtPct(a.percentage)}</td>
    </tr>
  `).join('');
}

let holdingsGroups = [];
let sortCol = 'ticker';
let sortDir = 1;  // 1 = asc, -1 = desc

async function loadHoldings() {
  const res      = await fetch('/api/holdings');
  const holdings = await res.json();
  const tbody    = document.getElementById('holdingsBody');

  if (!holdings.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted" style="padding:2rem">
      No holdings yet. <a href="/holdings">Add your first holding.</a></td></tr>`;
    return;
  }

  // Group by ticker (blank ticker = its own row keyed by id)
  const groups = {};
  for (const h of holdings) {
    const key = h.ticker || `__no_ticker_${h.id}`;
    if (!groups[key]) {
      groups[key] = { ticker: h.ticker, name: h.name, asset_type: h.asset_type,
                      category: h.category, shares: 0, cost_basis: 0, current_value: 0 };
    }
    groups[key].shares        += h.shares;
    groups[key].cost_basis    += h.cost_basis;
    groups[key].current_value += h.current_value;
  }

  // Pre-compute derived sort fields
  holdingsGroups = Object.values(groups).map(g => ({
    ...g,
    gain:    g.current_value - g.cost_basis,
    gainPct: g.cost_basis > 0 ? (g.current_value - g.cost_basis) / g.cost_basis * 100 : 0,
    pps:     g.shares > 0 ? g.current_value / g.shares : 0,
  }));

  renderHoldingsTable();
}

function sortHoldings(col) {
  sortDir = col === sortCol ? -sortDir : 1;
  sortCol = col;
  renderHoldingsTable();
}

function renderHoldingsTable() {
  const tbody = document.getElementById('holdingsBody');

  const sorted = [...holdingsGroups].sort((a, b) => {
    const av = a[sortCol] ?? '';
    const bv = b[sortCol] ?? '';
    if (typeof av === 'string') return av.localeCompare(bv) * sortDir;
    return (av - bv) * sortDir;
  });

  // Update sort indicators
  document.querySelectorAll('.sort-indicator').forEach(el => {
    const col = el.dataset.col;
    el.textContent = col === sortCol ? (sortDir === 1 ? ' ↑' : ' ↓') : '';
  });

  tbody.innerHTML = sorted.map(g => {
    const cls = g.gain >= 0 ? 'text-success' : 'text-danger';
    return `
    <tr>
      <td><strong>${esc(g.ticker) || '—'}</strong></td>
      <td>${esc(g.name)}</td>
      <td><span class="badge badge-${g.asset_type}">${TYPE_LABELS[g.asset_type] ?? g.asset_type}</span></td>
      <td>${esc(g.category) || '—'}</td>
      <td class="text-right">${g.shares > 0 ? g.shares.toFixed(4) : '—'}</td>
      <td class="text-right">${g.pps > 0 ? fmt(g.pps) : '—'}</td>
      <td class="text-right">${fmt(g.cost_basis)}</td>
      <td class="text-right">${fmt(g.current_value)}</td>
      <td class="text-right ${cls}">${fmt(g.gain)}</td>
      <td class="text-right ${cls}">${(g.gain >= 0 ? '+' : '')}${fmtPct(g.gainPct)}</td>
    </tr>`;
  }).join('');
}

function updateTimestamp() {
  document.getElementById('lastUpdated').textContent =
    'As of ' + new Date().toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });
}

async function refreshPrices() {
  const btn    = document.getElementById('refreshBtn');
  const status = document.getElementById('refreshStatus');

  btn.disabled    = true;
  btn.textContent = 'Refreshing…';
  status.style.display = 'none';
  status.className     = 'alert';

  try {
    const res  = await fetch('/api/holdings/refresh-prices', { method: 'POST' });
    const data = await res.json();

    const parts = [];
    if (data.updated.length) parts.push(`Updated ${data.updated.length} holding(s).`);
    if (data.skipped.length) parts.push(`Skipped (no price): ${data.skipped.join(', ')}.`);
    if (data.errors.length)  parts.push(`Errors: ${data.errors.map(e => `${e.ticker} — ${e.error}`).join('; ')}.`);

    status.textContent   = parts.join('  ') || 'No tickered holdings to update.';
    status.style.display = 'block';
    status.classList.add(data.errors.length ? 'alert-danger' : 'alert-success');

    updateTimestamp();
    loadSummary();
    loadHoldings();
  } catch (err) {
    status.textContent   = `Request failed: ${err.message}`;
    status.style.display = 'block';
    status.classList.add('alert-danger');
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Refresh Prices';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  updateTimestamp();
  loadSummary();
  loadHoldings();
});
