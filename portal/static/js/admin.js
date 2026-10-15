document.addEventListener('DOMContentLoaded', () => {
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const editor = document.getElementById('editor-dialog');
  const form = document.getElementById('editor-form');
  const nameInput = document.getElementById('editor-name');
  const descriptionInput = document.getElementById('editor-description');
  const descriptionField = document.getElementById('editor-description-field');
  const testOptions = document.getElementById('editor-test-options');
  const hasTestInput = document.getElementById('editor-has-test');
  const testField = document.getElementById('editor-test-field');
  const testUrlInput = document.getElementById('editor-test-url');
  const editorError = document.getElementById('editor-error');
  const accessOptions = document.getElementById('editor-access-options');
  const departmentsField = document.getElementById('editor-departments');
  const filesDialog = document.getElementById('files-dialog');
  const filesList = document.getElementById('files-list');
  const fileInput = document.getElementById('file-input');
  const filesError = document.getElementById('files-error');
  let editorUrl = '';
  let editingLecture = false;
  let saving = false;
  let filesBusy = false;
  let lectureCard = null;
  const deleteDialog = document.getElementById('delete-dialog');
  const deleteForm = document.getElementById('delete-form');
  const deleteConfirm = document.getElementById('delete-confirm');
  const deleteError = document.getElementById('delete-error');
  let deletion = null;
  let deleting = false;

  function confirmDeletion(title, description, label, action) {
    if (deletion) return Promise.resolve(false);
    document.getElementById('delete-title').textContent = title;
    document.getElementById('delete-description').textContent = description;
    deleteConfirm.textContent = label;
    showError(deleteError);
    deleteDialog.returnValue = '';
    return new Promise(resolve => {
      deletion = { action, resolve, label };
      deleteDialog.showModal();
      document.getElementById('delete-cancel').focus();
    });
  }

  deleteForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (deleting || !deletion) return;
    deleting = true;
    deleteForm.querySelectorAll('button').forEach(button => { button.disabled = true; });
    deleteConfirm.textContent = 'Удаление…';
    showError(deleteError);
    try {
      await deletion.action();
      deleteDialog.close('deleted');
    } catch (error) {
      showError(deleteError, error.message);
    } finally {
      deleting = false;
      deleteForm.querySelectorAll('button').forEach(button => { button.disabled = false; });
      if (deletion) deleteConfirm.textContent = deletion.label;
    }
  });
  ['delete-cancel', 'delete-close'].forEach(id => {
    document.getElementById(id).addEventListener('click', () => {
      if (!deleting) deleteDialog.close('cancel');
    });
  });
  deleteDialog.addEventListener('cancel', event => {
    if (deleting) event.preventDefault();
  });
  deleteDialog.addEventListener('click', event => {
    const rect = deleteDialog.getBoundingClientRect();
    if (!deleting && event.target === deleteDialog &&
        (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) {
      deleteDialog.close('cancel');
    }
  });
  deleteDialog.addEventListener('close', () => {
    const pending = deletion;
    deletion = null;
    pending?.resolve(deleteDialog.returnValue === 'deleted');
  });

  async function post(url, data) {
    const body = new FormData();
    for (const [key, value] of Object.entries(data)) {
      for (const item of Array.isArray(value) ? value : [value]) {
        body.append(key, item ?? '');
      }
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

  function syncTestField() {
    const enabled = editingLecture && hasTestInput.checked;
    testOptions.classList.toggle('hidden', !editingLecture);
    hasTestInput.disabled = !editingLecture;
    testField.classList.toggle('hidden', !enabled);
    testUrlInput.disabled = !enabled;
    testUrlInput.required = enabled;
  }

  hasTestInput.addEventListener('change', () => {
    syncTestField();
    if (hasTestInput.checked) testUrlInput.focus();
  });

  function syncAccessFields() {
    accessOptions.classList.toggle('hidden', !editingLecture);
    accessOptions.disabled = !editingLecture;
    const restricted = form.elements.visibility.value === 'departments';
    departmentsField.classList.toggle('hidden', !restricted);
    departmentsField.querySelectorAll('input').forEach(input => {
      input.disabled = !editingLecture || !restricted;
    });
  }

  accessOptions.addEventListener('change', syncAccessFields);

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
    testUrlInput.value = values.test_url || '';
    hasTestInput.checked = Boolean(values.test_url);
    syncTestField();
    form.elements.visibility.value = values.visibility || 'all';
    const selectedDepartments = (values.departments || '').split(',');
    departmentsField.querySelectorAll('input').forEach(input => {
      input.checked = selectedDepartments.includes(input.value);
    });
    syncAccessFields();
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
    if (editingLecture) {
      data.description = descriptionInput.value.trim();
      data.has_test = hasTestInput.checked ? '1' : '0';
      data.test_url = hasTestInput.checked ? testUrlInput.value.trim() : '';
      data.visibility = form.elements.visibility.value;
      data.departments = Array.from(departmentsField.querySelectorAll('input:checked'), input => input.value);
      if (data.visibility === 'departments' && !data.departments.length) {
        showError(editorError, 'Выберите хотя бы один отдел. Если отделов нет, сначала создайте отдел в админке.');
        return;
      }
    }
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
      syncTestField();
      syncAccessFields();
    }
  });

  const departmentsForm = document.getElementById('user-departments-form');
  const userSearch = document.getElementById('user-search');
  const searchStatus = document.getElementById('user-search-status');
  const searchEmpty = document.getElementById('users-search-empty');
  const normalizeName = value => value.normalize('NFKC').toLocaleLowerCase('ru').replace(/ё/g, 'е').trim().replace(/\s+/g, ' ');
  const userRows = Array.from(departmentsForm.querySelectorAll('[data-user-row]'), row => ({
    row, name: normalizeName(row.dataset.userFullName),
  }));
  function filterUsers() {
    const query = normalizeName(userSearch.value);
    const words = query ? query.split(' ') : [];
    let total = 0;
    let visible = 0;
    userRows.forEach(({ row, name }) => {
      if (!row.isConnected) return;
      total++;
      row.hidden = !words.every(word => name.includes(word));
      if (!row.hidden) visible++;
    });
    searchStatus.textContent = `Показано: ${visible} из ${total}`;
    searchEmpty.hidden = visible > 0;
    searchEmpty.textContent = total ? 'Пользователи не найдены. Попробуйте изменить запрос.' : 'Пользователей пока нет.';
  }
  userSearch.addEventListener('input', filterUsers);
  filterUsers();
  const departmentSelects = Array.from(departmentsForm.querySelectorAll('select[data-user-id]'));
  const departmentSave = document.getElementById('save-departments');
  const departmentStatus = document.getElementById('departments-status');
  const departmentError = document.getElementById('departments-error');
  const savedDepartments = new Map(departmentSelects.map(select => [select, select.value]));
  const roleSelects = new Map(Array.from(departmentsForm.querySelectorAll('[data-user-role]'), select => [select.dataset.userRole, select]));
  const savedRoles = new Map(Array.from(roleSelects, ([id, select]) => [id, select.value]));
  let departmentsSaving = false;
  const changedDepartments = () => departmentSelects.filter(select =>
    select.isConnected && (select.value !== savedDepartments.get(select) || roleSelects.get(select.dataset.userId).value !== savedRoles.get(select.dataset.userId))
  );

  const deleteButtons = departmentsForm.querySelectorAll('[data-delete-user]');
  const departmentDeleteButtons = document.querySelectorAll('[data-act="del-department"]');
  const syncDeleteButtons = () => {
    deleteButtons.forEach(button => {
      button.disabled = departmentsSaving || button.hasAttribute('data-own-account');
    });
    departmentDeleteButtons.forEach(button => { button.disabled = departmentsSaving; });
  };
  departmentsForm.addEventListener('click', async event => {
    const button = event.target.closest('[data-delete-user]');
    if (!button || button.disabled || departmentsSaving) return;
    departmentsSaving = true;
    syncDeleteButtons();
    departmentSave.disabled = true;
    departmentSelects.forEach(select => { select.disabled = true; });
    roleSelects.forEach(select => { select.disabled = true; });
    showError(departmentError);
    try {
      const deleted = await confirmDeletion(
        'Удалить аккаунт?', `Аккаунт «${button.dataset.userName}» будет удалён. Пользователь потеряет доступ к порталу.`,
        'Удалить аккаунт', () => post(`/api/user/${button.dataset.deleteUser}/delete/`, {}),
      );
      if (!deleted) return;
      button.closest('[data-user-row]').remove();
      filterUsers();
      document.querySelectorAll('[data-department-count]').forEach(counter => {
        const count = departmentSelects.filter(select => select.isConnected && savedDepartments.get(select) === counter.dataset.departmentCount).length;
        counter.textContent = `${count} польз.`;
      });
      departmentStatus.textContent = changedDepartments().length
        ? `Несохранённых изменений: ${changedDepartments().length}` : 'Аккаунт удалён';
    } catch (error) {
      showError(departmentError, error.message);
    } finally {
      departmentsSaving = false;
      syncDeleteButtons();
      departmentSelects.forEach(select => { select.disabled = false; });
      roleSelects.forEach(select => { select.disabled = select.hasAttribute('data-own-role'); });
      departmentSave.disabled = changedDepartments().length === 0;
    }
  });

  departmentsForm.addEventListener('change', () => {
    const count = changedDepartments().length;
    departmentSave.disabled = departmentsSaving || count === 0;
    departmentStatus.textContent = count ? `Несохранённых изменений: ${count}` : 'Нет изменений';
    showError(departmentError);
  });

  window.addEventListener('beforeunload', event => {
    if (changedDepartments().length) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  departmentsForm.addEventListener('submit', async event => {
    event.preventDefault();
    const changed = changedDepartments();
    if (departmentsSaving || !changed.length) return;
    const changes = changed.map(select => ({
      user_id: Number(select.dataset.userId),
      department_id: select.value ? Number(select.value) : null,
      ...(roleSelects.get(select.dataset.userId).value !== savedRoles.get(select.dataset.userId)
        ? { role: roleSelects.get(select.dataset.userId).value } : {}),
    }));
    departmentsSaving = true;
    syncDeleteButtons();
    departmentSave.disabled = true;
    departmentSelects.forEach(select => { select.disabled = true; });
    roleSelects.forEach(select => { select.disabled = true; });
    departmentSave.textContent = 'Сохранение…';
    showError(departmentError);
    try {
      await post(departmentsForm.action, { changes: JSON.stringify(changes) });
      changed.forEach(select => {
        savedDepartments.set(select, select.value);
        savedRoles.set(select.dataset.userId, roleSelects.get(select.dataset.userId).value);
      });
      departmentStatus.textContent = `Изменения сохранены: ${changed.length}`;
      document.querySelectorAll('[data-department-count]').forEach(counter => {
        const count = departmentSelects.filter(select => select.isConnected && select.value === counter.dataset.departmentCount).length;
        counter.textContent = `${count} польз.`;
      });
    } catch (error) {
      showError(departmentError, error.message);
    } finally {
      departmentsSaving = false;
      syncDeleteButtons();
      departmentSelects.forEach(select => { select.disabled = false; });
      roleSelects.forEach(select => { select.disabled = select.hasAttribute('data-own-role'); });
      departmentSave.textContent = 'Сохранить изменения';
      departmentSave.disabled = changedDepartments().length === 0;
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
      case 'del-department': {
        if (departmentsSaving) return;
        if (changedDepartments().length) {
          departmentsForm.closest('details').open = true;
          showError(departmentError, 'Сначала сохраните изменения пользователей, затем удалите отдел.');
          departmentSave.scrollIntoView({ block: 'center' });
          return;
        }
        departmentsSaving = true;
        syncDeleteButtons();
        departmentSelects.forEach(select => { select.disabled = true; });
        roleSelects.forEach(select => { select.disabled = true; });
        try {
          const deleted = await confirmDeletion(
            'Удалить отдел?', `Отдел «${button.dataset.departmentName}» будет удалён. Его сотрудники останутся в системе без отдела. Лекции сохранятся; доступ этого отдела к ним будет снят.`,
            'Удалить отдел', () => post(`/api/department/${button.dataset.departmentId}/delete/`, {}),
          );
          if (!deleted) return;
          location.reload();
        } catch (error) {
          showError(departmentError, error.message);
        } finally {
          departmentsSaving = false;
          syncDeleteButtons();
          departmentSelects.forEach(select => { select.disabled = false; });
          roleSelects.forEach(select => { select.disabled = select.hasAttribute('data-own-role'); });
        }
        break;
      }
      case 'add-department':
        openEditor('Новый отдел', '/api/department/create/');
        break;
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
          test_url: lecture.dataset.testUrl,
          visibility: lecture.dataset.visibility,
          departments: lecture.dataset.departments,
        }, true);
        break;
      case 'files':
        openFilesManager(lecture);
        break;
      case 'del-section':
      case 'del-lecture': {
        const deletingSection = button.dataset.act === 'del-section';
        button.disabled = true;
        try {
          const deleted = await confirmDeletion(
            deletingSection ? 'Удалить раздел?' : 'Удалить лекцию?',
            deletingSection ? `Раздел «${section.querySelector('.section-title').textContent.trim()}», все его лекции и файлы будут удалены.`
              : `Лекция «${lecture.querySelector('.lecture-title').textContent.trim()}» и все её файлы будут удалены.`,
            deletingSection ? 'Удалить раздел' : 'Удалить лекцию',
            () => post(deletingSection ? `/api/section/${sid}/delete/` : `/api/lecture/${lid}/delete/`, {}),
          );
          if (!deleted) return;
          location.reload();
        } finally {
          button.disabled = false;
        }
        break;
      }
    }
  });
});
