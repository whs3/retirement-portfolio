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
        legend: { position: 'right' },
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

  tbody.innerHTML = Object.values(groups).map(g => {
    const gain    = g.current_value - g.cost_basis;
    const gainPct = g.cost_basis > 0 ? (gain / g.cost_basis * 100) : 0;
    const cls     = gain >= 0 ? 'text-success' : 'text-danger';
    const pps     = g.shares > 0 ? fmt(g.current_value / g.shares) : '—';
    return `
    <tr>
      <td><strong>${esc(g.ticker) || '—'}</strong></td>
      <td>${esc(g.name)}</td>
      <td><span class="badge badge-${g.asset_type}">${TYPE_LABELS[g.asset_type] ?? g.asset_type}</span></td>
      <td>${esc(g.category) || '—'}</td>
      <td class="text-right">${g.shares > 0 ? g.shares.toFixed(4) : '—'}</td>
      <td class="text-right">${pps}</td>
      <td class="text-right">${fmt(g.cost_basis)}</td>
      <td class="text-right">${fmt(g.current_value)}</td>
      <td class="text-right ${cls}">${fmt(gain)}</td>
      <td class="text-right ${cls}">${(gain >= 0 ? '+' : '')}${fmtPct(gainPct)}</td>
    </tr>`;
  }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  loadSummary();
  loadHoldings();
  document.getElementById('lastUpdated').textContent =
    'As of ' + new Date().toLocaleDateString('en-US', { dateStyle: 'medium' });
});
