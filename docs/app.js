// 歷史比價工具：讀取 crawl_history.json 與兩份 CSV 快照，在瀏覽器端比對漲跌
// Historical comparison tool: loads crawl_history.json plus two CSV snapshots and diffs them client-side

// ── 狀態 State ──
let compareResults = [];
let showAll = false;
// 檔名 → 模式 File → mode
const modeMap = new Map();
// 年 → 月 → 快照清單（最新在前）Year → month → entries, newest first
let index = {};
// 已載入或載入中的 CSV，切換 A/B 不重抓；失敗會移除以便重試
// Loaded or in-flight CSVs so switching A/B never refetches; failures are evicted for retry
const csvCache = new Map();
// 各分類的摺疊狀態，重新渲染時沿用 Collapsed state per category, kept across re-renders
const collapsedState = new Map();

// 分類顯示順序：主要零組件優先，名單須與 crawler/models.py 的 MAIN_CATEGORIES 一致
// Category order: main PC components first; keep in sync with MAIN_CATEGORIES in crawler/models.py
const PRIMARY_CATEGORIES = [
  '處理器 CPU', '主機板 MB', '記憶體 RAM', '固態硬碟 M.2｜SSD', '2.5/3.5 傳統內接硬碟HDD',
  '散熱器｜散熱墊｜散熱膏', '封閉式｜開放式水冷', '顯示卡VGA', 'CASE 機殼(+電源)', '電源供應器',
];
const STATUS_ORDER = { up: 0, down: 1, new: 2, removed: 3, same: 4 };
const STATUS_LABEL = { up: '▲ 漲價', down: '▼ 降價', same: '— 持平', new: '✦ 新增', removed: '✕ 下架' };

// ── DOM 元素 Elements ──
const $ = (id) => document.getElementById(id);
const btnCompare = $('btnCompare');
const loadingOverlay = $('loadingOverlay');
const mainContent = $('mainContent');
const groupsSection = $('groupsSection');
const toggleAll = $('toggleAll');
const toggleExpand = $('toggleExpand');
const headerMeta = $('headerMeta');
const modeNotice = $('modeNotice');
const selectors = {
  A: { year: $('selectA_year'), month: $('selectA_month'), entry: $('selectA_entry') },
  B: { year: $('selectB_year'), month: $('selectB_month'), entry: $('selectB_entry') },
};

// ── 工具函式 Utilities ──
const FILE_RE = /coolpc_(?<year>\d{4})(?<month>\d{2})(?<day>\d{2})_(?<hour>\d{2})(?<min>\d{2})(?<sec>\d{2})/;
const parseFilename = (file) => FILE_RE.exec(file)?.groups ?? null;
const money = (n) => `$${Number(n).toLocaleString()}`;
const formatPrice = (price) => (price == null || price === '' ? '—' : money(price));
const formatDiff = (diff) => (diff === 0 ? '0' : `${diff > 0 ? '+' : '-'}${money(Math.abs(diff))}`);
const formatPct = (pct) => (pct == null ? '—' : pct === 0 ? '0%' : `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`);
const trend = (diff) => (diff > 0 ? 'up' : diff < 0 ? 'down' : 'same');

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);

// 商品名稱開頭的 ｛型號｝（原價屋用全形括號，半形也接受）加粗、其餘規格降為次要色，
// 與 crawler/builder.py 的 _name_html() 一致
// Bold the leading ｛model｝ (CoolPC uses full-width braces; ASCII accepted too) and mute
// the rest, matching _name_html() in crawler/builder.py
const MODEL_RE = /^\s*[{｛]([^}｝]*)[}｝]\s*([\s\S]*)$/;
const nameHtml = (name) => {
  const m = MODEL_RE.exec(name ?? '');
  if (!m) return escapeHtml(name);
  return `<span class="model">${escapeHtml(m[1])}</span>${m[2] ? ` <span class="spec">${escapeHtml(m[2])}</span>` : ''}`;
};

// ── CSV 載入 Load CSV via PapaParse ──
const loadCSV = (file) => {
  if (!csvCache.has(file)) {
    csvCache.set(file, new Promise((resolve, reject) => {
      // CSV 位於站台根目錄的 output/ CSVs live in output/ at the site root
      Papa.parse(`output/${file}`, {
        download: true,
        header: true,
        skipEmptyLines: true,
        complete: ({ data }) => resolve(data),
        error: (err) => { csvCache.delete(file); reject(err); },
      });
    }));
  }
  return csvCache.get(file);
};

// ── 快照選單 Snapshot selectors ──
const buildIndex = (entries) => {
  index = {};
  modeMap.clear();
  for (const { file, mode } of entries) {
    const p = parseFilename(file);
    if (!p) continue;
    modeMap.set(file, mode);
    ((index[p.year] ??= {})[p.month] ??= []).push({ file, mode, ...p });
  }
};

const desc = (obj) => Object.keys(obj).sort().reverse();
const fill = (select, pairs) => select.replaceChildren(...pairs.map(([text, value]) => new Option(text, value)));
const populateYears = (side) => fill(selectors[side].year, desc(index).map((y) => [`${y} 年`, y]));
const populateMonths = (side) => {
  const { year, month } = selectors[side];
  fill(month, desc(index[year.value] ?? {}).map((m) => [`${m} 月`, m]));
};
const populateEntries = (side) => {
  const { year, month, entry } = selectors[side];
  const list = index[year.value]?.[month.value] ?? [];
  fill(entry, list.map((e) => [`${e.day}日 ${e.hour}:${e.min} [${e.mode}]`, e.file]));
};
const initSide = (side) => {
  populateYears(side);
  populateMonths(side);
  populateEntries(side);
};
// 年 → 月 → 快照三級連動 Year → month → entry cascade
const bindCascade = (side) => {
  const { year, month } = selectors[side];
  year.addEventListener('change', () => { populateMonths(side); populateEntries(side); });
  month.addEventListener('change', () => populateEntries(side));
};
const selectedFile = (side) => selectors[side].entry.value;
const modeOf = (file) => modeMap.get(file) ?? 'MAIN';

// ── 商品識別 Product identity ──
// 商品識別鍵，須與 crawler/builder.py 的 _row_key() 一致。同名商品會列在不同子分類
// （同型號螢幕分列 27 吋與 32 吋區塊，價差 7 倍），只用 name 會互相覆蓋產生假漲跌。
// Product identity key; must match _row_key() in crawler/builder.py. The same name appears
// under different subcategories (7x apart in price), so name alone would collide.
const rowKey = (r) => `${r.category || ''} ${r.subcategory || ''} ${r.name}`;

// 以「識別鍵 + 第幾次出現」建表，須與 crawler/builder.py 的 _occurrence_keys() 一致：每一列都推進
// 出現序，只有同時有名稱與價格的列才進表；同一子分類內同名商品以出現序配對，第 n 筆對第 n 筆。
// 一併回傳出現過的分類。
// Index by identity key plus nth occurrence, matching _occurrence_keys() in crawler/builder.py: every
// row advances the counter, only rows with both a name and a price are stored; duplicates within one
// subcategory pair by occurrence order. Also returns the categories seen.
const buildKeyedMap = (rows) => {
  const map = new Map();
  const seen = new Map();
  const cats = new Set();
  for (const row of rows) {
    const k = rowKey(row);
    const n = seen.get(k) ?? 0;
    seen.set(k, n + 1);
    if (row.name && row.price) {
      map.set(`${k} #${n}`, row);
      cats.add(row.category);
    }
  }
  return { map, cats };
};

// ── 比對 Comparison ──
const buildComparison = (fileA, fileB, dataA, dataB) => {
  const { map: mapA, cats: catsA } = buildKeyedMap(dataA);
  const { map: mapB, cats: catsB } = buildKeyedMap(dataB);

  // 只比較兩邊都有的分類，避免 MAIN/ALL 模式差異被算成新增或下架
  // Compare only categories present on both sides so MAIN/ALL differences aren't read as adds/removals
  const shared = new Set([...catsA].filter((c) => catsB.has(c)));
  const excluded = [...new Set([...catsA, ...catsB])].filter((c) => !shared.has(c));
  modeNotice.style.display = excluded.length ? 'block' : 'none';
  if (excluded.length) {
    modeNotice.innerHTML = `<div class="mode-notice-inner">⚠ 舊(A) 為 ${escapeHtml(modeOf(fileA))} 模式，新(B) 為 ${escapeHtml(modeOf(fileB))} 模式，已自動排除非共同分類（${excluded.map(escapeHtml).join('、')}），僅比較共同存在的 ${shared.size} 個分類。</div>`;
  }

  compareResults = [];
  for (const key of new Set([...mapA.keys(), ...mapB.keys()])) {
    const a = mapA.get(key);
    const b = mapB.get(key);
    const { name, category = '' } = a ?? b;
    if (!shared.has(category)) continue;
    const priceA = a ? Number(a.price) : null;
    const priceB = b ? Number(b.price) : null;
    // 價差 = 新(B) − 舊(A)，正數為漲價；只在一邊出現即為新增或下架
    // diff = new(B) − old(A), positive means up; present on one side only means new or removed
    const diff = priceA != null && priceB != null ? priceB - priceA : null;
    const status = diff != null ? trend(diff) : priceB != null ? 'new' : 'removed';
    const pct = diff != null && priceA ? (diff / priceA) * 100 : null;
    compareResults.push({ name, category, priceA, priceB, diff, pct, status, remark: b?.remark || a?.remark || '' });
  }

  updateStats();
  renderGroups();
  mainContent.style.display = 'block';
};

const runComparison = async () => {
  const fileA = selectedFile('A');
  const fileB = selectedFile('B');
  if (!fileA || !fileB) return;
  mainContent.style.display = 'none';
  loadingOverlay.classList.add('active');
  try {
    const [dataA, dataB] = await Promise.all([loadCSV(fileA), loadCSV(fileB)]);
    buildComparison(fileA, fileB, dataA, dataB);
  } catch (err) {
    console.error('Failed to load CSV:', err);
    // 不用 alert 阻塞，改在頁首提示並保留選單讓使用者重試
    // No blocking alert: hint in the header and keep the selectors so the user can retry
    headerMeta.textContent = 'CSV 載入失敗，請重新比較';
  } finally {
    loadingOverlay.classList.remove('active');
  }
};

// ── 統計 Stats ──
const updateStats = () => {
  const counts = { Total: compareResults.length, Changed: 0, Up: 0, Down: 0, New: 0, Removed: 0 };
  for (const { status } of compareResults) {
    if (status === 'same') continue;
    counts.Changed += 1;
    counts[status[0].toUpperCase() + status.slice(1)] += 1;
  }
  for (const [key, n] of Object.entries(counts)) $(`stat${key}`).textContent = n;
};

// ── 渲染 Rendering ──
const TABLE_HEAD = '<thead><tr><th class="th-name">商品名稱</th><th class="th-remark">備註</th>'
  + '<th class="th-price">舊 (A)</th><th class="th-price">新 (B)</th><th class="th-diff">價差</th>'
  + '<th class="th-pct">%</th><th class="th-status">狀態</th></tr></thead>';

// 儲存格順序固定：名稱、備註、A 價、B 價、價差、幅度、狀態，手機版 CSS 以 nth-child 定位 A/B 價
// Cell order is fixed (name, remark, price A, price B, diff, pct, status); mobile CSS positions the prices by nth-child
const rowHtml = (r) => {
  const t = trend(r.diff);
  const rowClass = r.status === 'new' ? ' class="row-new"' : r.status === 'removed' ? ' class="row-removed"' : '';
  return `<tr${rowClass}>`
    + `<td class="td-name">${nameHtml(r.name)}</td>`
    + `<td class="td-remark">${escapeHtml(r.remark)}</td>`
    + `<td class="td-price${r.priceA == null ? ' empty' : ''}">${formatPrice(r.priceA)}</td>`
    + `<td class="td-price${r.priceB == null ? ' empty' : ''}">${formatPrice(r.priceB)}</td>`
    + `<td class="td-diff ${t}">${r.diff != null ? formatDiff(r.diff) : '—'}</td>`
    + `<td class="td-pct ${t}">${formatPct(r.pct)}</td>`
    + `<td class="td-status"><span class="badge badge-${r.status}">${STATUS_LABEL[r.status]}</span></td>`
    + '</tr>';
};
const tableHtml = (rows) => `<div class="table-scroll"><table class="compare-table">${TABLE_HEAD}<tbody>${rows.map(rowHtml).join('')}</tbody></table></div>`;

const changedOf = (items) => items.filter((r) => r.status !== 'same').length;
const rank = (cat) => {
  const i = PRIMARY_CATEGORIES.indexOf(cat);
  return i === -1 ? PRIMARY_CATEGORIES.length : i;
};

const renderGroups = () => {
  // 記住目前摺疊狀態再重繪 Remember collapsed state before re-rendering
  for (const g of groupsSection.querySelectorAll('.category-group')) {
    collapsedState.set(g.dataset.category, g.classList.contains('collapsed'));
  }

  // 主要零組件優先，其餘依異動數遞減；組內依狀態再依名稱排序
  // Main components first, the rest by change count; within a group by status then name
  const grouped = [...Map.groupBy(compareResults, (r) => r.category)]
    .sort(([ca, ia], [cb, ib]) => rank(ca) - rank(cb) || changedOf(ib) - changedOf(ia) || ca.localeCompare(cb));

  groupsSection.innerHTML = grouped.map(([category, items]) => {
    items.sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.name.localeCompare(b.name));
    const changed = changedOf(items);
    const shown = showAll ? items : items.filter((r) => r.status !== 'same');
    const collapsed = collapsedState.get(category) ?? true;
    return `<div class="category-group${collapsed ? ' collapsed' : ''}" data-category="${escapeHtml(category)}">`
      + '<div class="category-header">'
      + `<div class="category-header-left"><span class="category-arrow">▼</span><span class="category-name">${escapeHtml(category)}</span></div>`
      + `<div class="category-badges">${changed ? `<span class="category-count has-changes">${changed} 異動</span>` : ''}<span class="category-count">${items.length} 項</span></div>`
      + '</div>'
      + `<div class="category-body">${shown.length ? tableHtml(shown) : '<div class="group-empty">無異動商品</div>'}</div>`
      + '</div>';
  }).join('');
};

// ── 初始化 Initialize ──
const init = async () => {
  try {
    const resp = await fetch('crawl_history.json');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const entries = await resp.json();
    if (!entries.length) {
      headerMeta.textContent = '尚無資料';
      return;
    }
    buildIndex(entries);

    // B（新）預設最新一筆；A（舊）預設同月第 6 筆，不足則取該月最後一筆
    // B (new) defaults to the newest entry; A (old) to the 6th of the same month, or the month's last
    initSide('B');
    initSide('A');
    selectors.A.entry.selectedIndex = Math.min(5, selectors.A.entry.options.length - 1);
    bindCascade('A');
    bindCascade('B');

    headerMeta.textContent = `共 ${entries.length} 筆歷史紀錄`;
    await runComparison();
  } catch (err) {
    console.error('Failed to load crawl history:', err);
    headerMeta.textContent = '載入失敗';
  }
};

// ── 事件 Events ──
// 分類標題的展開／收合用事件委派，重繪後不必重新綁定
// Group headers toggle via delegation, so re-rendering never rebinds listeners
groupsSection.addEventListener('click', (e) => e.target.closest('.category-header')?.parentElement.classList.toggle('collapsed'));
btnCompare.addEventListener('click', runComparison);
toggleAll.addEventListener('change', () => {
  showAll = toggleAll.checked;
  renderGroups();
});
toggleExpand.addEventListener('change', () => {
  for (const g of groupsSection.querySelectorAll('.category-group')) g.classList.toggle('collapsed', !toggleExpand.checked);
});

init();
