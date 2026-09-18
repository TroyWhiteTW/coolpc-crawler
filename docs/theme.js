// 主題切換：預設深色，選擇存在 localStorage；<head> 的小段 script 會在首次繪製前還原
// Theme toggle: dark by default, the choice persists in localStorage; a snippet in <head>
// restores it before first paint
const root = document.documentElement;
const toggle = document.querySelector('.theme-toggle');
const themeColor = document.querySelector('meta[name="theme-color"]');
// 對應兩套 token 的 --bg，讓手機瀏覽器的狀態列跟著換色
// Matches --bg of each token set so mobile browser chrome follows the theme
const COLORS = { dark: '#0b0f1a', light: '#f7f6f2' };

const apply = (theme) => {
  root.dataset.theme = theme;
  toggle?.setAttribute('aria-checked', String(theme === 'light'));
  themeColor?.setAttribute('content', COLORS[theme]);
};

apply(root.dataset.theme === 'light' ? 'light' : 'dark');

toggle?.addEventListener('click', () => {
  const next = root.dataset.theme === 'light' ? 'dark' : 'light';
  apply(next);
  // 私密瀏覽等無法寫入時只影響本頁 Storage unavailable (private mode etc.): the choice lasts for this page only
  try { localStorage.setItem('theme', next); } catch {}
});
