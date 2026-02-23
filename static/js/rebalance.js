'use strict';

const CATEGORY_COLORS = [
  '#2563eb','#16a34a','#d97706','#7c3aed','#db2777','#0891b2',
  '#65a30d','#ea580c','#9333ea','#0284c7','#15803d','#b45309',
];

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

let rebalanceChart = null;

function fmt(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

// ── Alerts ────────────────────────────────────────────────────────────────────

function showAlert(msg, type = 'success') {
  const div       = document.createElement('div');
  div.className   = `alert alert-${type}`;
  div.textContent = msg;
  document.getElementById('alertContainer').prepend(div);
  setTimeout(() => div.remove(), 5000);
}

// ── Target allocation editor ──────────────────────────────────────────────────

async function loadTargetAllocations() {
  const res         = await fetch('/api/allocations');
  const allocations = await res.json();

  document.getElementById('targetBody').innerHTML = allocations.map(a => `
    <tr>
      <td>${esc(a.category)}</td>
      <td class="text-right">
        <input type="number" class="allocation-input"
               name="${esc(a.category)}"
               value="${a.target_percentage}"
               min="0" max="100" step="0.01"
               oninput="updateTotal()">
      </td>
    </tr>
  `).join('');

  updateTotal();
}

function updateTotal() {
  const inputs  = document.querySelectorAll('.allocation-input');
  let total     = 0;
  inputs.forEach(inp => { total += parseFloat(inp.value) || 0; });

  const totalEl   = document.getElementById('allocationTotal');
  const warningEl = document.getElementById('allocationWarning');
  const ok        = Math.abs(total - 100) < 0.01;

  totalEl.textContent      = total.toFixed(1);
  totalEl.style.color      = ok ? '' : 'var(--danger)';
  warningEl.style.display  = ok ? 'none' : 'inline';
}

async function useCurrentAllocations() {
  const res  = await fetch('/api/rebalance');
  const data = await res.json();
  const pctMap = {};
  data.recommendations.forEach(r => { pctMap[r.category] = r.current_pct; });

  document.querySelectorAll('.allocation-input').forEach(inp => {
    if (pctMap[inp.name] !== undefined) {
      inp.value = pctMap[inp.name].toFixed(4);
    }
  });
  updateTotal();
}

async function saveAllocations(event) {
  event.preventDefault();

  const data = [];
  document.querySelectorAll('.allocation-input').forEach(inp => {
    data.push({ category: inp.name, target_percentage: parseFloat(inp.value) || 0 });
  });

  const res    = await fetch('/api/allocations', {
    method:  'PUT',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(data),
  });
  const result = await res.json();

  if (res.ok) {
    showAlert('Target allocations saved successfully.', 'success');
    loadRebalance();
  } else {
    showAlert(result.error ?? 'Failed to save allocations.', 'error');
  }
}

// ── Rebalance chart + recommendations ────────────────────────────────────────

async function loadRebalance() {
  const res  = await fetch('/api/rebalance');
  const data = await res.json();
  renderRebalanceChart(data.recommendations);
  renderRecommendations(data.recommendations);
}

function renderRebalanceChart(recs) {
  const canvas = document.getElementById('rebalanceChart');
  const ctx    = canvas.getContext('2d');

  if (rebalanceChart) rebalanceChart.destroy();
  if (!recs.length) return;

  const labels      = recs.map(r => r.category);
  const colors      = recs.map((_, i) => CATEGORY_COLORS[i % CATEGORY_COLORS.length]);
  const lightColors = colors.map(c => c + '55');

  rebalanceChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label:           'Current %',
          data:            recs.map(r => +r.current_pct.toFixed(2)),
          backgroundColor: colors,
          borderRadius:    4,
        },
        {
          label:           'Target %',
          data:            recs.map(r => r.target_pct),
          backgroundColor: lightColors,
          borderColor:     colors,
          borderWidth:     2,
          borderRadius:    4,
        },
      ],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' } },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { callback: v => v + '%' },
        },
      },
    },
  });
}

function renderRecommendations(recs) {
  const tbody = document.getElementById('recommendationsBody');

  if (!recs.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No data — add holdings first.</td></tr>';
    return;
  }

  tbody.innerHTML = recs.map(r => {
    const diffCls = r.difference > 1 ? 'text-success' : r.difference < -1 ? 'text-danger' : '';
    return `
    <tr>
      <td>${esc(r.category)}</td>
      <td class="text-right">${fmt(r.current_value)}</td>
      <td class="text-right">${r.current_pct.toFixed(2)}%</td>
      <td class="text-right">${r.target_pct.toFixed(1)}%</td>
      <td class="text-right">${fmt(r.target_value)}</td>
      <td class="text-right ${diffCls}">${r.difference >= 0 ? '+' : ''}${fmt(r.difference)}</td>
      <td class="text-center"><span class="badge badge-${r.action.toLowerCase()}">${r.action}</span></td>
    </tr>`;
  }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  loadTargetAllocations();
  loadRebalance();
});
