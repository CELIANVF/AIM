/**
 * Client-side table sort: click header cells to sort tbody rows.
 * Use class "table-sortable" on <table>. Mark non-sortable headers with data-sort="disable".
 * Optional: data-sort="number" | data-sort="date" (DD/MM/YYYY[ HH:MM]).
 */
(function () {
  'use strict';

  function logicalThIndex(tr, th) {
    var pos = 0;
    for (var i = 0; i < tr.cells.length; i++) {
      var cell = tr.cells[i];
      if (cell === th) return pos;
      pos += cell.colSpan || 1;
    }
    return -1;
  }

  function getCellAtLogicalColumn(row, logicalIndex) {
    var pos = 0;
    for (var i = 0; i < row.cells.length; i++) {
      var cell = row.cells[i];
      var span = cell.colSpan || 1;
      if (logicalIndex >= pos && logicalIndex < pos + span) return cell;
      pos += span;
    }
    return null;
  }

  function parseEuroDateTime(text) {
    var m = String(text || '').trim().match(/(\d{2})\/(\d{2})\/(\d{4})(?:\s+(\d{2}):(\d{2}))?/);
    if (!m) return NaN;
    return new Date(
      parseInt(m[3], 10),
      parseInt(m[2], 10) - 1,
      parseInt(m[1], 10),
      m[4] ? parseInt(m[4], 10) : 0,
      m[5] ? parseInt(m[5], 10) : 0
    ).getTime();
  }

  /** ISO YYYY-MM-DD (optionally followed by more text) or European DD/MM/YYYY[ HH:MM] */
  function parseFlexibleDate(text) {
    var t = String(text || '').trim();
    var iso = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (iso) {
      return new Date(parseInt(iso[1], 10), parseInt(iso[2], 10) - 1, parseInt(iso[3], 10)).getTime();
    }
    return parseEuroDateTime(t);
  }

  function cellSortKey(cell, mode) {
    if (!cell) return '';
    var t = cell.textContent.replace(/\s+/g, ' ').trim();
    if (mode === 'number') {
      var n = parseFloat(String(t).replace(/\s/g, '').replace(',', '.'));
      return isNaN(n) ? t.toLowerCase() : n;
    }
    if (mode === 'date') {
      var ts = parseFlexibleDate(t);
      return isNaN(ts) ? t.toLowerCase() : ts;
    }
    return t.toLowerCase();
  }

  function inferMode(th) {
    var ds = (th.getAttribute('data-sort') || '').toLowerCase();
    if (ds === 'disable') return 'disable';
    if (ds === 'number' || ds === 'date') return ds;
    var label = (th.textContent || '').trim().toLowerCase();
    if (label === 'id') return 'number';
    return 'text';
  }

  function clearSortClasses(thead) {
    var ths = thead.querySelectorAll('th');
    for (var i = 0; i < ths.length; i++) {
      ths[i].classList.remove('th-sort-asc', 'th-sort-desc');
      ths[i].removeAttribute('aria-sort');
    }
  }

  function sortTable(table, th, logicalCol) {
    var thead = table.tHead;
    var tbody = table.tBodies[0];
    if (!thead || !tbody) return;

    if (th.getAttribute('data-sort') === 'disable') return;
    var mode = inferMode(th);
    if (mode === 'disable') return;

    var headerRow = th.parentNode;
    var prevCol = table.getAttribute('data-sort-col');
    var prevDir = table.getAttribute('data-sort-dir') || 'asc';
    var dir = 1;
    if (String(prevCol) === String(logicalCol) && prevDir === 'asc') dir = -1;

    var rows = Array.prototype.slice.call(tbody.rows, 0);
    if (rows.length < 2) {
      clearSortClasses(thead);
      th.classList.add(dir === 1 ? 'th-sort-asc' : 'th-sort-desc');
      th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
      table.setAttribute('data-sort-col', String(logicalCol));
      table.setAttribute('data-sort-dir', dir === 1 ? 'asc' : 'desc');
      return;
    }

    rows.sort(function (a, b) {
      var ca = getCellAtLogicalColumn(a, logicalCol);
      var cb = getCellAtLogicalColumn(b, logicalCol);
      var va = cellSortKey(ca, mode);
      var vb = cellSortKey(cb, mode);
      if (va < vb) return -dir;
      if (va > vb) return dir;
      return 0;
    });

    for (var r = 0; r < rows.length; r++) {
      tbody.appendChild(rows[r]);
    }

    clearSortClasses(thead);
    th.classList.add(dir === 1 ? 'th-sort-asc' : 'th-sort-desc');
    th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
    table.setAttribute('data-sort-col', String(logicalCol));
    table.setAttribute('data-sort-dir', dir === 1 ? 'asc' : 'desc');
  }

  function onHeaderActivate(table, th) {
    if (th.getAttribute('data-sort') === 'disable') return;
    var tr = th.parentNode;
    var logicalCol = logicalThIndex(tr, th);
    if (logicalCol < 0) return;
    sortTable(table, th, logicalCol);
  }

  function initTable(table) {
    var thead = table.tHead;
    if (!thead || !thead.rows.length) return;
    var headerRow = thead.rows[0];
    thead.addEventListener('click', function (e) {
      var th = e.target.closest('th');
      if (!th || th.getAttribute('data-sort') === 'disable') return;
      if (!headerRow.contains(th)) return;
      onHeaderActivate(table, th);
    });
    thead.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var th = e.target.closest('th');
      if (!th || th.getAttribute('data-sort') === 'disable') return;
      if (!headerRow.contains(th)) return;
      e.preventDefault();
      onHeaderActivate(table, th);
    });

    for (var i = 0; i < headerRow.cells.length; i++) {
      var th = headerRow.cells[i];
      if (th.getAttribute('data-sort') === 'disable') continue;
      th.setAttribute('tabindex', '0');
      var t = (th.getAttribute('title') || '').trim();
      if (t.indexOf('Trier') === -1) {
        th.setAttribute('title', (t ? t + ' · ' : '') + 'Cliquer pour trier');
      }
    }
  }

  function run() {
    document.querySelectorAll('table.table-sortable').forEach(initTable);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
