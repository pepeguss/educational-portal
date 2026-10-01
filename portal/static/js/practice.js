document.addEventListener('DOMContentLoaded', () => {
  const panel = document.getElementById('practice-work');
  const upload = document.getElementById('practice-upload');
  const error = document.getElementById('practice-error');
  const progress = document.getElementById('practice-progress');
  const csrf = panel.querySelector('[name=csrfmiddlewaretoken]').value;
  let busy = false;

  async function save(url, body) {
    if (busy) return;
    busy = true;
    error.classList.add('hidden');
    progress.classList.remove('hidden');
    const controls = Array.from(panel.querySelectorAll('input, button'), element => [element, element.disabled]);
    controls.forEach(([element]) => { element.disabled = true; });
    try {
      const response = await fetch(url, { method: 'POST', body, headers: { 'X-CSRFToken': csrf } });
      const result = await response.json().catch(() => {
        throw new Error('Не удалось обработать ответ сервера. Обновите страницу и попробуйте ещё раз.');
      });
      if (!response.ok) throw new Error(result.error || 'Не удалось сохранить работу.');
      location.reload();
    } catch (failure) {
      error.textContent = failure.message;
      error.classList.remove('hidden');
      progress.classList.add('hidden');
      controls.forEach(([element, disabled]) => { element.disabled = disabled; });
      busy = false;
    }
  }

  upload?.addEventListener('submit', event => {
    event.preventDefault();
    const files = upload.elements.files.files;
    if (files.length > 10 || Array.from(files).some(file => !file.size || file.size > 20 * 1024 * 1024)) {
      error.textContent = 'Выберите до 10 непустых файлов, каждый не больше 20 МБ.';
      error.classList.remove('hidden');
      return;
    }
    save(upload.action, new FormData(upload));
  });

  panel.addEventListener('click', event => {
    const button = event.target.closest('[data-practice-action]');
    if (button && !button.disabled) save(button.dataset.practiceAction, new FormData());
  });
});
