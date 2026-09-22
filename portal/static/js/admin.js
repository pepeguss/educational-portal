document.addEventListener('DOMContentLoaded', () => {
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const editor = document.getElementById('editor-dialog');
  const form = document.getElementById('editor-form');
  const nameInput = document.getElementById('editor-name');
  const descriptionInput = document.getElementById('editor-description');
  const descriptionField = document.getElementById('editor-description-field');
  const editorError = document.getElementById('editor-error');
  const filesDialog = document.getElementById('files-dialog');
  const filesList = document.getElementById('files-list');
  const fileInput = document.getElementById('file-input');
  const filesError = document.getElementById('files-error');
  let editorUrl = '';
  let editingLecture = false;
  let saving = false;
  let filesBusy = false;
  let lectureCard = null;

  async function post(url, data) {
    const body = new FormData();
    for (const [key, value] of Object.entries(data)) {
      body.append(key, value ?? '');
    }
    const response = await fetch(url, {
      method: 'POST', body, headers: { 'X-CSRFToken': csrf },
    });
    const result = await response.json().catch(() => {
      throw new Error('Не удалось обработать ответ сервера. Обновите страницу и попробуйте ещё раз.');
    });
    if (!response.ok || result.error) {
      throw new Error(result.error || 'Не удалось сохранить изменения.');
    }
    return result;
  }

  function showError(element, message = '') {
    element.textContent = message;
    element.classList.toggle('hidden', !message);
  }

  function openEditor(title, url, values = {}, isLecture = false) {
    editorUrl = url;
    editingLecture = isLecture;
    form.reset();
    document.getElementById('editor-title').textContent = title;
    nameInput.value = values.title || '';
    nameInput.setCustomValidity('');
    descriptionInput.value = values.description || '';
    descriptionInput.disabled = !isLecture;
    descriptionField.classList.toggle('hidden', !isLecture);
    showError(editorError);
    editor.showModal();
    nameInput.focus();
  }

  nameInput.addEventListener('input', () => nameInput.setCustomValidity(''));
  document.getElementById('editor-cancel').addEventListener('click', () => editor.close());
  editor.addEventListener('cancel', (event) => {
    if (saving) event.preventDefault();
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (saving) return;
    const title = nameInput.value.trim();
    if (!title) {
      nameInput.setCustomValidity('Введите название.');
      nameInput.reportValidity();
      return;
    }
    const data = { title };
    if (editingLecture) data.description = descriptionInput.value.trim();
    saving = true;
    const controls = form.querySelectorAll('input, textarea, button');
    controls.forEach(control => { control.disabled = true; });
    showError(editorError);
    try {
      await post(editorUrl, data);
      location.reload();
    } catch (error) {
      showError(editorError, error.message);
    } finally {
      saving = false;
      controls.forEach(control => { control.disabled = false; });
      descriptionInput.disabled = !editingLecture;
    }
  });

  // Разметка файлов хранится в HTML; после изменений сохраняем список для повторного открытия.
  function syncFiles() {
    document.getElementById('files-empty').classList.toggle('hidden', filesList.childElementCount > 0);
    lectureCard.querySelector('[data-file-count]').textContent = filesList.childElementCount;
    lectureCard.querySelector('[data-lecture-files]').content.replaceChildren(
      ...Array.from(filesList.children, row => row.cloneNode(true))
    );
  }

  function setFilesBusy(busy) {
    filesBusy = busy;
    fileInput.disabled = busy;
    document.getElementById('files-close').disabled = busy;
    filesList.querySelectorAll('button').forEach(button => { button.disabled = busy; });
  }

  function openFilesManager(card) {
    lectureCard = card;
    filesList.replaceChildren(card.querySelector('[data-lecture-files]').content.cloneNode(true));
    fileInput.value = '';
    showError(filesError);
    document.getElementById('files-empty').classList.toggle('hidden', filesList.childElementCount > 0);
    filesDialog.showModal();
  }

  document.getElementById('files-close').addEventListener('click', () => filesDialog.close());
  filesDialog.addEventListener('cancel', (event) => {
    if (filesBusy) event.preventDefault();
  });

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file || filesBusy) return;
    setFilesBusy(true);
    showError(filesError);
    try {
      const result = await post(`/api/file/${lectureCard.dataset.lectureId}/upload/`, { file });
      const row = document.getElementById('file-row-template').content.cloneNode(true);
      row.querySelector('[data-file-name]').textContent = result.name;
      row.querySelector('[data-del-file]').dataset.delFile = result.id;
      filesList.append(row);
    } catch (error) {
      showError(filesError, error.message);
    } finally {
      fileInput.value = '';
      setFilesBusy(false);
      syncFiles();
    }
  });

  filesList.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-del-file]');
    if (!button || filesBusy) return;
    setFilesBusy(true);
    showError(filesError);
    try {
      await post(`/api/file/${button.dataset.delFile}/delete/`, {});
      button.closest('[data-file-row]').remove();
    } catch (error) {
      showError(filesError, error.message);
    } finally {
      setFilesBusy(false);
      syncFiles();
    }
  });

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-act]');
    if (!button || button.disabled) return;
    const section = button.closest('[data-section-id]');
    const lecture = button.closest('[data-lecture-id]');
    const sid = section?.dataset.sectionId;
    const lid = lecture?.dataset.lectureId;

    switch (button.dataset.act) {
      case 'add-section':
        openEditor('Новый раздел', '/api/section/create/');
        break;
      case 'edit-section':
        openEditor('Переименовать раздел', `/api/section/${sid}/update/`, {
          title: section.querySelector('.section-title').textContent,
        });
        break;
      case 'add-lecture':
        openEditor('Новая лекция', `/api/lecture/${sid}/create/`, {}, true);
        break;
      case 'edit-lecture':
        openEditor('Редактировать лекцию', `/api/lecture/${lid}/update/`, {
          title: lecture.querySelector('.lecture-title').textContent,
          description: lecture.dataset.description,
        }, true);
        break;
      case 'files':
        openFilesManager(lecture);
        break;
      case 'del-section':
      case 'del-lecture': {
        const deletingSection = button.dataset.act === 'del-section';
        if (!confirm(deletingSection ? 'Удалить раздел со всеми лекциями?' : 'Удалить лекцию?')) return;
        button.disabled = true;
        try {
          await post(deletingSection ? `/api/section/${sid}/delete/` : `/api/lecture/${lid}/delete/`, {});
          location.reload();
        } catch (error) {
          alert(error.message);
        } finally {
          button.disabled = false;
        }
        break;
      }
    }
  });
});
