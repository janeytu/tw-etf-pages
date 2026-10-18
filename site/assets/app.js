(function () {
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  var tocToggle = qs('[data-toc-toggle]');
  var toc = qs('#toc');
  if (tocToggle && toc) {
    tocToggle.addEventListener('click', function () {
      toc.classList.toggle('open');
    });
  }

  qsa('[data-filter-group]').forEach(function (group) {
    var targetId = group.getAttribute('data-filter-group');
    var table = qs('[data-etf-table="' + targetId + '"]');
    if (!table) return;
    group.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-filter]');
      if (!btn) return;
      qsa('[data-filter]', group).forEach(function (b) {
        b.classList.toggle('active', b === btn);
      });
      var mode = btn.getAttribute('data-filter');
      qsa('tr.unchanged', table).forEach(function (row) {
        row.classList.toggle('hidden', mode === 'changed');
      });
    });
  });

  var links = qsa('#toc a[href^="#"]');
  var sections = links
    .map(function (a) { return qs(a.getAttribute('href')); })
    .filter(Boolean);

  function setActive() {
    var y = window.scrollY + 100;
    var current = sections[0];
    sections.forEach(function (sec) {
      if (sec.offsetTop <= y) current = sec;
    });
    links.forEach(function (a) {
      a.classList.toggle('active', current && a.getAttribute('href') === '#' + current.id);
    });
  }

  if (sections.length) {
    window.addEventListener('scroll', setActive, { passive: true });
    setActive();
  }

  /* ---- 異動資料日切換 ---- */
  function formatLots(shares) {
    if (shares == null) return '—';
    var lots = Number(shares) / 1000;
    if (Math.abs(lots - Math.round(lots)) < 1e-9) {
      return Math.round(lots).toLocaleString('zh-TW') + ' 張';
    }
    var s = lots.toLocaleString('zh-TW', { maximumFractionDigits: 3 });
    return s + ' 張';
  }

  function formatWeight(v) {
    if (v == null || v === '') return null;
    return Number(v).toFixed(2);
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function rowHtml(r) {
    var changed = !!r.changed;
    var cls = changed ? 'changed' : 'unchanged hidden';
    var w = formatWeight(r.curr_weight_pct);
    var weightCell = '—';
    if (w != null) {
      weightCell = '<strong>' + w + '</strong>';
      var wd = r.weight_delta;
      if (changed && wd != null && Number(wd) !== 0) {
        var up = Number(wd) > 0;
        var sign = up ? '+' : '';
        weightCell += '<br /><span class="' + (up ? 'delta-up' : 'delta-down') + '">'
          + (up ? '🔺' : '🟢') + sign + Number(wd).toFixed(2) + '</span>';
      }
    }
    var status = r.status || {};
    return '<tr class="' + cls + '">'
      + '<td>' + escapeHtml(r.stock_code) + '</td>'
      + '<td>' + escapeHtml(r.stock_name) + '</td>'
      + '<td class="num">' + formatLots(r.curr_shares) + '</td>'
      + '<td class="num">' + weightCell + '</td>'
      + '<td><span class="' + escapeHtml(status.css || '') + '">'
      + escapeHtml(status.label || '') + '</span></td>'
      + '</tr>';
  }

  function applyChangeDay(root, entry) {
    if (!entry) return;
    var asOf = qs('[data-as-of]', root) || qs('[data-as-of]');
    var prev = qs('[data-prev-as-of]', root) || qs('[data-prev-as-of]');
    var prevWrap = qs('[data-prev-wrap]', root) || qs('[data-prev-wrap]');
    var source = qs('[data-source]', root) || qs('[data-source]');
    // Header subtitle may live outside root — update page-level meta too
    qsa('[data-as-of]').forEach(function (el) { el.textContent = entry.as_of_date || '—'; });
    if (entry.prev_as_of_date) {
      qsa('[data-prev-wrap]').forEach(function (el) {
        el.innerHTML = '／對比 <strong data-prev-as-of>' + escapeHtml(entry.prev_as_of_date) + '</strong>';
        el.classList.remove('hidden');
      });
    } else {
      qsa('[data-prev-wrap]').forEach(function (el) {
        el.innerHTML = '';
      });
    }
    if (source || qs('[data-source]')) {
      qsa('[data-source]').forEach(function (el) {
        el.textContent = entry.source || '—';
      });
    }

    var summary = entry.summary || {};
    qsa('[data-chip]', root).forEach(function (el) {
      var key = el.getAttribute('data-chip');
      el.textContent = String(summary[key] != null ? summary[key] : 0);
    });

    var countEl = qs('[data-changed-count]', root);
    if (countEl) countEl.textContent = String(entry.changed_count || 0);

    var tbody = qs('[data-change-tbody]', root);
    if (tbody) {
      tbody.innerHTML = (entry.rows || []).map(rowHtml).join('');
    }

    var noCh = qs('[data-no-changes]', root);
    if (noCh) {
      noCh.classList.toggle('hidden', (entry.changed_count || 0) !== 0);
    }

    // Reset filter to "changed"
    var group = qs('[data-filter-group]', root);
    if (group) {
      qsa('[data-filter]', group).forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-filter') === 'changed');
      });
      var table = qs('[data-etf-table]', root);
      if (table) {
        qsa('tr.unchanged', table).forEach(function (row) {
          row.classList.add('hidden');
        });
      }
    }
  }

  function initDateSwitcher() {
    qsa('[data-change-history-root]').forEach(function (root) {
      var dataEl = qs('[data-change-history-json]', root);
      var select = qs('[data-date-select]', root);
      if (!dataEl || !select) return;
      var history;
      try {
        history = JSON.parse(dataEl.textContent);
      } catch (err) {
        console.error('change history JSON parse failed', err);
        return;
      }
      if (!history || !history.length) return;
      var byDate = {};
      history.forEach(function (h) { byDate[h.as_of_date] = h; });

      function show(dateStr) {
        var entry = byDate[dateStr];
        if (!entry) return;
        applyChangeDay(root, entry);
        try {
          var url = new URL(window.location.href);
          url.searchParams.set('date', dateStr);
          window.history.replaceState({}, '', url.pathname + url.search + url.hash);
        } catch (e) { /* ignore */ }
      }

      select.addEventListener('change', function () {
        show(select.value);
      });

      var want = null;
      try {
        want = new URLSearchParams(window.location.search).get('date');
      } catch (e) { want = null; }
      if (want && byDate[want]) {
        select.value = want;
      }
      show(select.value);
    });

    // Index: navigate to ETF detail with ?date=
    qsa('[data-index-date-nav]').forEach(function (sel) {
      sel.addEventListener('change', function () {
        var ticker = sel.getAttribute('data-index-date-nav');
        var d = sel.value;
        if (ticker && d) {
          window.location.href = ticker + '.html?date=' + encodeURIComponent(d);
        }
      });
    });
  }

  /* ---- 近20天持股趨勢 (Chart.js) ---- */
  function sharesToLots(v) {
    if (v == null) return null;
    return Math.round((Number(v) / 1000) * 1000) / 1000;
  }

  function formatLotsLabel(v) {
    if (v == null || Number.isNaN(v)) return '—';
    var abs = Math.abs(v);
    if (Math.abs(abs - Math.round(abs)) < 1e-9) {
      return (v > 0 && String(v).indexOf('+') !== 0 ? '' : '') + Math.round(v).toLocaleString('zh-TW') + ' 張';
    }
    return v.toLocaleString('zh-TW', { maximumFractionDigits: 3 }) + ' 張';
  }

  var PALETTE = [
    '#e84967', '#2563eb', '#0d9488', '#d97706', '#7c3aed',
    '#db2777', '#0891b2', '#65a30d', '#ea580c', '#4f46e5'
  ];

  function initTrend() {
    var dataEl = qs('#trend-data');
    var canvas = qs('#trend-chart');
    var select = qs('#trend-stock-select');
    if (!dataEl || !canvas || !select) return;
    if (typeof Chart === 'undefined') {
      console.warn('Chart.js 未載入，跳過趨勢圖');
      return;
    }

    var trend;
    try {
      trend = JSON.parse(dataEl.textContent);
    } catch (err) {
      console.error('trend JSON parse failed', err);
      return;
    }

    var byCode = {};
    (trend.stocks || []).forEach(function (s) {
      byCode[s.stock_code] = s;
    });

    // Populate select: intermittent first, then by activity
    var ordered = (trend.stocks || []).slice().sort(function (a, b) {
      if (b.intermittent_buy_score !== a.intermittent_buy_score) {
        return b.intermittent_buy_score - a.intermittent_buy_score;
      }
      if (b.buy_days !== a.buy_days) return b.buy_days - a.buy_days;
      return (b.activity || 0) - (a.activity || 0);
    });

    ordered.forEach(function (s) {
      var opt = document.createElement('option');
      opt.value = s.stock_code;
      var tag = s.intermittent_label ? ' · ' + s.intermittent_label : '';
      opt.textContent = s.stock_code + ' ' + s.stock_name + tag;
      select.appendChild(opt);
    });

    var chart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: trend.dates || [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom' },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var v = ctx.parsed.y;
                return ctx.dataset.label + '：' + formatLotsLabel(v);
              }
            }
          }
        },
        scales: {
          x: {
            title: { display: true, text: '資料日' },
            ticks: { maxRotation: 45, minRotation: 0 }
          },
          y: {
            title: { display: true, text: '持股（張）' },
            ticks: {
              callback: function (v) {
                return Number(v).toLocaleString('zh-TW');
              }
            }
          }
        }
      }
    });

    function selectedCodes() {
      return Array.from(select.selectedOptions).map(function (o) { return o.value; });
    }

    function setSelected(codes) {
      var set = {};
      (codes || []).forEach(function (c) { set[c] = true; });
      Array.from(select.options).forEach(function (o) {
        o.selected = !!set[o.value];
      });
      refreshChart();
    }

    function refreshChart() {
      var codes = selectedCodes();
      var countEl = qs('[data-trend-selected-count]');
      if (countEl) countEl.textContent = String(codes.length);

      chart.data.datasets = codes.map(function (code, i) {
        var s = byCode[code];
        var label = s ? (s.stock_code + ' ' + s.stock_name) : code;
        var color = PALETTE[i % PALETTE.length];
        return {
          label: label,
          data: (s ? s.shares : []).map(sharesToLots),
          borderColor: color,
          backgroundColor: color,
          tension: 0.25,
          spanGaps: true,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2
        };
      });
      chart.update();

      qsa('.trend-pick-row').forEach(function (row) {
        var c = row.getAttribute('data-pick-code');
        row.classList.toggle('is-selected', codes.indexOf(c) !== -1);
      });
    }

    select.addEventListener('change', refreshChart);

    qsa('[data-trend-preset]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var preset = btn.getAttribute('data-trend-preset');
        if (preset === 'clear') {
          setSelected([]);
          return;
        }
        if (preset === 'default') {
          setSelected(trend.default_codes || []);
          return;
        }
        if (preset === 'intermittent') {
          var codes = (trend.top_intermittent || []).map(function (t) {
            return t.stock_code;
          }).slice(0, 5);
          if (!codes.length) codes = trend.default_codes || [];
          setSelected(codes);
        }
      });
    });

    qsa('.trend-pick-row').forEach(function (row) {
      function toggle() {
        var code = row.getAttribute('data-pick-code');
        var cur = selectedCodes();
        var idx = cur.indexOf(code);
        if (idx === -1) cur.push(code);
        else cur.splice(idx, 1);
        setSelected(cur);
      }
      row.addEventListener('click', toggle);
      row.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault();
          toggle();
        }
      });
    });

    setSelected(trend.default_codes || []);
  }

  function whenChartReady(fn, tries) {
    tries = tries == null ? 40 : tries;
    if (typeof Chart !== 'undefined') {
      fn();
      return;
    }
    if (tries <= 0) {
      console.warn('Chart.js 未載入，跳過趨勢圖');
      return;
    }
    setTimeout(function () { whenChartReady(fn, tries - 1); }, 50);
  }

  function boot() {
    initDateSwitcher();
    whenChartReady(initTrend);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

/* ---- 加權指數 KD 走勢圖 ---- */
(function () {
  function drawKd(tries) {
    var canvas = document.getElementById('kd-chart');
    var dataEl = document.getElementById('kd-chart-data');
    if (!canvas || !dataEl) return;
    if (typeof Chart === 'undefined') {
      if ((tries || 0) < 40) setTimeout(function () { drawKd((tries || 0) + 1); }, 150);
      return;
    }
    var rows = JSON.parse(dataEl.textContent || '[]');
    var band = {
      id: 'kdBand',
      beforeDraw: function (c) {
        var y = c.scales.y, a = c.chartArea, ctx = c.ctx;
        if (!y || !a) return;
        ctx.save();
        ctx.fillStyle = 'rgba(239,68,68,0.10)';
        ctx.fillRect(a.left, y.getPixelForValue(100), a.right - a.left, y.getPixelForValue(80) - y.getPixelForValue(100));
        ctx.fillStyle = 'rgba(34,197,94,0.12)';
        ctx.fillRect(a.left, y.getPixelForValue(20), a.right - a.left, y.getPixelForValue(0) - y.getPixelForValue(20));
        ctx.restore();
      }
    };
    new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: rows.map(function (r) { return r.date.slice(5); }),
        datasets: [
          { label: 'K', data: rows.map(function (r) { return r.k; }), borderColor: '#2563eb', backgroundColor: '#2563eb', pointRadius: 1.5, tension: 0.2, yAxisID: 'y' },
          { label: 'D', data: rows.map(function (r) { return r.d; }), borderColor: '#f59e0b', backgroundColor: '#f59e0b', pointRadius: 1.5, tension: 0.2, yAxisID: 'y' },
          { label: '收盤', data: rows.map(function (r) { return r.close; }), borderColor: 'rgba(100,116,139,0.6)', backgroundColor: 'rgba(100,116,139,0.6)', borderDash: [4, 3], pointRadius: 0, tension: 0.2, yAxisID: 'y2' }
        ]
      },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        scales: {
          y: { min: 0, max: 100, ticks: { stepSize: 20 }, title: { display: true, text: 'K / D' } },
          y2: { position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: '加權指數' } }
        }
      },
      plugins: [band]
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { drawKd(0); });
  else drawKd(0);
})();
