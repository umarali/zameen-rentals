/** A small header disclosure; information opens only when a topic is chosen. */
const PAGES = {
  about: { path: '/about', title: 'About ZameenRentals' },
  pricing: { path: '/pricing', title: 'Pricing' },
  faq: { path: '/faq', title: 'A few useful answers' },
};

export function initSiteMenu({ onHelp }) {
  const trigger = document.getElementById('siteMenuBtn');
  const menu = document.getElementById('siteMenu');
  const anchor = trigger.parentElement;
  const items = [...menu.querySelectorAll('a, button')];
  const dialog = document.createElement('dialog');
  dialog.id = 'siteInfoDialog';
  dialog.className = 'site-info-dialog';
  dialog.setAttribute('aria-labelledby', 'siteInfoTitle');
  dialog.innerHTML = `
    <div class="site-info-heading"><h2 id="siteInfoTitle"></h2><button type="button" data-info-close aria-label="Close information" autofocus>&times;</button></div>
    <div class="site-info-content"></div>
    <div class="site-info-footer"><button type="button" data-info-search>Back to search <span aria-hidden="true">↗</span></button></div>`;
  document.body.append(dialog);
  const content = dialog.querySelector('.site-info-content');
  let pending;

  function setMenu(open) {
    menu.hidden = !open;
    trigger.setAttribute('aria-expanded', String(open));
  }
  function closeInfo() {
    pending?.abort();
    pending = null;
    dialog.close();
    trigger.focus();
  }
  trigger.addEventListener('click', () => setMenu(menu.hidden));
  trigger.addEventListener('keydown', event => {
    if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    event.preventDefault();
    setMenu(true);
    items[event.key === 'ArrowDown' ? 0 : items.length - 1].focus();
  });
  anchor.addEventListener('keydown', event => {
    if (menu.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      setMenu(false);
      trigger.focus();
    } else if (items.includes(event.target) && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const index = items.indexOf(event.target);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 :
        (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[next].focus();
    }
  });
  document.addEventListener('pointerdown', event => {
    if (!anchor.contains(event.target)) setMenu(false);
  });
  document.addEventListener('focusin', event => {
    if (!anchor.contains(event.target)) setMenu(false);
  });
  menu.querySelector('#welcomeBtn').addEventListener('click', () => {
    setMenu(false);
    trigger.focus(); // Help restores focus to the visible header control.
    onHelp();
  });
  dialog.querySelector('[data-info-close]').addEventListener('click', closeInfo);
  dialog.querySelector('[data-info-search]').addEventListener('click', () => {
    closeInfo();
    document.getElementById('nlInput').focus();
  });
  dialog.addEventListener('cancel', event => {
    event.preventDefault();
    closeInfo();
  });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) closeInfo();
  });

  async function showPage(key) {
    const page = PAGES[key];
    setMenu(false);
    trigger.focus();
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 8000);
    dialog.querySelector('#siteInfoTitle').textContent = page.title;
    content.innerHTML = '<p role="status">Loading…</p>';
    content.setAttribute('aria-busy', 'true');
    dialog.showModal();
    try {
      const response = await fetch(page.path, { signal: controller.signal });
      if (!response.ok) throw new Error('Page unavailable');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const body = doc.querySelector('.site-info-body');
      if (!body) throw new Error('Page unavailable');
      if (pending !== controller || !dialog.open) return;
      content.replaceChildren(...body.childNodes);
    } catch (error) {
      if (pending !== controller || (error.name === 'AbortError' && !timedOut)) return;
      const message = document.createElement('p');
      message.setAttribute('role', 'status');
      message.textContent = 'This information could not be loaded. ';
      const link = document.createElement('a');
      link.href = page.path;
      link.textContent = 'Open the page';
      message.append(link);
      content.replaceChildren(message);
    } finally {
      clearTimeout(timer);
      if (pending === controller) content.removeAttribute('aria-busy');
    }
  }
  menu.addEventListener('click', event => {
    const link = event.target.closest('a[data-site-info]');
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    showPage(link.dataset.siteInfo);
  });
}
