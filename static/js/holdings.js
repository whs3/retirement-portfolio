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
let sortCol      = 'purchase_date';
let sortDir      = -1;  // 1 = asc, -1 = desc

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

// Rows visible under the current search box + owner/account filters, with
// derived sort fields. Shared by the table body, the ticker summary, and
// sellAllTicker() so "Sell All" only ever acts on what's on screen.
function getFilteredHoldings() {
  const query         = (document.getElementById('holdingsSearch')?.value ?? '').trim().toLowerCase();
  const ownerFilter   = document.getElementById('ownerFilter')?.value ?? '';
  const accountFilter = document.getElementById('accountTypeFilter')?.value ?? '';

  const rows = holdings.map(h => ({
    ...h,
    gain:    h.current_value - h.cost_basis,
    gainPct: h.cost_basis > 0 ? (h.current_value - h.cost_basis) / h.cost_basis * 100 : 0,
    pps:     h.shares !== 0 ? h.current_value / h.shares : 0,
  }));

  return (query || ownerFilter || accountFilter)
    ? rows.filter(h =>
        (!query || (h.name ?? '').toLowerCase().includes(query) ||
                   (h.ticker ?? '').toLowerCase().includes(query) ||
                   (h.purchase_date ?? '').toLowerCase().includes(query)) &&
        (!ownerFilter   || h.owner === ownerFilter) &&
        (!accountFilter || h.account_type === accountFilter)
      )
    : rows;
}

function renderTable() {
  const tbody = document.getElementById('holdingsBody');

  if (!holdings.length) {
    tbody.innerHTML = `<tr><td colspan="13" class="text-center text-muted" style="padding:2rem">
      No holdings yet. Click "Add Holding" to get started.</td></tr>`;
    return;
  }

  const filtered = getFilteredHoldings();
  filtered.sort((a, b) => {
    const av = a[sortCol] ?? '';
    const bv = b[sortCol] ?? '';
    if (typeof av === 'string') return av.localeCompare(bv) * sortDir;
    return (av - bv) * sortDir;
  });

  // Update sort indicators
  document.querySelectorAll('.sort-indicator').forEach(el => {
    el.textContent = el.dataset.col === sortCol ? (sortDir === 1 ? ' ↑' : ' ↓') : '';
  });

  const summaryEl = document.getElementById('searchSummary');
  let summaryEntries = [];
  if (filtered.length) {
    const byTicker = {};
    for (const h of filtered) {
      const t = h.ticker || '—';
      if (!byTicker[t]) byTicker[t] = { shares: 0, current_value: 0 };
      byTicker[t].shares        += h.shares;
      byTicker[t].current_value += h.current_value;
    }
    summaryEntries = Object.entries(byTicker)
      .filter(([, s]) => Math.abs(Math.round(Number(s.current_value) * 100) / 100) > 0.01)
      .sort(([, a], [, b]) => b.current_value - a.current_value);
  }

  if (summaryEntries.length) {
    const totalShares = summaryEntries.reduce((sum, [, s]) => sum + s.shares, 0);
    const totalValue  = summaryEntries.reduce((sum, [, s]) => sum + s.current_value, 0);
    const summaryRows = summaryEntries.map(([ticker, s]) => {
        const sharesStr  = s.shares !== 0 ? parseFloat(s.shares.toFixed(6)).toString() : '—';
        const sellButton = (ticker !== '—' && ticker !== '$$CASH')
          ? `<button class="btn btn-sm btn-warning" onclick="sellAllTicker('${esc(ticker)}')">Sell All</button>`
          : '';
        return `<tr>
          <td style="padding:0.2rem 1.5rem 0.2rem 0"><strong>${esc(ticker)}</strong></td>
          <td style="padding:0.2rem 1.5rem 0.2rem 0;text-align:right">${sharesStr}</td>
          <td style="padding:0.2rem 1.5rem 0.2rem 0;text-align:right">${fmt(s.current_value)}</td>
          <td style="padding:0.2rem 0">${sellButton}</td>
        </tr>`;
      }).join('');
    const totalSharesStr = totalShares !== 0 ? parseFloat(totalShares.toFixed(6)).toString() : '—';
    const totalRow = `<tr style="border-top:2px solid var(--border,#dee2e6)">
      <td style="padding:0.3rem 1.5rem 0.2rem 0"><strong>Total</strong></td>
      <td style="padding:0.3rem 1.5rem 0.2rem 0;text-align:right"><strong>${totalSharesStr}</strong></td>
      <td style="padding:0.3rem 1.5rem 0.2rem 0;text-align:right"><strong>${fmt(totalValue)}</strong></td>
      <td></td>
    </tr>`;
    summaryEl.innerHTML = `
      <div style="font-size:0.8rem;color:var(--text-muted,#6c757d);margin-bottom:0.35rem;text-transform:uppercase;letter-spacing:0.05em">Summary by ticker</div>
      <table style="border-collapse:collapse;font-size:0.9rem">
        <thead><tr>
          <th style="text-align:left;padding:0.2rem 1.5rem 0.2rem 0;border-bottom:1px solid var(--border,#dee2e6)">Ticker</th>
          <th style="text-align:right;padding:0.2rem 1.5rem 0.2rem 0;border-bottom:1px solid var(--border,#dee2e6)">Total Shares</th>
          <th style="text-align:right;padding:0.2rem 1.5rem 0.2rem 0;border-bottom:1px solid var(--border,#dee2e6)">Total Current Value</th>
          <th style="border-bottom:1px solid var(--border,#dee2e6)"></th>
        </tr></thead>
        <tbody>${summaryRows}${totalRow}</tbody>
      </table>`;
    summaryEl.style.display = 'block';
  } else {
    summaryEl.style.display = 'none';
    summaryEl.innerHTML = '';
  }

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="13" class="text-center text-muted" style="padding:2rem">
      No holdings match your search.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(h => {
    const cls   = h.gain >= 0 ? 'text-success' : 'text-danger';
    const notes = h.notes ? `<br><small class="text-muted">${esc(h.notes)}</small>` : '';
    return `
    <tr>
      <td style="white-space:nowrap"><strong>${esc(h.name)}</strong>${notes}</td>
      <td>${esc(h.ticker) || '—'}</td>
      <td>${h.purchase_date || '—'}</td>
      <td class="text-right">${h.shares !== 0 ? h.shares : '—'}</td>
      <td class="text-right">${h.pps !== 0 ? fmt(h.pps) : '—'}</td>
      <td class="text-right">${fmt(h.current_value)}</td>
      <td class="text-right">${fmt(h.cost_basis)}</td>
      <td class="text-right ${cls}">${fmt(h.gain)}</td>
      <td class="text-right ${cls}">${(h.gain >= 0 ? '+' : '')}${h.gainPct.toFixed(2)}%</td>
      <td>${esc(h.category) || '—'}</td>
      <td>${esc(h.owner) || '—'}</td>
      <td>${esc(h.account_type) || '—'}</td>
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
    document.getElementById('purchaseDate').value  = h.purchase_date;
    document.getElementById('notes').value         = h.notes;
    document.getElementById('owner').value         = h.owner || '';
    document.getElementById('accountType').value   = h.account_type || '';
  } else {
    title.textContent     = 'Add Holding';
    submitBtn.textContent = 'Add Holding';
    document.getElementById('holdingForm').reset();
    document.getElementById('holdingId').value    = '';
    document.getElementById('assetType').value    = 'etf';
    document.getElementById('purchaseDate').value = new Date().toISOString().slice(0, 10);
  }

  document.getElementById('modalOverlay').classList.add('open');
  document.getElementById('ticker').focus();
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
    owner:         document.getElementById('owner').value,
    account_type:  document.getElementById('accountType').value,
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

async function sellAllTicker(ticker) {
  const matches = getFilteredHoldings().filter(h => (h.ticker || '—') === ticker);
  if (!matches.length) return;

  const totalShares = matches.reduce((sum, x) => sum + x.shares, 0);
  const totalValue  = matches.reduce((sum, x) => sum + x.current_value, 0);

  if (Math.abs(totalShares) < 1e-6 && Math.abs(Math.round(totalValue * 100) / 100) <= 0.01) {
    alert(`${ticker} is already fully sold.`);
    return;
  }

  // A ticker can be split across multiple owner/account combos; the backend
  // only closes one combo per call, so fan out to every combo shown here.
  const groups = [...new Map(
    matches.map(h => [`${h.owner} ${h.account_type}`, { owner: h.owner, account_type: h.account_type }])
  ).values()];

  const sharesStr  = parseFloat(totalShares.toFixed(6));
  const groupLabel = groups.length > 1
    ? `across ${groups.length} owner/account groups`
    : `(${groups[0].owner || 'Unassigned'} / ${groups[0].account_type || 'Unassigned'})`;
  if (!confirm(
    `Sell all ${sharesStr} shares of ${ticker} ${groupLabel}?\n\n` +
    `This replaces all matching lots with closed $0 positions (currently ${fmt(totalValue)}).`
  )) return;

  const errors = [];
  for (const g of groups) {
    const res = await fetch('/api/holdings/sell-all', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ticker, owner: g.owner, account_type: g.account_type }),
    });
    if (!res.ok) {
      const result = await res.json();
      errors.push(result.error ?? `Failed for ${g.owner || 'Unassigned'} / ${g.account_type || 'Unassigned'}`);
    }
  }

  loadHoldings();
  if (errors.length) alert(errors.join('\n'));
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

async function importCsv(input) {
  const file = input.files && input.files[0];
  if (!file) return;

  const status = document.getElementById('refreshStatus');
  const btn    = document.getElementById('importBtn');

  status.style.display = 'none';
  status.className     = 'alert';
  btn.disabled          = true;
  btn.textContent       = 'Importing…';

  try {
    const formData = new FormData();
    formData.append('file', file);
    const res  = await fetch('/api/import/csv', { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok) {
      const rowMsgs = (data.row_errors || []).map(e => `Row ${e.row}: ${e.error}`);
      status.textContent = rowMsgs.length
        ? `${data.error} — ${rowMsgs.join('; ')}`
        : (data.error || 'Import failed.');
      status.classList.add('alert-danger');
    } else {
      status.textContent = `Imported ${data.imported} holding(s).`;
      status.classList.add('alert-success');
      loadHoldings();
    }
    status.style.display = 'block';
  } catch (err) {
    status.textContent   = `Request failed: ${err.message}`;
    status.style.display = 'block';
    status.classList.add('alert-danger');
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Import CSV';
    input.value     = '';
  }
}

async function fetchPrice() {
  const ticker = document.getElementById('ticker').value.trim().toUpperCase();
  if (!ticker) return;

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
    if (editingId === null) document.getElementById('costBasis').value = shares.toFixed(2);
    return;
  }
  if (fetchedPrice === null) return;
  const cv = (shares * fetchedPrice).toFixed(2);
  document.getElementById('currentValue').value = cv;
  if (editingId === null) document.getElementById('costBasis').value = cv;
}

document.addEventListener('DOMContentLoaded', () => {
  loadHoldings();
  document.getElementById('holdingsSearch').addEventListener('input', renderTable);
  document.getElementById('shares').addEventListener('input', recalcCurrentValue);

  let fetchTimer = null;
  document.getElementById('ticker').addEventListener('input', () => {
    const val = document.getElementById('ticker').value.toUpperCase();
    if (val === '$$CASH') {
      document.getElementById('assetType').value = 'cash';
      recalcCurrentValue();
      return;
    }
    clearTimeout(fetchTimer);
    fetchTimer = setTimeout(fetchPrice, 600);
  });
});
