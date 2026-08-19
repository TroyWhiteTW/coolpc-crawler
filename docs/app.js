// ── 狀態 State ──
let dataA = [];
let dataB = [];
let showAll = true;
let compareResults = [];
let historyEntries = [];

// 檔名→模式對照表 Filename to mode lookup
const modeMap = new Map();

// 按年月索引的資料結構 Indexed by year → month → entries
// { "2026": { "04": [{file, mode, day, time}, ...], ... }, ... }
let indexedData = {};

// ── DOM 元素 Elements ──
const btnCompare = document.getElementById('btnCompare');
const loadingOverlay = document.getElementById('loadingOverlay');
const mainContent = document.getElementById('mainContent');
const groupsSection = document.getElementById('groupsSection');
const toggleAll = document.getElementById('toggleAll');
const headerMeta = document.getElementById('headerMeta');
const modeNotice = document.getElementById('modeNotice');
const toggleExpand = document.getElementById('toggleExpand');

// 分級選單元素 Cascading select elements
const selectors = {
  A: {
    year: document.getElementById('selectA_year'),
    month: document.getElementById('selectA_month'),
    entry: document.getElementById('selectA_entry'),
  },
  B: {
    year: document.getElementById('selectB_year'),
    month: document.getElementById('selectB_month'),
    entry: document.getElementById('selectB_entry'),
  },
};

// ── 工具函式 Utilities ──

// 解析檔名 Parse filename into components
function parseFilename(filename) {
  const m = filename.match(/coolpc_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
  if (!m) return null;
  return {
    year: m[1],
    month: m[2],
    day: m[3],
    hour: m[4],
    min: m[5],
    sec: m[6],
  };
}

// 格式化為日期時間顯示 Format entry for display in the entry dropdown
function formatEntryLabel(parsed, mode) {
  return parsed.day + '日 ' + parsed.hour + ':' + parsed.min + ' [' + mode + ']';
}

// 格式化價格 Format price with comma separator
function formatPrice(price) {
  if (price == null || price === '') return '—';
  return '$' + Number(price).toLocaleString();
}

// 格式化價差 Format price difference with sign
function formatDiff(diff) {
  if (diff === 0) return '0';
  const sign = diff > 0 ? '+' : '';
  return sign + '$' + diff.toLocaleString();
}

// 格式化漲跌幅百分比 Format percentage change
function formatPct(pct) {
  if (pct == null) return '—';
  if (pct === 0) return '0%';
  const sign = pct > 0 ? '+' : '';
  return sign + pct.toFixed(1) + '%';
}

// ── CSV 載入 Load CSV via PapaParse ──
// 已下載 CSV 快取，避免重複切換 A/B 時重抓
// CSV cache to avoid re-downloading when switching A/B selections
const csvCache = new Map();

function loadCSV(filename) {
  if (csvCache.has(filename)) {
    return Promise.resolve(csvCache.get(filename));
  }
  return new Promise((resolve, reject) => {
    const url = '../output/' + filename;
    Papa.parse(url, {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        csvCache.set(filename, results.data);
        resolve(results.data);
      },
      error: (err) => reject(err),
    });
  });
}

// ── 建立索引 Build year/month index from history entries ──
function buildIndex() {
  indexedData = {};
  modeMap.clear();
  historyEntries.forEach((entry) => {
    const p = parseFilename(entry.file);
    if (!p) return;
    modeMap.set(entry.file, entry.mode);
    if (!indexedData[p.year]) indexedData[p.year] = {};
    if (!indexedData[p.year][p.month]) indexedData[p.year][p.month] = [];
    indexedData[p.year][p.month].push({
      file: entry.file,
      mode: entry.mode,
      ...p,
    });
  });
}

// ── 填入年份選單 Populate year dropdown ──
function populateYears(side) {
  const sel = selectors[side].year;
  sel.innerHTML = '';
  // 年份降序 Years descending
  const years = Object.keys(indexedData).sort().reverse();
  years.forEach((y) => sel.add(new Option(y + ' 年', y)));
}

// ── 填入月份選單 Populate month dropdown ──
function populateMonths(side) {
  const sel = selectors[side].month;
  const year = selectors[side].year.value;
  sel.innerHTML = '';
  if (!indexedData[year]) return;
  const months = Object.keys(indexedData[year]).sort().reverse();
  months.forEach((m) => sel.add(new Option(m + ' 月', m)));
}

// ── 填入具體時間選單 Populate entry dropdown ──
function populateEntries(side) {
  const sel = selectors[side].entry;
  const year = selectors[side].year.value;
  const month = selectors[side].month.value;
  sel.innerHTML = '';
  if (!indexedData[year] || !indexedData[year][month]) return;
  // 已按檔名降序排列（最新在前）Entries already sorted desc (newest first)
  indexedData[year][month].forEach((e) => {
    sel.add(new Option(formatEntryLabel(e, e.mode), e.file));
  });
}

// ── 初始化某側的選單 Initialize one side's cascading selects ──
function initSide(side) {
  populateYears(side);
  populateMonths(side);
  populateEntries(side);
}

// ── 串聯事件：年份變動 → 更新月份 → 更新項目 Year change → update months → entries ──
function bindCascade(side) {
  selectors[side].year.addEventListener('change', () => {
    populateMonths(side);
    populateEntries(side);
  });
  selectors[side].month.addEventListener('change', () => {
    populateEntries(side);
  });
}

// ── 取得選定檔名 Get selected filename for a side ──
function getSelectedFile(side) {
  return selectors[side].entry.value;
}

function getMode(filename) {
  return modeMap.get(filename) || 'MAIN';
}

// ── 初始化 Initialize ──
async function init() {
  try {
    const resp = await fetch('crawl_history.json');
    historyEntries = await resp.json();

    if (historyEntries.length === 0) {
      headerMeta.textContent = '尚無資料';
      return;
    }

    buildIndex();

    // 初始化 B 側（右）：預設最新 Initialize B (right): default to newest
    initSide('B');

    // 初始化 A 側（左）：預設第六筆 Initialize A (left): default to 6th entry
    initSide('A');
    if (selectors.A.entry.options.length > 5) {
      selectors.A.entry.selectedIndex = 5;
    } else {
      selectors.A.entry.selectedIndex = selectors.A.entry.options.length - 1;
    }

    bindCascade('A');
    bindCascade('B');

    headerMeta.textContent = '共 ' + historyEntries.length + ' 筆歷史紀錄';

    await runComparison();
  } catch (err) {
    console.error('Failed to load crawl history:', err);
    headerMeta.textContent = '載入失敗';
  }
}

// ── 執行比較 Run comparison ──
async function runComparison() {
  const fileA = getSelectedFile('A');
  const fileB = getSelectedFile('B');
  if (!fileA || !fileB) return;

  mainContent.style.display = 'none';
  loadingOverlay.classList.add('active');

  try {
    [dataA, dataB] = await Promise.all([loadCSV(fileA), loadCSV(fileB)]);
    buildComparison(fileA, fileB);
  } catch (err) {
    console.error('Failed to load CSV:', err);
    alert('載入 CSV 失敗，請確認檔案是否存在。');
  } finally {
    loadingOverlay.classList.remove('active');
  }
}

// ── 建立比較資料 Build comparison data ──
function buildComparison(fileA, fileB) {
  const mapA = new Map();
  const mapB = new Map();
  const catsA = new Set();
  const catsB = new Set();

  dataA.forEach((row) => {
    if (row.name && row.price) {
      mapA.set(row.name, row);
      catsA.add(row.category);
    }
  });
  dataB.forEach((row) => {
    if (row.name && row.price) {
      mapB.set(row.name, row);
      catsB.add(row.category);
    }
  });

  // 取分類交集，避免 MAIN/ALL 模式差異導致誤判
  // Intersect categories to avoid MAIN/ALL mode mismatch
  const sharedCats = new Set([...catsA].filter((c) => catsB.has(c)));
  const modeA = getMode(fileA);
  const modeB = getMode(fileB);
  const excludedCats = new Set([
    ...[...catsA].filter((c) => !sharedCats.has(c)),
    ...[...catsB].filter((c) => !sharedCats.has(c)),
  ]);

  if (excludedCats.size > 0) {
    modeNotice.style.display = 'block';
    modeNotice.innerHTML =
      '<div class="mode-notice-inner">⚠ 舊(A) 為 ' + escapeHtml(modeA) + ' 模式，新(B) 為 ' + escapeHtml(modeB) +
      ' 模式，已自動排除非共同分類（' + [...excludedCats].map(escapeHtml).join('、') +
      '），僅比較共同存在的 ' + sharedCats.size + ' 個分類。</div>';
  } else {
    modeNotice.style.display = 'none';
  }

  const allNames = new Set();
  mapA.forEach((row, name) => { if (sharedCats.has(row.category)) allNames.add(name); });
  mapB.forEach((row, name) => { if (sharedCats.has(row.category)) allNames.add(name); });

  compareResults = [];
  allNames.forEach((name) => {
    const a = mapA.get(name);
    const b = mapB.get(name);

    if (a && !sharedCats.has(a.category)) return;
    if (b && !sharedCats.has(b.category)) return;

    const priceA = a ? Number(a.price) : null;
    const priceB = b ? Number(b.price) : null;
    const category = (a || b).category || '';

    let diff = null;
    let status = 'same';

    if (priceA != null && priceB != null) {
      // 價差 = 新(B) - 舊(A)，正數表示漲價 Diff = new(B) - old(A), positive = price up
      diff = priceB - priceA;
      if (diff > 0) status = 'up';
      else if (diff < 0) status = 'down';
    } else if (priceA == null && priceB != null) {
      // 舊沒有、新有 = 新增商品 Only in new(B) = newly added
      status = 'new';
    } else if (priceA != null && priceB == null) {
      // 舊有、新沒有 = 下架商品 Only in old(A) = removed
      status = 'removed';
    }

    const remarkA = a ? (a.remark || '') : '';
    const remarkB = b ? (b.remark || '') : '';
    const remark = remarkB || remarkA;
    // 漲跌幅百分比 Percentage change based on old price
    let pct = null;
    if (diff != null && priceA != null && priceA !== 0) {
      pct = (diff / priceA) * 100;
    }

    compareResults.push({ name, category, priceA, priceB, diff, pct, remark, status });
  });

  updateStats();
  renderGroups();
  mainContent.style.display = 'block';
}

// ── 統計 Stats ──
function updateStats() {
  const r = compareResults;
  document.getElementById('statTotal').textContent = r.length;
  document.getElementById('statChanged').textContent = r.filter((x) => x.status !== 'same').length;
  document.getElementById('statUp').textContent = r.filter((x) => x.status === 'up').length;
  document.getElementById('statDown').textContent = r.filter((x) => x.status === 'down').length;
  document.getElementById('statNew').textContent = r.filter((x) => x.status === 'new').length;
  document.getElementById('statRemoved').textContent = r.filter((x) => x.status === 'removed').length;
}

// ── 記錄各分類的摺疊狀態 Track collapsed state per category ──
const collapsedState = new Map();

// ── 渲染分組 Render category groups ──
function renderGroups() {
  // 儲存當前摺疊狀態 Save current collapsed state before re-render
  groupsSection.querySelectorAll('.category-group').forEach((g) => {
    const name = g.dataset.category;
    if (name) collapsedState.set(name, g.classList.contains('collapsed'));
  });

  groupsSection.innerHTML = '';

  const grouped = new Map();
  compareResults.forEach((r) => {
    if (!grouped.has(r.category)) grouped.set(r.category, []);
    grouped.get(r.category).push(r);
  });

  grouped.forEach((items) => {
    const order = { up: 0, down: 1, new: 2, removed: 3, same: 4 };
    items.sort((a, b) => {
      if (order[a.status] !== order[b.status]) return order[a.status] - order[b.status];
      return a.name.localeCompare(b.name);
    });
  });

  grouped.forEach((items, category) => {
    const changedCount = items.filter((r) => r.status !== 'same').length;
    const filteredItems = showAll ? items : items.filter((r) => r.status !== 'same');

    const group = document.createElement('div');
    group.className = 'category-group';
    group.dataset.category = category;
    const isCollapsed = collapsedState.has(category) ? collapsedState.get(category) : true;
    if (isCollapsed) group.classList.add('collapsed');

    const header = document.createElement('div');
    header.className = 'category-header';
    header.innerHTML =
      '<div class="category-header-left">' +
        '<span class="category-arrow">▼</span>' +
        '<span class="category-name">' + escapeHtml(category) + '</span>' +
      '</div>' +
      '<div class="category-badges">' +
        (changedCount > 0
          ? '<span class="category-count has-changes">' + changedCount + ' 異動</span>'
          : '') +
        '<span class="category-count">' + items.length + ' 項</span>' +
      '</div>';

    header.addEventListener('click', () => {
      group.classList.toggle('collapsed');
    });

    const body = document.createElement('div');
    body.className = 'category-body';

    if (filteredItems.length > 0) {
      const tableWrap = document.createElement('div');
      tableWrap.className = 'table-scroll';

      const table = document.createElement('table');
      table.className = 'compare-table';
      table.innerHTML =
        '<thead><tr>' +
          '<th class="th-name">商品名稱</th>' +
          '<th class="th-remark">備註</th>' +
          '<th class="th-price">舊 (A)</th>' +
          '<th class="th-price">新 (B)</th>' +
          '<th class="th-diff">價差</th>' +
          '<th class="th-pct">%</th>' +
          '<th class="th-status">狀態</th>' +
        '</tr></thead>';

      const tbody = document.createElement('tbody');
      filteredItems.forEach((r) => {
        const tr = document.createElement('tr');
        if (r.status === 'new') tr.className = 'row-new';
        else if (r.status === 'removed') tr.className = 'row-removed';

        tr.innerHTML =
          '<td class="td-name">' + escapeHtml(r.name) + '</td>' +
          '<td class="td-remark">' + escapeHtml(r.remark) + '</td>' +
          '<td class="td-price' + (r.priceA == null ? ' empty' : '') + '">' + formatPrice(r.priceA) + '</td>' +
          '<td class="td-price' + (r.priceB == null ? ' empty' : '') + '">' + formatPrice(r.priceB) + '</td>' +
          '<td class="td-diff ' + (r.diff > 0 ? 'up' : r.diff < 0 ? 'down' : 'same') + '">' +
            (r.diff != null ? formatDiff(r.diff) : '—') + '</td>' +
          '<td class="td-pct ' + (r.diff > 0 ? 'up' : r.diff < 0 ? 'down' : 'same') + '">' +
            formatPct(r.pct) + '</td>' +
          '<td class="td-status">' + statusBadge(r.status) + '</td>';

        tbody.appendChild(tr);
      });

      table.appendChild(tbody);
      tableWrap.appendChild(table);
      body.appendChild(tableWrap);
    } else {
      body.innerHTML = '<div class="group-empty">無異動商品</div>';
    }

    group.append(header, body);
    groupsSection.appendChild(group);
  });
}

function statusBadge(status) {
  const labels = {
    up: '▲ 漲價',
    down: '▼ 降價',
    same: '— 持平',
    new: '✦ 新增',
    removed: '✕ 下架',
  };
  return '<span class="badge badge-' + status + '">' + labels[status] + '</span>';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── 全部展開/收合 Expand/Collapse all ──
function setAllGroups(collapsed) {
  groupsSection.querySelectorAll('.category-group').forEach((g) => {
    g.classList.toggle('collapsed', collapsed);
  });
}

// ── 事件綁定 Event bindings ──
btnCompare.addEventListener('click', runComparison);

toggleAll.addEventListener('change', () => {
  showAll = toggleAll.checked;
  renderGroups();
});

toggleExpand.addEventListener('change', () => {
  setAllGroups(!toggleExpand.checked);
});

// ── 啟動 Init ──
init();
