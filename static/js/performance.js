'use strict';

let perfChart = null;

function fmt(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function fmtK(n) {
  if (Math.abs(n) >= 1_000_000) return '$' + (n / 1_000_000).toFixed(2) + 'M';
  if (Math.abs(n) >= 1_000)     return '$' + (n / 1_000).toFixed(1) + 'K';
  return fmt(n);
}

async function loadPerformance() {
  const loading = document.getElementById('loadingMsg');
  loading.className     = 'alert';
  loading.textContent   = 'Fetching 12 months of price history — this may take a moment…';
  loading.style.display = 'block';

  ['summaryCards','chartCard','monthlyCard','untrackedNotice'].forEach(id => {
    document.getElementById(id).style.display = 'none';
  });

  try {
    const res  = await fetch('/api/performance');
    const data = await res.json();

    loading.style.display = 'none';

    if (!res.ok) {
      loading.classList.add('alert-danger');
      loading.textContent   = data.error ?? 'Failed to load performance data.';
      loading.style.display = 'block';
      return;
    }

    if (!data.dates || !data.dates.length) {
      loading.classList.add('alert-danger');
      loading.textContent   = 'No price history available. Add holdings with ticker symbols to see performance.';
      loading.style.display = 'block';
      return;
    }

    document.getElementById('asOfDate').textContent =
      'As of ' + new Date().toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });

    renderSummary(data.summary);
    renderChart(data.dates, data.values);
    renderMonthly(data.monthly);

    if (data.untracked && data.untracked.length) {
      const msg = document.getElementById('untrackedMsg');
      msg.innerHTML = `<strong>Note:</strong> The following tickers had no price history and are included at their current value: ${data.untracked.map(t => `<strong>${t}</strong>`).join(', ')}.`;
      document.getElementById('untrackedNotice').style.display = 'block';
    }

  } catch (err) {
    loading.classList.add('alert-danger');
    loading.textContent   = `Request failed: ${err.message}`;
    loading.style.display = 'block';
  }
}

function renderSummary(s) {
  const pos = s.gain >= 0;

  document.getElementById('startValue').textContent = fmt(s.start_value);
  document.getElementById('endValue').textContent   = fmt(s.end_value);
  document.getElementById('peakValue').textContent  = fmt(s.peak_value);

  const gainEl  = document.getElementById('gainValue');
  const pctEl   = document.getElementById('gainPct');
  gainEl.textContent = fmt(s.gain);
  gainEl.className   = 'card-value ' + (pos ? 'text-success' : 'text-danger');
  pctEl.textContent  = (pos ? '+' : '') + s.gain_pct.toFixed(2) + '%';
  pctEl.className    = 'card-sub '    + (pos ? 'text-success' : 'text-danger');

  document.getElementById('summaryCards').style.display = '';
}

function renderChart(dates, values) {
  const canvas = document.getElementById('performanceChart');
  const ctx    = canvas.getContext('2d');

  const isUp  = values[values.length - 1] >= values[0];
  const color = isUp ? '#16a34a' : '#dc2626';

  // First trading day of each month (handles weekends/holidays on the 1st)
  const monthStarts = new Set();
  const seenMonths  = new Set();
  for (const d of dates) {
    const ym = d.slice(0, 7);   // "YYYY-MM"
    if (!seenMonths.has(ym)) { seenMonths.add(ym); monthStarts.add(d); }
  }

  const gradient = ctx.createLinearGradient(0, 0, 0, 320);
  gradient.addColorStop(0,   color + '33');
  gradient.addColorStop(1,   color + '00');

  // Plugin: draw a vertical grid line for each month start
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
        c.beginPath();
        c.moveTo(x, top);
        c.lineTo(x, bottom);
        c.stroke();
      }
      c.restore();
    },
  };

  if (perfChart) perfChart.destroy();

  perfChart = new Chart(ctx, {
    type:    'line',
    plugins: [monthGridPlugin],
    data: {
      labels: dates,
      datasets: [{
        data:            values,
        borderColor:     color,
        borderWidth:     2,
        backgroundColor: gradient,
        fill:            true,
        pointRadius:     0,
        pointHoverRadius: 4,
        tension:         0.3,
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
            label: ctx => ' Portfolio Value: ' + fmt(ctx.parsed.y),
          },
        },
      },
      scales: {
        x: {
          type: 'category',
          ticks: {
            autoSkip:    false,
            maxRotation: 0,
            callback(val, i) {
              const d = this.getLabelForValue(val);
              if (!d) return null;
              if (monthStarts.has(d)) {
                return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
              }
              return null;
            },
          },
          grid: { display: false },
        },
        y: {
          ticks: { callback: v => fmtK(v) },
          grid:  { color: '#f1f5f9' },
        },
      },
    },
  });

  document.getElementById('chartCard').style.display = '';
}

function renderMonthly(monthly) {
  if (!monthly || !monthly.length) return;

  document.getElementById('monthlyBody').innerHTML = [...monthly].reverse().map(m => {
    const pos = m.gain >= 0;
    const cls = pos ? 'text-success' : 'text-danger';
    return `<tr>
      <td>${m.month}</td>
      <td class="text-right">${fmt(m.start)}</td>
      <td class="text-right">${fmt(m.end)}</td>
      <td class="text-right ${cls}">${pos ? '+' : ''}${fmt(m.gain)}</td>
      <td class="text-right ${cls}">${pos ? '+' : ''}${m.gain_pct.toFixed(2)}%</td>
    </tr>`;
  }).join('');

  document.getElementById('monthlyCard').style.display = '';
}

document.addEventListener('DOMContentLoaded', loadPerformance);
