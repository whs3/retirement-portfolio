'use strict';

let wdChart = null;

function fmt(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Withdrawal projection ─────────────────────────────────────────────────────

let wdSaveTimer  = null;
let wdFetchToken = 0;

function currentWdInputs() {
  return {
    rate:           document.getElementById('wdRate').value,
    return_rate:    document.getElementById('wdReturn').value,
    inflation_rate: document.getElementById('wdInflation').value,
    years:          document.getElementById('wdYears').value,
    ordinary_tax:   document.getElementById('wdOrdinaryTax').value,
    gains_tax:      document.getElementById('wdGainsTax').value,
  };
}

async function loadWithdrawal(useDefaults) {
  const status = document.getElementById('wdStatus');
  const token  = ++wdFetchToken;

  const params = new URLSearchParams();
  if (!useDefaults) {
    Object.entries(currentWdInputs()).forEach(([key, value]) => {
      if (value !== '') params.set(key, value);
    });
  }
  status.textContent = 'Calculating…';

  try {
    const res  = await fetch('/api/withdrawal?' + params.toString());
    const data = await res.json();
    if (token !== wdFetchToken) return;  // a newer input has since superseded this request

    if (!res.ok) {
      status.textContent = data.error || 'Failed to calculate projection.';
      return;
    }
    status.textContent = '';

    if (useDefaults) {
      document.getElementById('wdRate').value        = data.assumptions.annual_rate_pct;
      document.getElementById('wdReturn').value      = data.assumptions.expected_return_pct;
      document.getElementById('wdInflation').value   = data.assumptions.inflation_pct;
      document.getElementById('wdYears').value       = data.assumptions.years;
      document.getElementById('wdOrdinaryTax').value = data.assumptions.ordinary_tax_pct;
      document.getElementById('wdGainsTax').value    = data.assumptions.gains_tax_pct;
    }

    renderWithdrawalSummary(data);
    renderWithdrawalChart(data);
    renderWithdrawalTable(data);
  } catch (err) {
    if (token !== wdFetchToken) return;
    status.textContent = `Request failed: ${err.message}`;
  }
}

function renderWithdrawalSummary(data) {
  const el = document.getElementById('wdSummary');
  if (!data.rows.length) {
    el.style.display = 'none';
    return;
  }
  const lastRow = data.rows[data.rows.length - 1];
  const first = data.rows[0];
  let text;
  if (data.depletion_year != null) {
    const row = data.rows[data.depletion_year - 1];
    el.className = 'alert alert-warning';
    text = `Starting from ${fmt(data.starting_balance)}, the portfolio is projected to run out `
      + `in year ${data.depletion_year} (${row.calendar_year}) at these assumptions.`;
  } else {
    el.className = 'alert alert-success';
    text = `Starting from ${fmt(data.starting_balance)}, the portfolio is projected to last the `
      + `full ${data.assumptions.years} years, ending around ${fmt(lastRow.end_balance)} in ${lastRow.calendar_year}.`;
  }
  if (first.rmd > first.planned_withdrawal + 0.5) {
    text += ` In ${first.calendar_year} the required distribution of ${fmt(first.rmd)} is above the `
      + `${data.assumptions.annual_rate_pct}% withdrawal, so the plan withdraws ${fmt(first.withdrawal)}.`;
  }
  if (first.tax > 0.5) {
    text += ` About ${fmt(first.spendable)} of that is spendable after an estimated ${fmt(first.tax)} in tax.`;
  }
  const buckets = data.tax_buckets;
  if (buckets) {
    text += ` Today's mix is ${fmt(buckets.pretax)} pre-tax, ${fmt(buckets.taxable)} taxable, and ${fmt(buckets.roth)} Roth.`;
  }
  el.textContent = text;
  el.style.display = 'block';
}

function renderWithdrawalChart(data) {
  const wrap = document.getElementById('wdChartWrap');
  if (!data.rows.length) {
    wrap.style.display = 'none';
    if (wdChart) { wdChart.destroy(); wdChart = null; }
    return;
  }
  wrap.style.display = '';

  const labels = data.rows.map(r => r.calendar_year);
  const values = data.rows.map(r => r.end_balance);
  const depleted = data.depletion_year != null;
  const color = depleted ? '#dc2626' : '#16a34a';

  const ctx = document.getElementById('wdChart').getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 320);
  gradient.addColorStop(0, color + '33');
  gradient.addColorStop(1, color + '00');

  if (wdChart) wdChart.destroy();
  wdChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data:             values,
        borderColor:      color,
        borderWidth:      2,
        backgroundColor:  gradient,
        fill:             true,
        pointRadius:      0,
        pointHoverRadius: 4,
        tension:          0.2,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ' Balance: ' + fmt(ctx.parsed.y) } },
      },
      scales: {
        x: { grid: { display: false } },
        y: { ticks: { callback: v => fmt(v) }, grid: { color: '#f1f5f9' } },
      },
    },
  });
}

function renderWithdrawalTable(data) {
  const wrap = document.getElementById('wdTableWrap');
  const body = document.getElementById('wdTableBody');
  if (!data.rows.length) {
    wrap.style.display = 'none';
    return;
  }
  body.innerHTML = data.rows.map(r => {
    const sources = r.sources || {};
    const taxTitle = `Pre-tax ${fmt(sources.pretax || 0)}, taxable ${fmt(sources.taxable || 0)}, Roth ${fmt(sources.roth || 0)}`;
    return `
    <tr>
      <td>${r.year} (${r.calendar_year})</td>
      <td class="text-right">${fmt(r.start_balance)}</td>
      <td class="text-right">${fmt(r.planned_withdrawal)}</td>
      <td class="text-right">${r.rmd ? fmt(r.rmd) : '—'}</td>
      <td class="text-right">${fmt(r.withdrawal)}</td>
      <td class="text-right" title="${esc(taxTitle)}">${r.tax ? fmt(r.tax) : '—'}</td>
      <td class="text-right">${fmt(r.spendable)}</td>
      <td class="text-right">${fmt(r.end_balance)}</td>
    </tr>`;
  }).join('');
  wrap.style.display = '';
}

function queueWithdrawalSave() {
  clearTimeout(wdSaveTimer);
  wdSaveTimer = setTimeout(async () => {
    const inputs = currentWdInputs();
    try {
      await apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          withdrawal_rate:            inputs.rate,
          withdrawal_return_rate:     inputs.return_rate,
          withdrawal_inflation_rate:  inputs.inflation_rate,
          withdrawal_years:           inputs.years,
          tax_rate_ordinary:          inputs.ordinary_tax,
          tax_rate_gains:             inputs.gains_tax,
        }),
      });
      loadRmd();
    } catch (err) {
      const status = document.getElementById('wdStatus');
      if (status) status.textContent = err.message || 'Save failed.';
      console.error('saving withdrawal assumptions failed:', err);
    }
  }, 500);
  loadWithdrawal(false);
}

// ── RMD tracking ──────────────────────────────────────────────────────────────

function statusLabel(o) {
  if (!o.birthdate) return '<span class="text-muted">Enter birthdate</span>';
  if (o.required) return '<span class="text-danger">Required</span>';
  return `<span class="text-muted">In ${o.years_until_required} yr${o.years_until_required === 1 ? '' : 's'} (age ${o.rmd_start_age})</span>`;
}

async function loadRmd() {
  const body = document.getElementById('rmdBody');
  try {
    const data = await apiFetch('/api/rmd');

    const note = document.getElementById('rmdBalanceNote');
    if (note) note.textContent = data.balance_note || '';

    const billInput  = document.getElementById('birthdateBill');
    const akikoInput = document.getElementById('birthdateAkiko');
    const owners = {};
    data.owners.forEach(o => { owners[o.owner] = o; });
    if (document.activeElement !== billInput)  billInput.value  = owners['Bill']?.birthdate  || '';
    if (document.activeElement !== akikoInput) akikoInput.value = owners['Akiko']?.birthdate || '';

    body.innerHTML = data.owners.map(o => `
      <tr>
        <td>${esc(o.owner)}</td>
        <td class="text-right">${o.age != null ? o.age : '—'}</td>
        <td class="text-right">${o.rmd_start_age != null ? o.rmd_start_age : '—'}</td>
        <td>${statusLabel(o)}</td>
        <td class="text-right">${fmt(o.balance)}</td>
        <td class="text-right">${o.distribution_period != null ? o.distribution_period : '—'}</td>
        <td class="text-right">${o.rmd_amount ? fmt(o.rmd_amount) : '—'}</td>
      </tr>`).join('');

    renderRmdProjection(owners, data.projection_assumptions);
  } catch (err) {
    body.innerHTML = `<tr><td colspan="7" class="text-center text-danger">Failed to load: ${esc(err.message)}</td></tr>`;
  }
}

function renderRmdProjection(owners, assumptions) {
  const wrap = document.getElementById('rmdProjectionWrap');
  const note = document.getElementById('rmdProjectionNote');
  const body = document.getElementById('rmdProjectionBody');

  const bill  = owners['Bill']?.projection  || [];
  const akiko = owners['Akiko']?.projection || [];
  const rowCount = Math.max(bill.length, akiko.length);

  if (rowCount === 0) {
    wrap.style.display = 'none';
    return;
  }

  note.textContent =
    `Projected using the ${assumptions.return_rate_pct}% expected annual return and ` +
    `${assumptions.years}-year horizon set in the withdrawal calculator above; balances shown ` +
    `are reduced by each year's RMD and then grown at that rate.`;

  const rows = [];
  for (let i = 0; i < rowCount; i++) {
    const b = bill[i];
    const a = akiko[i];
    const calendarYear = (b || a).calendar_year;
    const combined = (b?.rmd_amount || 0) + (a?.rmd_amount || 0);
    rows.push(`
      <tr>
        <td>${calendarYear}</td>
        <td class="text-right">${b ? b.age : '—'}</td>
        <td class="text-right">${b?.rmd_amount ? fmt(b.rmd_amount) : '—'}</td>
        <td class="text-right">${a ? a.age : '—'}</td>
        <td class="text-right">${a?.rmd_amount ? fmt(a.rmd_amount) : '—'}</td>
        <td class="text-right">${combined ? fmt(combined) : '—'}</td>
      </tr>`);
  }
  body.innerHTML = rows.join('');
  wrap.style.display = '';
}

let rmdSaveTimer = null;

function queueBirthdateSave(key, value) {
  const status = document.getElementById('rmdSaveStatus');
  clearTimeout(rmdSaveTimer);
  status.textContent = 'Saving…';
  rmdSaveTimer = setTimeout(async () => {
    try {
      await apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });
      status.textContent = 'Saved.';
      loadRmd();
      loadWithdrawal(false);
    } catch (err) {
      status.textContent = err.message || 'Save failed.';
    }
  }, 400);
}

document.addEventListener('DOMContentLoaded', () => {
  loadWithdrawal(true);
  loadRmd();

  ['wdRate', 'wdReturn', 'wdInflation', 'wdYears', 'wdOrdinaryTax', 'wdGainsTax'].forEach(id => {
    document.getElementById(id).addEventListener('input', queueWithdrawalSave);
  });

  document.getElementById('birthdateBill').addEventListener('change', (e) => {
    queueBirthdateSave('birthdate_bill', e.target.value);
  });
  document.getElementById('birthdateAkiko').addEventListener('change', (e) => {
    queueBirthdateSave('birthdate_akiko', e.target.value);
  });
});
