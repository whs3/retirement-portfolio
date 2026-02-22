'use strict';

const ACTION_CLASS = {
  ADD:    'badge-buy',
  EDIT:   'badge-hold',
  DELETE: 'badge-sell',
};

function fmtDollar(s) {
  if (!s) return '—';
  // s is already like "$4200.00" from the log; parse and reformat
  const n = parseFloat(s.replace('$', ''));
  if (isNaN(n)) return s;
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function fmtChange(s) {
  if (!s) return '—';
  const n = parseFloat(s.replace('$', ''));
  if (isNaN(n)) return s;
  const formatted = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Math.abs(n));
  if (n > 0)  return `<span class="text-success">+${formatted}</span>`;
  if (n < 0)  return `<span class="text-danger">−${formatted}</span>`;
  return `<span class="text-muted">${formatted}</span>`;
}

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

let pollTimer      = null;
let lastEntryCount = -1;

async function loadAuditLog() {
  const res     = await fetch('/api/audit');
  const entries = await res.json();

  // Update count + "last refreshed" indicator
  document.getElementById('entryCount').textContent =
    entries.length === 1 ? '1 entry' : `${entries.length} entries`;
  document.getElementById('lastRefreshed').textContent =
    'Refreshed ' + new Date().toLocaleTimeString();

  // Skip re-rendering the table if nothing has changed
  if (entries.length === lastEntryCount) return;
  lastEntryCount = entries.length;

  const tbody = document.getElementById('auditBody');
  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No audit entries yet.</td></tr>';
    return;
  }

  tbody.innerHTML = entries.map(e => {
    const f          = e.fields;
    const actionCls  = ACTION_CLASS[e.action] ?? 'badge-hold';
    const ticker     = e.ticker && e.ticker !== '—' ? esc(e.ticker) : '<span class="text-muted">—</span>';

    return `
    <tr>
      <td style="white-space:nowrap;font-variant-numeric:tabular-nums">${esc(e.timestamp)}</td>
      <td><span class="badge ${actionCls}">${esc(e.action)}</span></td>
      <td>${ticker}</td>
      <td>${esc(e.name)}</td>
      <td class="text-right">${fmtDollar(f.current_value)}</td>
      <td class="text-right">${fmtDollar(f.cost_basis)}</td>
      <td class="text-right">${fmtChange(f.value_change)}</td>
      <td class="text-right">${fmtChange(f.cost_basis_change)}</td>
    </tr>`;
  }).join('');
}

function applyPollInterval() {
  const ms = parseInt(document.getElementById('pollInterval').value, 10);
  clearInterval(pollTimer);
  if (ms > 0) pollTimer = setInterval(loadAuditLog, ms);
}

document.addEventListener('DOMContentLoaded', () => {
  loadAuditLog();
  applyPollInterval();
  document.getElementById('pollInterval').addEventListener('change', applyPollInterval);
});
