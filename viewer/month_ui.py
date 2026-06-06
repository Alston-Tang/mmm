MONTH_SUMMARY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MMM — Month Summary</title>
  <style>
    :root {
      --bg: #0f1419;
      --surface: #1a2332;
      --border: #2d3a4d;
      --text: #e7ecf3;
      --muted: #8b9cb3;
      --accent: #5b9fd4;
      --green: #6bcb8a;
      --red: #e07a7a;
      --yellow: #e6c07b;
    }
    * { box-sizing: border-box; }
    body {
      font-family: "SF Pro Text", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 1.5rem;
      line-height: 1.5;
    }
    h1 { font-size: 1.35rem; font-weight: 600; margin: 0 0 0.75rem; }
    h2 { font-size: 1rem; font-weight: 600; margin: 1.5rem 0 0.75rem; }
    .flow-section { margin-bottom: 1.5rem; }
    .flow-section h3 {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.95rem;
      font-weight: 600;
      margin: 0 0 0.5rem;
    }
    .flow-section .flow-total { color: var(--muted); font-size: 0.85rem; font-weight: 400; }
    .nav { display: flex; gap: 1rem; margin-bottom: 1rem; font-size: 0.9rem; }
    .nav a { color: var(--accent); text-decoration: none; }
    .nav a.active { color: var(--text); font-weight: 600; pointer-events: none; }
    .toolbar {
      display: flex;
      gap: 0.75rem;
      align-items: end;
      flex-wrap: wrap;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
      margin-bottom: 1rem;
    }
    label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.75rem; color: var(--muted); }
    select, button {
      font: inherit;
      padding: 0.45rem 0.6rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
    }
    button {
      cursor: pointer;
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 500;
    }
    .meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 0.75rem; }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
      gap: 0.75rem;
      margin-bottom: 0.5rem;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
    }
    .card-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }
    .card-value { font-size: 1.5rem; font-weight: 600; margin: 0.25rem 0; font-variant-numeric: tabular-nums; }
    .card-sub { font-size: 0.8rem; color: var(--muted); }
    .income .card-value { color: var(--green); }
    .consumption .card-value { color: var(--red); }
    .transfer .card-value { color: var(--yellow); }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th, td { padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }
    th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
    tr:hover td { background: rgba(255,255,255,0.03); }
    .badge {
      display: inline-block;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      font-size: 0.7rem;
    }
    .badge.addition { background: rgba(107,203,138,0.15); color: var(--green); }
    .badge.reduction { background: rgba(224,122,122,0.15); color: var(--red); }
    .badge.transfer { background: rgba(230,192,123,0.15); color: var(--yellow); }
    .empty { text-align: center; padding: 3rem; color: var(--muted); }
    .err { color: var(--red); font-size: 0.85rem; }
    .category-row { cursor: pointer; }
    .category-row:hover td { background: rgba(255,255,255,0.05); }
    .category-name { display: flex; align-items: center; gap: 0.4rem; }
    .chevron {
      display: inline-block;
      color: var(--muted);
      font-size: 0.75rem;
      transition: transform 0.15s ease;
    }
    .category-row.expanded .chevron { transform: rotate(90deg); }
    .category-detail-row td {
      padding: 0;
      background: rgba(255,255,255,0.02);
      border-bottom: 1px solid var(--border);
    }
    .tx-panel { padding: 0.35rem 0.75rem 0.75rem 2rem; }
    .tx-list { list-style: none; margin: 0; padding: 0; }
    .tx-list li {
      border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .tx-list li:last-child { border-bottom: none; }
    .tx-link {
      display: grid;
      grid-template-columns: 6.5rem 1fr auto;
      gap: 0.75rem;
      align-items: baseline;
      color: inherit;
      text-decoration: none;
      padding: 0.4rem 0;
      font-size: 0.8rem;
    }
    .tx-link:hover .tx-desc { color: var(--accent); }
    .tx-date { color: var(--muted); }
    .tx-amount { font-variant-numeric: tabular-nums; text-align: right; }
    .tx-empty { color: var(--muted); font-size: 0.8rem; padding: 0.25rem 0; }
  </style>
</head>
<body>
  <nav class="nav">
    <a href="/">Transactions</a>
    <a href="/month" class="active">Month summary</a>
  </nav>
  <h1>Month Summary</h1>
  <div class="toolbar">
    <label>Month
      <select id="month-select"></select>
    </label>
    <button type="button" id="load-btn">View</button>
  </div>
  <div class="meta" id="summary">Select a month to view income, consumption, and transfers.</div>
  <div class="cards" id="cards"></div>
  <h2>By flow and category</h2>
  <div id="category-wrap"></div>
  <div class="err" id="error" style="display:none"></div>
  <script>
    const api = window.location.origin + '/api/v1';
    let currentMonth = '';
    const txCache = new Map();
    const expanded = new Set();
    let categoriesBound = false;

    function categoryKey(flow, category) {
      return `${currentMonth}|${flow}|${category}`;
    }

    function renderTransactionList(items, flow, category) {
      if (!items.length) {
        return '<div class="tx-empty">No transactions.</div>';
      }
      return `<ul class="tx-list">${items.map(tx => `
        <li>
          <a class="tx-link" href="${viewerTxUrl(tx, flow, category)}">
            <span class="tx-date">${esc(tx.transaction_date || '—')}</span>
            <span class="tx-desc">${esc(tx.description)}</span>
            <span class="tx-amount">${fmtMoney(tx.amount_usd)}</span>
          </a>
        </li>`).join('')}</ul>`;
    }

    function monthBounds(month) {
      const [y, m] = month.split('-').map(Number);
      const last = new Date(y, m, 0).getDate();
      return {
        from: `${month}-01`,
        to: `${month}-${String(last).padStart(2, '0')}`,
      };
    }

    function viewerTxUrl(tx, flow, category) {
      const bounds = monthBounds(currentMonth);
      const p = new URLSearchParams({
        analyzed_transaction_id: tx.analyzed_transaction_id,
        view: 'analyzed',
        date_from: bounds.from,
        date_to: bounds.to,
        flow_direction: flow,
        category,
      });
      return `/?${p}`;
    }

    async function toggleCategory(row) {
      const flow = row.dataset.flow;
      const category = row.dataset.category;
      const detail = row.nextElementSibling;
      if (!detail || !detail.classList.contains('category-detail-row')) return;

      const key = categoryKey(flow, category);
      if (expanded.has(key)) {
        expanded.delete(key);
        row.classList.remove('expanded');
        detail.style.display = 'none';
        return;
      }

      expanded.add(key);
      row.classList.add('expanded');
      detail.style.display = '';
      const panel = detail.querySelector('.tx-panel');

      if (txCache.has(key)) {
        panel.innerHTML = renderTransactionList(txCache.get(key), flow, category);
        return;
      }

      panel.innerHTML = '<span class="meta">Loading…</span>';
      try {
        const params = new URLSearchParams({ flow_direction: flow, category });
        const res = await fetch(
          `${api}/months/${encodeURIComponent(currentMonth)}/transactions?${params}`,
        );
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load transactions');
        const items = data.items || [];
        txCache.set(key, items);
        panel.innerHTML = renderTransactionList(items, flow, category);
      } catch (err) {
        panel.innerHTML = `<span class="err">${esc(err.message)}</span>`;
        expanded.delete(key);
        row.classList.remove('expanded');
        detail.style.display = 'none';
      }
    }

    function bindCategoryClicks() {
      if (categoriesBound) return;
      document.getElementById('category-wrap').addEventListener('click', e => {
        if (e.target.closest('.tx-link')) return;
        const row = e.target.closest('.category-row');
        if (row) toggleCategory(row);
      });
      categoriesBound = true;
    }

    function esc(text) {
      if (text == null) return '';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function fmtMoney(n) {
      return '$' + Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function flowLabel(flow) {
      if (flow === 'addition') return 'Income';
      if (flow === 'reduction') return 'Consumption';
      if (flow === 'transfer') return 'Transfer';
      return flow || '—';
    }

    function flowBadge(flow) {
      const cls = flow === 'addition' ? 'addition' : flow === 'reduction' ? 'reduction' : flow === 'transfer' ? 'transfer' : '';
      return `<span class="badge ${cls}">${esc(flowLabel(flow))}</span>`;
    }

    function renderCards(data) {
      const cards = [
        { cls: 'income', label: 'Income', block: data.income },
        { cls: 'consumption', label: 'Consumption', block: data.consumption },
        { cls: 'transfer', label: 'Transfer', block: data.transfer },
      ];
      document.getElementById('cards').innerHTML = cards.map(c => `
        <div class="card ${c.cls}">
          <div class="card-label">${c.label}</div>
          <div class="card-value">${fmtMoney(c.block.total_usd)}</div>
          <div class="card-sub">${c.block.count} transaction${c.block.count === 1 ? '' : 's'}</div>
        </div>`).join('');
    }

    function renderCategories(byFlow) {
      const wrap = document.getElementById('category-wrap');
      const sections = byFlow || [];
      const hasRows = sections.some(s => (s.categories || []).length > 0);
      if (!hasRows) {
        wrap.innerHTML = '<div class="empty">No categorized transactions for this month.</div>';
        return;
      }

      wrap.innerHTML = sections.map(section => {
        const rows = section.categories || [];
        const flowCls = section.flow_direction === 'addition'
          ? 'addition'
          : section.flow_direction === 'reduction'
            ? 'reduction'
            : section.flow_direction === 'transfer'
              ? 'transfer'
              : '';
        const table = rows.length
          ? `<table>
              <thead><tr><th>Category</th><th class="num">Count</th><th class="num">Total (USD)</th></tr></thead>
              <tbody>${rows.map(r => `
                <tr class="category-row" data-flow="${esc(section.flow_direction)}" data-category="${esc(r.category)}">
                  <td class="category-name"><span class="chevron">▸</span>${esc(r.category)}</td>
                  <td class="num">${r.count}</td>
                  <td class="num">${fmtMoney(r.total_usd)}</td>
                </tr>
                <tr class="category-detail-row" style="display:none">
                  <td colspan="3"><div class="tx-panel"><span class="meta">Loading…</span></div></td>
                </tr>`).join('')}</tbody>
            </table>`
          : '<div class="empty" style="padding:1rem">No transactions in this flow.</div>';

        return `<section class="flow-section">
          <h3>
            <span class="badge ${flowCls}">${esc(section.label || flowLabel(section.flow_direction))}</span>
            <span class="flow-total">${fmtMoney(section.total_usd)} · ${section.count} transaction${section.count === 1 ? '' : 's'}</span>
          </h3>
          ${table}
        </section>`;
      }).join('');
      bindCategoryClicks();
    }

    async function loadMonths() {
      const res = await fetch(api + '/months');
      const data = await res.json();
      const select = document.getElementById('month-select');
      select.innerHTML = '';
      const months = data.months || [];
      if (!months.length) {
        select.innerHTML = '<option value="">No data</option>';
        return;
      }
      months.forEach(m => {
        const o = document.createElement('option');
        o.value = m.month;
        o.textContent = `${m.month} (${m.transaction_count} tx)`;
        select.appendChild(o);
      });
      const params = new URLSearchParams(window.location.search);
      const requested = params.get('month');
      if (requested && months.some(m => m.month === requested)) {
        select.value = requested;
      }
    }

    async function loadSummary() {
      const errEl = document.getElementById('error');
      errEl.style.display = 'none';
      const month = document.getElementById('month-select').value;
      if (!month) return;

      document.getElementById('summary').textContent = 'Loading…';
      try {
        const res = await fetch(api + '/months/' + encodeURIComponent(month));
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to load month summary');

        currentMonth = data.month;
        txCache.clear();
        expanded.clear();

        const net = data.income.total_usd - data.consumption.total_usd;
        document.getElementById('summary').textContent =
          `${data.month} · ${data.transaction_count} transactions · net ${fmtMoney(net)} (income − consumption)`;
        renderCards(data);
        renderCategories(data.by_flow || []);

        const url = new URL(window.location);
        url.searchParams.set('month', month);
        history.replaceState(null, '', url);
      } catch (err) {
        document.getElementById('summary').textContent = 'Failed to load summary.';
        errEl.textContent = err.message;
        errEl.style.display = 'block';
      }
    }

    document.getElementById('load-btn').onclick = loadSummary;
    document.getElementById('month-select').addEventListener('change', loadSummary);
    loadMonths().then(loadSummary);
  </script>
</body>
</html>"""
