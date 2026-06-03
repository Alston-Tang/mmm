VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MMM — Transaction Viewer</title>
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
      --orange: #f0a060;
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
    h1 { font-size: 1.35rem; font-weight: 600; margin: 0 0 1rem; }
    .filters {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
      gap: 0.75rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
      margin-bottom: 1rem;
    }
    label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.75rem; color: var(--muted); }
    input, select, button, textarea {
      font: inherit;
      padding: 0.45rem 0.6rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
    }
    textarea { resize: vertical; min-height: 2.2rem; }
    button {
      cursor: pointer;
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 500;
      align-self: end;
    }
    button.secondary { background: transparent; color: var(--text); border-color: var(--border); }
    button.save-btn { padding: 0.35rem 0.6rem; font-size: 0.75rem; align-self: auto; white-space: nowrap; }
    button.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .toolbar { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
    .meta { color: var(--muted); font-size: 0.85rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th, td { padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { color: var(--muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }
    tr:hover td { background: rgba(255,255,255,0.03); }
    tr.needs-attention td { background: rgba(240,160,96,0.06); }
    .amount-reduction { color: var(--red); }
    .amount-addition { color: var(--green); }
    .amount-transfer { color: var(--yellow); }
    .badge {
      display: inline-block;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      font-size: 0.7rem;
      background: rgba(91,159,212,0.15);
      color: var(--accent);
    }
    .badge.sub { background: rgba(230,192,123,0.15); color: var(--yellow); }
    .badge.attention { background: rgba(240,160,96,0.2); color: var(--orange); }
    .badge.queued { background: rgba(107,203,138,0.18); color: var(--green); }
    tr.pending-retry td { background: rgba(107,203,138,0.05); }
    .queued-comment {
      font-size: 0.8rem;
      color: var(--text);
      margin-bottom: 0.4rem;
      padding: 0.4rem 0.55rem;
      background: rgba(107,203,138,0.08);
      border-radius: 4px;
      border-left: 2px solid var(--green);
      white-space: pre-wrap;
    }
    .queued-comment-label { font-size: 0.7rem; color: var(--muted); margin-bottom: 0.15rem; }
    .comment-unavailable { font-size: 0.8rem; color: var(--muted); line-height: 1.4; }
    .pager { display: flex; gap: 0.5rem; margin-top: 1rem; align-items: center; }
    .empty { text-align: center; padding: 3rem; color: var(--muted); }
    .account { font-size: 0.75rem; color: var(--muted); }
    .comment-cell { min-width: 14rem; }
    .comment-row { display: flex; gap: 0.4rem; align-items: flex-start; }
    .comment-row textarea { flex: 1; font-size: 0.8rem; }
    .status-msg { font-size: 0.75rem; margin-top: 0.25rem; }
    .status-msg.ok { color: var(--green); }
    .status-msg.err { color: var(--red); }
    .attention-reason { font-size: 0.75rem; color: var(--orange); margin-top: 0.2rem; }
    .source-btn {
      padding: 0.3rem 0.55rem;
      font-size: 0.75rem;
      background: transparent;
      color: var(--accent);
      border-color: var(--border);
      align-self: auto;
    }
    .source-btn.active { background: rgba(91,159,212,0.15); border-color: var(--accent); }
    tr.source-detail-row td { padding: 0; background: rgba(91,159,212,0.04); border-bottom: 1px solid var(--border); }
    .source-panel {
      padding: 0.75rem 1rem 1rem;
      font-size: 0.8rem;
    }
    .source-panel h3 {
      margin: 0 0 0.6rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .source-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
      gap: 0.5rem 1.25rem;
    }
    .source-field dt { color: var(--muted); font-size: 0.7rem; margin: 0; }
    .source-field dd { margin: 0.1rem 0 0; word-break: break-word; }
    .source-id { font-family: ui-monospace, monospace; font-size: 0.72rem; color: var(--muted); margin-top: 0.5rem; }
  </style>
</head>
<body>
  <h1>Transaction Viewer</h1>
  <form class="filters" id="filters">
    <label>View<select name="view">
      <option value="">All</option>
      <option value="analyzed">Analyzed only</option>
      <option value="needs_attention">Needs attention only</option>
      <option value="pending_retry">Pending re-analysis</option>
    </select></label>
    <label>From<input type="date" name="date_from" /></label>
    <label>To<input type="date" name="date_to" /></label>
    <label>Category<select name="category"><option value="">All</option></select></label>
    <label>Flow<select name="flow_direction"><option value="">All</option></select></label>
    <label>Subscription<select name="is_subscription"><option value="">All</option><option value="true">Yes</option><option value="false">No</option></select></label>
    <label>Min amount<input type="number" name="min_amount" step="0.01" placeholder="0" /></label>
    <label>Max amount<input type="number" name="max_amount" step="0.01" placeholder="" /></label>
    <label>Min confidence<input type="number" name="min_confidence" step="0.01" min="0" max="1" placeholder="0" /></label>
    <label>Search<input type="search" name="q" placeholder="merchant, description..." /></label>
    <label>Sort by<select name="sort_by">
      <option value="transaction_date" selected>Date</option>
      <option value="amount_usd">Amount</option>
      <option value="category">Category</option>
      <option value="confidence">Confidence</option>
      <option value="created_at">Analyzed at</option>
      <option value="updated_at">Updated at</option>
    </select></label>
    <label>Order<select name="sort_order">
      <option value="desc" selected>Newest first</option>
      <option value="asc">Oldest first</option>
    </select></label>
    <button type="submit">Apply</button>
  </form>
  <div class="toolbar">
    <span class="meta" id="summary">Loading…</span>
  </div>
  <div id="table-wrap"></div>
  <div class="pager">
    <button type="button" class="secondary" id="prev" disabled>Previous</button>
    <span class="meta" id="page-info"></span>
    <button type="button" class="secondary" id="next" disabled>Next</button>
  </div>
  <script>
    const api = window.location.origin + '/api/v1';
    let offset = 0;
    let limit = 50;
    let total = 0;
    const sourceCache = new Map();

    function esc(text) {
      if (text == null) return '';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function fmtVal(value) {
      if (value == null || value === '') return '—';
      if (typeof value === 'boolean') return value ? 'Yes' : 'No';
      if (typeof value === 'object') return esc(JSON.stringify(value));
      return esc(value);
    }

    function sourceToggleButton(rowId, sourceId) {
      if (!sourceId) return '<span class="meta">—</span>';
      return `<button type="button" class="source-btn secondary" data-source-id="${esc(sourceId)}" data-detail-id="source-${esc(rowId)}">View source</button>`;
    }

    function sourceDetailRow(rowId, colSpan) {
      return `<tr class="source-detail-row" id="source-${esc(rowId)}" style="display:none">
        <td colspan="${colSpan}"><div class="source-panel"><span class="meta">Loading…</span></div></td>
      </tr>`;
    }

    function renderSourcePanel(src) {
      const pfc = src.personal_finance_category;
      const pfcText = pfc
        ? [pfc.primary, pfc.detailed].filter(Boolean).join(' / ')
        : null;
      const fields = [
        ['Date', src.date],
        ['Authorized', src.authorized_date],
        ['Amount', src.amount != null ? `${src.amount} ${src.iso_currency_code || ''}`.trim() : null],
        ['Name', src.name],
        ['Merchant', src.merchant_name],
        ['Original description', src.original_description],
        ['Payment channel', src.payment_channel],
        ['Pending', src.pending],
        ['Plaid category', pfcText],
        ['Account', src.account_display_name || src.account_name],
        ['Account type', [src.account_type, src.account_subtype].filter(Boolean).join(' / ') || null],
        ['Account mask', src.account_mask ? `••••${src.account_mask}` : null],
        ['Institution', src.item_label],
        ['Synced at', src.synced_at],
      ];
      const grid = fields.map(([label, value]) =>
        `<div class="source-field"><dt>${esc(label)}</dt><dd>${fmtVal(value)}</dd></div>`
      ).join('');
      return `<h3>Original Plaid transaction</h3><div class="source-grid">${grid}</div>
        <div class="source-id">transaction_id: ${esc(src.transaction_id)}</div>`;
    }

    function renderSourcePanelFromMetadata(meta, sourceId) {
      const fields = [
        ['Date', meta.date],
        ['Authorized', meta.authorized_date],
        ['Amount', meta.amount != null ? `${meta.amount} ${meta.iso_currency_code || ''}`.trim() : null],
        ['Name', meta.name],
        ['Merchant', meta.merchant_name],
        ['Original description', meta.original_description],
        ['Payment channel', meta.payment_channel],
        ['Pending', meta.pending],
        ['Account', meta.account_display_name || meta.account_name],
        ['Account type', [meta.account_type, meta.account_subtype].filter(Boolean).join(' / ') || null],
        ['Institution', meta.item_label],
      ];
      const grid = fields.map(([label, value]) =>
        `<div class="source-field"><dt>${esc(label)}</dt><dd>${fmtVal(value)}</dd></div>`
      ).join('');
      return `<h3>Original transaction (cached snapshot)</h3><div class="source-grid">${grid}</div>
        <div class="source-id">transaction_id: ${esc(sourceId)}</div>
        <div class="meta" style="margin-top:0.4rem">Live Plaid record not found; showing metadata saved at analysis time.</div>`;
    }

    async function toggleSource(btn, fallbackMeta) {
      const sourceId = btn.dataset.sourceId;
      const detailRow = document.getElementById(btn.dataset.detailId);
      if (!detailRow) return;

      if (detailRow.style.display !== 'none') {
        detailRow.style.display = 'none';
        btn.textContent = 'View source';
        btn.classList.remove('active');
        return;
      }

      detailRow.style.display = '';
      btn.textContent = 'Hide source';
      btn.classList.add('active');
      const panel = detailRow.querySelector('.source-panel');

      if (sourceCache.has(sourceId)) {
        panel.innerHTML = renderSourcePanel(sourceCache.get(sourceId));
        return;
      }

      panel.innerHTML = '<span class="meta">Loading…</span>';
      try {
        const res = await fetch(api + '/source-transactions/' + encodeURIComponent(sourceId));
        const data = await res.json();
        if (!res.ok) {
          if (fallbackMeta && Object.keys(fallbackMeta).length) {
            panel.innerHTML = renderSourcePanelFromMetadata(fallbackMeta, sourceId);
            return;
          }
          throw new Error(data.detail || 'Source transaction not found');
        }
        sourceCache.set(sourceId, data);
        panel.innerHTML = renderSourcePanel(data);
      } catch (err) {
        if (fallbackMeta && Object.keys(fallbackMeta).length) {
          panel.innerHTML = renderSourcePanelFromMetadata(fallbackMeta, sourceId);
        } else {
          panel.innerHTML = `<span class="status-msg err">${esc(err.message)}</span>`;
        }
      }
    }

    function wireSourceButtonsWithMeta(root, items) {
      root.querySelectorAll('.source-btn').forEach(btn => {
        const idx = btn.closest('tr')?.dataset?.itemIndex;
        const meta = idx != null && items[idx] ? (items[idx].source_metadata || {}) : {};
        btn.onclick = () => toggleSource(btn, meta);
      });
    }

    function paramsFromForm() {
      const fd = new FormData(document.getElementById('filters'));
      const p = new URLSearchParams();
      for (const [k, v] of fd.entries()) {
        if (v !== '') p.set(k, v);
      }
      p.set('limit', limit);
      p.set('offset', offset);
      return p;
    }

    function viewMode() {
      return document.querySelector('[name=view]').value;
    }

    function queuedBadge() {
      return '<span class="badge queued">Queued for re-analysis</span>';
    }

    function queuedCommentDisplay(comment) {
      if (!comment) return '';
      return `<div class="queued-comment"><div class="queued-comment-label">Your comment</div>${esc(comment)}</div>`;
    }

    function commentField(rowId, sourceId, analyzedId, existingComment, isQueued, sourceAvailable) {
      const queuedNote = isQueued ? queuedCommentDisplay(existingComment) : '';
      if (!sourceAvailable) {
        return `<div class="comment-cell">
          ${queuedNote}
          <div class="comment-unavailable">Source transaction was removed by bank sync. Re-queue is not available.</div>
          <div class="status-msg" id="status-${rowId}"></div>
        </div>`;
      }
      const dataAttrs = [
        `data-row-id="${rowId}"`,
        sourceId ? `data-source-id="${sourceId}"` : '',
        analyzedId ? `data-analyzed-id="${analyzedId}"` : '',
      ].filter(Boolean).join(' ');
      const prefilled = existingComment ? esc(existingComment) : '';
      const saveLabel = isQueued ? 'Update' : 'Save';
      return `<div class="comment-cell">
        ${queuedNote}
        <div class="comment-row">
          <textarea placeholder="Guidance for re-analysis…" rows="2" ${dataAttrs}>${prefilled}</textarea>
          <button type="button" class="save-btn" ${dataAttrs}>${saveLabel}</button>
        </div>
        <div class="status-msg" id="status-${rowId}"></div>
      </div>`;
    }

    function fmtAmount(item, flow) {
      const n = item.amount_usd;
      if (n == null) return '—';
      const cls = flow ? 'amount-' + flow : 'amount-reduction';
      const sign = flow === 'addition' ? '+' : flow === 'reduction' ? '−' : '';
      return `<span class="${cls}">${sign}$${Math.abs(n).toFixed(2)}</span>`;
    }

    function statusCell(item) {
      if (item.pending_reanalysis) {
        return queuedBadge();
      }
      if (item.kind === 'needs_attention' || item.needs_attention) {
        return '<span class="badge attention">review</span>';
      }
      const sub = item.is_subscription ? '<span class="badge sub">sub</span> ' : '';
      if (item.category) {
        return `${sub}<span class="badge">${esc(item.category)}</span>`;
      }
      return '<span class="badge attention">review</span>';
    }

    async function saveComment(btn) {
      const textarea = btn.parentElement.querySelector('textarea');
      const comment = textarea.value.trim();
      const statusEl = document.getElementById('status-' + btn.dataset.rowId);
      if (!comment) {
        statusEl.textContent = 'Enter a comment first.';
        statusEl.className = 'status-msg err';
        return;
      }
      btn.disabled = true;
      statusEl.textContent = 'Saving…';
      statusEl.className = 'status-msg';
      const body = { comment };
      if (btn.dataset.sourceId) body.source_transaction_id = btn.dataset.sourceId;
      if (btn.dataset.analyzedId) body.analyzed_transaction_id = btn.dataset.analyzedId;
      try {
        const res = await fetch(api + '/transactions/requeue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail;
          const msg = Array.isArray(detail)
            ? detail.map(d => d.msg || String(d)).join('; ')
            : (detail || 'Save failed');
          throw new Error(msg);
        }
        statusEl.textContent = 'Queued for re-analysis.';
        statusEl.className = 'status-msg ok';
        setTimeout(load, 800);
      } catch (err) {
        statusEl.textContent = err.message;
        statusEl.className = 'status-msg err';
      } finally {
        btn.disabled = false;
      }
    }

    function renderTransactionTable(data) {
      const items = data.items || [];
      const wrap = document.getElementById('table-wrap');

      if (!items.length) {
        wrap.innerHTML = '<div class="empty">No transactions match your filters.</div>';
        return;
      }

      const rows = items.map((item, i) => {
        const meta = item.source_metadata || {};
        const merchant = meta.merchant_name || meta.name || '';
        const account = meta.account_display_name || '';
        const rowId = 'row-' + i;
        const isQueued = item.kind === 'pending_retry' || item.pending_reanalysis;
        const isNA = item.kind === 'needs_attention';
        const rowClass = [
          isNA ? 'needs-attention' : '',
          isQueued ? 'pending-retry' : '',
        ].filter(Boolean).join(' ');
        const attentionHtml = item.attention_reason
          ? `<div class="attention-reason">${esc(item.attention_reason)}</div>`
          : '';
        const flow = item.flow_direction || '—';
        const analyzedId = item.analyzed_transaction_id || null;

        return `<tr class="${rowClass}" data-item-index="${i}">
          <td>${item.transaction_date || '—'}</td>
          <td>${fmtAmount(item, item.flow_direction)}</td>
          <td>${statusCell(item)}</td>
          <td>${esc(item.description)}${attentionHtml}
            <div class="account">${esc(merchant)}${account ? ' · ' + esc(account) : ''}</div></td>
          <td>${esc(flow)}</td>
          <td>${item.confidence != null ? (item.confidence * 100).toFixed(0) + '%' : '—'}</td>
          <td>${sourceToggleButton(rowId, item.source_transaction_id)}</td>
          <td>${commentField(rowId, item.source_transaction_id, analyzedId, item.user_comment, isQueued, item.source_available !== false)}</td>
        </tr>${sourceDetailRow(rowId, 8)}`;
      }).join('');

      wrap.innerHTML = `
        <table>
          <thead><tr>
            <th>Date</th><th>Amount</th><th>Status</th><th>Description</th><th>Flow</th><th>Conf.</th><th>Source</th><th>Re-analysis comment</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>`;

      wrap.querySelectorAll('.save-btn').forEach(btn => {
        btn.onclick = () => saveComment(btn);
      });
      wireSourceButtonsWithMeta(wrap, items);
    }

    function renderTable(data) {
      total = data.total;
      const mode = viewMode();
      const naCount = data.needs_attention_total || 0;
      const prCount = data.pending_retry_total || 0;
      const azCount = data.analyzed_total || 0;

      let summary = '';
      if (mode === 'needs_attention') {
        summary = `${data.total} need${data.total === 1 ? 's' : ''} attention`;
      } else if (mode === 'pending_retry') {
        summary = `${data.total} queued for re-analysis`;
      } else if (mode === 'analyzed') {
        summary = `${data.total} analyzed transaction${data.total === 1 ? '' : 's'}`;
      } else {
        summary = `${data.total} transaction${data.total === 1 ? '' : 's'} (${azCount} analyzed, ${naCount} need attention, ${prCount} queued)`;
      }
      summary += ` · sorted by ${data.sort_by} (${data.sort_order})`;
      document.getElementById('summary').textContent = summary;

      const visibleCount = data.items.length;
      const start = data.total ? data.offset + 1 : 0;
      const end = Math.min(data.offset + visibleCount, data.total);
      document.getElementById('page-info').textContent = `${start}–${end} of ${data.total}`;
      document.getElementById('prev').disabled = offset <= 0;
      document.getElementById('next').disabled = offset + limit >= total;

      renderTransactionTable(data);
    }

    async function loadFilters() {
      const res = await fetch(api + '/filters');
      const data = await res.json();
      const cat = document.querySelector('[name=category]');
      data.categories.forEach(c => {
        const o = document.createElement('option');
        o.value = c; o.textContent = c;
        cat.appendChild(o);
      });
      const flow = document.querySelector('[name=flow_direction]');
      data.flow_directions.forEach(f => {
        const o = document.createElement('option');
        o.value = f; o.textContent = f;
        flow.appendChild(o);
      });
    }

    async function load() {
      const res = await fetch(api + '/transactions?' + paramsFromForm());
      const data = await res.json();
      renderTable(data);
    }

    document.getElementById('filters').addEventListener('submit', e => {
      e.preventDefault();
      offset = 0;
      load();
    });
    document.getElementById('prev').onclick = () => { offset = Math.max(0, offset - limit); load(); };
    document.getElementById('next').onclick = () => { offset += limit; load(); };

    loadFilters().then(load);
  </script>
</body>
</html>"""
