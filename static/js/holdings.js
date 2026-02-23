'use strict';

const TYPE_LABELS = {
  stock:       'Stock',
  bond:        'Bond',
  etf:         'ETF',
  mutual_fund: 'Mutual Fund',
  cash:        'Cash',
};

let holdings     = [];
let editingId    = null;
let fetchedPrice = null;  // cached price from last "Fetch" call
let sortCol      = 'name';
let sortDir      = 1;  // 1 = asc, -1 = desc

function fmt(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Data ─────────────────────────────────────────────────────────────────────

async function loadHoldings() {
  const res = await fetch('/api/holdings');
  holdings  = await res.json();
  renderTable();
}

function sortHoldings(col) {
  sortDir = col === sortCol ? -sortDir : 1;
  sortCol = col;
  renderTable();
}

function renderTable() {
  const tbody = document.getElementById('holdingsBody');

  if (!holdings.length) {
    tbody.innerHTML = `<tr><td colspan="12" class="text-center text-muted" style="padding:2rem">
      No holdings yet. Click "Add Holding" to get started.</td></tr>`;
    return;
  }

  // Augment with derived sort fields
  const rows = holdings.map(h => ({
    ...h,
    gain:    h.current_value - h.cost_basis,
    gainPct: h.cost_basis > 0 ? (h.current_value - h.cost_basis) / h.cost_basis * 100 : 0,
    pps:     h.shares > 0 ? h.current_value / h.shares : 0,
  }));

  rows.sort((a, b) => {
    const av = a[sortCol] ?? '';
    const bv = b[sortCol] ?? '';
    if (typeof av === 'string') return av.localeCompare(bv) * sortDir;
    return (av - bv) * sortDir;
  });

  // Update sort indicators
  document.querySelectorAll('.sort-indicator').forEach(el => {
    el.textContent = el.dataset.col === sortCol ? (sortDir === 1 ? ' ↑' : ' ↓') : '';
  });

  tbody.innerHTML = rows.map(h => {
    const cls   = h.gain >= 0 ? 'text-success' : 'text-danger';
    const notes = h.notes ? `<br><small class="text-muted">${esc(h.notes)}</small>` : '';
    return `
    <tr>
      <td style="white-space:nowrap"><strong>${esc(h.name)}</strong>${notes}</td>
      <td>${esc(h.ticker) || '—'}</td>
      <td><span class="badge badge-${h.asset_type}">${TYPE_LABELS[h.asset_type] ?? h.asset_type}</span></td>
      <td>${esc(h.category) || '—'}</td>
      <td class="text-right">${h.shares > 0 ? h.shares : '—'}</td>
      <td class="text-right">${fmt(h.cost_basis)}</td>
      <td class="text-right">${h.pps > 0 ? fmt(h.pps) : '—'}</td>
      <td class="text-right">${fmt(h.current_value)}</td>
      <td class="text-right ${cls}">${fmt(h.gain)}</td>
      <td class="text-right ${cls}">${(h.gain >= 0 ? '+' : '')}${h.gainPct.toFixed(2)}%</td>
      <td>${h.purchase_date || '—'}</td>
      <td class="col-actions">
        <button class="btn btn-sm btn-secondary" onclick="openModal(${h.id})">Edit</button>
        <button class="btn btn-sm btn-danger"    onclick="deleteHolding(${h.id}, '${esc(h.name)}')">Delete</button>
      </td>
    </tr>`;
  }).join('');
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function openModal(id = null) {
  editingId = id;
  const title     = document.getElementById('modalTitle');
  const submitBtn = document.getElementById('submitBtn');

  if (id !== null) {
    const h = holdings.find(x => x.id === id);
    title.textContent     = 'Edit Holding';
    submitBtn.textContent = 'Save Changes';
    document.getElementById('holdingId').value    = h.id;
    document.getElementById('name').value         = h.name;
    document.getElementById('ticker').value       = h.ticker;
    document.getElementById('category').value     = h.category;
    document.getElementById('assetType').value    = h.asset_type;
    document.getElementById('shares').value       = h.shares;
    document.getElementById('costBasis').value    = h.cost_basis;
    document.getElementById('currentValue').value = h.current_value;
    document.getElementById('purchaseDate').value = h.purchase_date;
    document.getElementById('notes').value        = h.notes;
  } else {
    title.textContent     = 'Add Holding';
    submitBtn.textContent = 'Add Holding';
    document.getElementById('holdingForm').reset();
    document.getElementById('holdingId').value    = '';
    document.getElementById('assetType').value    = 'etf';
    document.getElementById('purchaseDate').value = new Date().toISOString().slice(0, 10);
  }

  document.getElementById('modalOverlay').classList.add('open');
}

function closeModal(event) {
  if (event.target === document.getElementById('modalOverlay')) closeModalDirect();
}

function closeModalDirect() {
  document.getElementById('modalOverlay').classList.remove('open');
  editingId    = null;
  fetchedPrice = null;
  const display = document.getElementById('priceDisplay');
  display.style.display = 'none';
  display.textContent   = '';
}

// ── CRUD ──────────────────────────────────────────────────────────────────────

async function submitForm(event) {
  event.preventDefault();

  const data = {
    name:          document.getElementById('name').value,
    ticker:        document.getElementById('ticker').value,
    category:      document.getElementById('category').value,
    asset_type:    document.getElementById('assetType').value,
    shares:        parseFloat(document.getElementById('shares').value) || 0,
    cost_basis:    parseFloat(document.getElementById('costBasis').value),
    current_value: parseFloat(document.getElementById('currentValue').value),
    purchase_date: document.getElementById('purchaseDate').value,
    notes:         document.getElementById('notes').value,
  };

  const id     = document.getElementById('holdingId').value;
  const url    = id ? `/api/holdings/${id}` : '/api/holdings';
  const method = id ? 'PUT' : 'POST';

  const res    = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(data),
  });
  const result = await res.json();

  if (res.ok) {
    closeModalDirect();
    loadHoldings();
  } else {
    alert(result.error ?? 'Failed to save holding.');
  }
}

async function deleteHolding(id, name) {
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;

  const res = await fetch(`/api/holdings/${id}`, { method: 'DELETE' });
  if (res.ok) {
    loadHoldings();
  } else {
    alert('Failed to delete holding.');
  }
}

// ── Live prices ───────────────────────────────────────────────────────────────

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

    status.textContent    = parts.join('  ') || 'No tickered holdings to update.';
    status.style.display  = 'block';
    status.classList.add(data.errors.length ? 'alert-danger' : 'alert-success');

    if (data.updated.length) loadHoldings();
  } catch (err) {
    status.textContent   = `Request failed: ${err.message}`;
    status.style.display = 'block';
    status.classList.add('alert-danger');
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Refresh Prices';
  }
}

async function fetchPrice() {
  const ticker = document.getElementById('ticker').value.trim().toUpperCase();
  if (!ticker) { alert('Enter a ticker symbol first.'); return; }

  const display = document.getElementById('priceDisplay');
  display.textContent  = 'Fetching…';
  display.style.display = 'inline';

  try {
    const res  = await fetch(`/api/price/${encodeURIComponent(ticker)}`);
    const data = await res.json();

    if (!res.ok) {
      display.textContent = `Error: ${data.error}`;
      fetchedPrice = null;
      return;
    }

    fetchedPrice = data.price;
    display.textContent = `Live price: $${data.price.toFixed(2)}`;
    if (data.name && !document.getElementById('name').value.trim()) {
      document.getElementById('name').value = data.name;
    }
    if (data.category && !document.getElementById('category').value.trim()) {
      document.getElementById('category').value = data.category;
    }
    recalcCurrentValue();
  } catch (err) {
    display.textContent = `Request failed: ${err.message}`;
    fetchedPrice = null;
  }
}

function recalcCurrentValue() {
  const ticker = document.getElementById('ticker').value.toUpperCase();
  const shares = parseFloat(document.getElementById('shares').value) || 0;
  if (ticker === '$$CASH') {
    document.getElementById('currentValue').value = shares.toFixed(2);
    return;
  }
  if (fetchedPrice === null) return;
  document.getElementById('currentValue').value = (shares * fetchedPrice).toFixed(2);
}

document.addEventListener('DOMContentLoaded', () => {
  loadHoldings();
  document.getElementById('shares').addEventListener('input', recalcCurrentValue);
  document.getElementById('ticker').addEventListener('input', () => {
    if (document.getElementById('ticker').value.toUpperCase() === '$$CASH') {
      document.getElementById('assetType').value = 'cash';
      recalcCurrentValue();
    }
  });
});
