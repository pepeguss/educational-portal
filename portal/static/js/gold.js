document.addEventListener('DOMContentLoaded', () => {
  const card = document.getElementById('gold-card');
  if (!card) return;
  const svg = document.getElementById('gold-chart');
  const status = document.getElementById('gold-status');
  const retry = document.getElementById('gold-retry');
  const tooltip = document.getElementById('gold-tooltip');
  const buttons = card.querySelectorAll('[data-days]');
  const money = value => value.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const date = value => new Date(`${value}T00:00:00Z`).toLocaleDateString('ru-RU', { timeZone: 'UTC' });
  const time = value => Date.parse(`${value}T00:00:00Z`);
  const put = (id, value) => { document.getElementById(id).textContent = value; };
  let points = [], days = 90, plotted = [];
  const ns = 'http://www.w3.org/2000/svg';
  function element(tag, attributes = {}, text = '') {
    const node = document.createElementNS(ns, tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    node.textContent = text;
    return node;
  }
  function draw() {
    if (!points.length) return;
    const last = points[points.length - 1];
    const cutoff = time(last.date) - days * 86400000;
    const selected = points.filter(point => time(point.date) >= cutoff);
    const first = selected[0];
    const delta = last.price - first.price;
    const sign = delta > 0 ? '+' : '';
    const values = selected.map(point => point.price);
    const min = Math.min(...values), max = Math.max(...values);
    const padding = Math.max((max - min) * 0.18, max * 0.002);
    const low = min - padding, high = max + padding;
    const x = point => 18 + (time(point.date) - time(first.date)) / (time(last.date) - time(first.date) || 1) * 780;
    const y = point => 268 - (point.price - low) / (high - low) * 244;
    plotted = selected.map(point => ({ ...point, x: x(point), y: y(point) }));
    put('gold-price', money(last.price));
    put('gold-date', `Цена на ${date(last.date)}`);
    put('gold-change', `${sign}${money(delta / first.price * 100)}% за период`);
    document.getElementById('gold-change').className = delta < 0 ? 'gold-change down' : 'gold-change up';
    put('gold-min', `${money(min)} ₽`);
    put('gold-max', `${money(max)} ₽`);
    put('gold-delta', `${sign}${money(delta)} ₽ / г`);
    buttons.forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.days) === days)));
    svg.replaceChildren();
    svg.append(element('title', { id: 'gold-chart-title' }, 'Цена золота в рублях за грамм'));
    svg.append(element('desc', { id: 'gold-chart-description' }, `С ${date(first.date)} по ${date(last.date)}. Минимум ${money(min)}, максимум ${money(max)}. Изменение ${sign}${money(delta)} рубля за грамм.`));
    const defs = element('defs');
    const gradient = element('linearGradient', { id: 'gold-fill', x1: '0', y1: '0', x2: '0', y2: '1' });
    gradient.append(element('stop', { offset: '0%', 'stop-color': '#e5ab29', 'stop-opacity': '.28' }), element('stop', { offset: '100%', 'stop-color': '#e5ab29', 'stop-opacity': '0' }));
    defs.append(gradient); svg.append(defs);
    for (let index = 0; index < 5; index++) {
      const height = 24 + index * 61;
      svg.append(element('line', { x1: 18, x2: 798, y1: height, y2: height, stroke: '#edf0f2', 'stroke-dasharray': '4 6' }));
      svg.append(element('text', { x: 818, y: height + 4, fill: '#9299a3', 'font-size': 12 }, Math.round(high - index / 4 * (high - low)).toLocaleString('ru-RU')));
    }
    const path = plotted.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ');
    svg.append(element('path', { d: `${path} L ${plotted[plotted.length - 1].x} 268 L 18 268 Z`, fill: 'url(#gold-fill)' }));
    svg.append(element('path', { d: path, fill: 'none', stroke: '#cf931b', 'stroke-width': 3, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    const end = plotted[plotted.length - 1];
    svg.append(element('circle', { cx: end.x, cy: end.y, r: 7, fill: '#cf931b', stroke: 'white', 'stroke-width': 3 }));
    for (let index = 0; index < 4; index++) {
      const point = plotted[Math.round(index / 3 * (plotted.length - 1))];
      svg.append(element('text', { x: 18 + index / 3 * 780, y: 305, 'text-anchor': index === 0 ? 'start' : index === 3 ? 'end' : 'middle', fill: '#9299a3', 'font-size': 12 }, date(point.date)));
    }
    tooltip.hidden = true;
  }
  svg.addEventListener('pointermove', event => {
    if (!plotted.length) return;
    const rect = svg.getBoundingClientRect();
    const pointerX = (event.clientX - rect.left) / rect.width * 900;
    const point = plotted.reduce((best, current) => Math.abs(current.x - pointerX) < Math.abs(best.x - pointerX) ? current : best);
    tooltip.textContent = `${date(point.date)} · ${money(point.price)} ₽ / г`;
    tooltip.hidden = false;
    tooltip.style.left = `${Math.max(0, Math.min(rect.width - tooltip.offsetWidth, point.x / 900 * rect.width - tooltip.offsetWidth / 2))}px`;
    tooltip.style.top = `${Math.max(0, point.y / 330 * rect.height - 44)}px`;
  });
  svg.addEventListener('pointerleave', () => { tooltip.hidden = true; });
  buttons.forEach(button => button.addEventListener('click', () => { days = Number(button.dataset.days); draw(); }));
  async function load() {
    retry.classList.add('hidden');
    status.textContent = 'Загружаем данные Банка России…';
    buttons.forEach(button => { button.disabled = true; });
    try {
      const response = await fetch(card.dataset.url, { headers: { Accept: 'application/json' } });
      const result = await response.json();
      if (!response.ok || !Array.isArray(result.points) || !result.points.length) throw new Error(result.error || 'Данные временно недоступны.');
      points = result.points;
      draw();
      document.getElementById('gold-content').hidden = false;
      status.textContent = result.stale ? 'Источник временно недоступен. Показаны последние сохранённые данные.' : '';
    } catch (error) {
      status.textContent = error.message === 'Failed to fetch' ? 'Не удалось загрузить цены. Проверьте соединение и попробуйте снова.' : error.message;
      retry.classList.remove('hidden');
    } finally {
      buttons.forEach(button => { button.disabled = false; });
    }
  }
  retry.addEventListener('click', load);
  load();
});
