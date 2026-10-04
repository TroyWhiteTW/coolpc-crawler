// 分類頁的漸進增強：價格表即時篩選、回到列表頂端按鈕。HTML 本身已含完整資料，沒有 JS 也能瀏覽
// Progressive enhancement for category pages: a live price-list filter and a back-to-list
// button. The HTML already carries every row, so the page still works without JS
const list = document.getElementById('price-list');
const input = document.getElementById('list-filter-input');
const status = document.querySelector('.filter-status');
const index = document.querySelector('.sub-index');
const back = document.querySelector('.back-to-list');

// 全形英數轉半形並忽略大小寫，「９８００Ｘ３Ｄ」與「9800x3d」視為相同
// Fold full-width characters and case so "９８００Ｘ３Ｄ" matches "9800x3d"
const norm = (s) => s.normalize('NFKC').toLowerCase();

const blocks = [...document.querySelectorAll('.sub-block')].map((block) => {
  const title = block.querySelector('h3');
  // 子分類名稱一併比對：輸入「27吋」可列出整個 27 吋區塊
  // Match the subcategory name too: typing "27吋" brings up the whole 27-inch block
  const sub = norm(title.firstChild.textContent);
  const rows = [...block.querySelectorAll('tbody tr')].map((tr) => ({
    tr,
    text: sub + ' ' + norm(tr.textContent),
  }));
  return { block, count: title.querySelector('.sub-count'), rows };
});
const total = blocks.reduce((n, b) => n + b.rows.length, 0);

// 以空白分隔的每個關鍵字都要出現（AND），無符合的子分類整塊隱藏
// Every space-separated term must appear (AND); subcategories with no match hide entirely
const applyFilter = () => {
  const terms = norm(input.value).split(/\s+/).filter(Boolean);
  const active = terms.length > 0;
  let shown = 0;
  for (const { block, count, rows } of blocks) {
    let n = 0;
    for (const row of rows) {
      const hit = !active || terms.every((t) => row.text.includes(t));
      row.tr.hidden = !hit;
      if (hit) n++;
    }
    block.hidden = n === 0;
    count.textContent = active ? `${n} / ${rows.length} 項` : `${rows.length} 項`;
    shown += n;
  }
  // 篩選時結果通常很短，索引反而擋路 While filtering the result is short; the index only gets in the way
  if (index) index.hidden = active;
  status.textContent = !active ? ''
    : shown ? `符合 ${shown} 項（共 ${total} 項）`
    : `沒有符合「${input.value.trim()}」的商品`;
};

if (input) {
  input.addEventListener('input', applyFilter);
  // 返回上一頁時瀏覽器可能還原輸入框內容，需重新套用
  // Back/forward navigation may restore the input's value; apply it again
  window.addEventListener('pageshow', () => { if (input.value) applyFilter(); });
}

if (list && back) {
  // 篩選框與索引捲出視窗上緣後才顯示按鈕 Show the button once the filter and index scroll off the top
  const tools = list.querySelector('.list-tools');
  new IntersectionObserver(([entry]) => {
    back.hidden = entry.isIntersecting || entry.boundingClientRect.top > 0;
  }).observe(tools);
  // 回到列表頂端時展開索引（手機預設收合），方便直接跳到其他子分類
  // Expand the index (collapsed by default on phones) so another subcategory is one tap away
  back.addEventListener('click', () => { if (index) index.open = true; });
}
