document.addEventListener('DOMContentLoaded', () => {
  const tabs = document.querySelectorAll('.file-tab');
  const viewer = document.getElementById('viewer');
  if (!tabs.length || !viewer) return;
  let revision = 0;
  let cleanup = () => {};
  let pdfLibrary;

  function showError(error) {
    const message = document.createElement('div');
    message.className = 'p-8 text-red-500';
    message.setAttribute('role', 'alert');
    message.textContent = `Не удалось открыть документ: ${error.message}`;
    viewer.replaceChildren(message);
  }

  async function renderPdf(fileUrl, current) {
    pdfLibrary ||= import('https://cdn.jsdelivr.net/npm/pdfjs-dist@5.4.149/build/pdf.min.mjs');
    const pdfjs = await pdfLibrary.catch(error => { pdfLibrary = null; throw error; });
    if (current !== revision) return;
    pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@5.4.149/build/pdf.worker.min.mjs';
    const task = pdfjs.getDocument({ url: fileUrl, isEvalSupported: false });
    let observer;
    cleanup = () => {
      observer?.disconnect();
      void task.destroy().catch(() => {});
    };
    const pdf = await task.promise;
    if (current !== revision) return;
    const scroll = document.createElement('div');
    scroll.className = 'document-scroll';
    viewer.replaceChildren(scroll);
    const width = Math.max(200, scroll.clientWidth - 32);
    let queue = Promise.resolve();
    // Render nearby pages one at a time, without a selectable text or annotation layer.
    observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        queue = queue.then(async () => {
          if (current !== revision) return;
          const page = await pdf.getPage(Number(entry.target.dataset.page));
          if (current !== revision) return;
          const viewport = page.getViewport({ scale: 1 });
          const scale = Math.min(width / viewport.width, 1.5);
          const display = page.getViewport({ scale });
          const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
          const canvas = document.createElement('canvas');
          canvas.width = Math.ceil(display.width * pixelRatio);
          canvas.height = Math.ceil(display.height * pixelRatio);
          canvas.setAttribute('aria-label', `Страница ${entry.target.dataset.page}`);
          entry.target.style.width = `${display.width}px`;
          entry.target.style.aspectRatio = `${display.width} / ${display.height}`;
          entry.target.replaceChildren(canvas);
          await page.render({
            canvasContext: canvas.getContext('2d'),
            viewport: page.getViewport({ scale: scale * pixelRatio }),
          }).promise;
          page.cleanup();
        }).catch(error => {
          if (current === revision) { cleanup(); showError(error); }
        });
      }
    }, { root: scroll, rootMargin: '500px' });
    for (let number = 1; number <= pdf.numPages; number++) {
      const page = document.createElement('div');
      page.className = 'pdf-page';
      page.dataset.page = number;
      page.style.width = `${width}px`;
      page.style.maxWidth = '100%';
      page.style.aspectRatio = '210 / 297';
      scroll.append(page);
      observer.observe(page);
    }
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(b => b.classList.remove('bg-amber-500','text-graphite-900','border-amber-500'));
      tab.classList.add('bg-amber-500','text-graphite-900','border-amber-500');
      renderFile(tab.dataset);
    });
  });
  tabs[0].click();

  async function renderFile(data){
    const current = ++revision;
    cleanup();
    cleanup = () => {};
    const { fileType, fileUrl, fileName } = data;
    viewer.classList.toggle('document-viewer', ['pdf', 'docx'].includes(fileType));
    viewer.innerHTML = '<div class="flex items-center justify-center h-[500px] text-gray-400">Загрузка…</div>';

    if (fileType === 'pdf') {
      try {
        await renderPdf(fileUrl, current);
      } catch (error) {
        if (current === revision) { cleanup(); showError(error); }
      }
    }
    else if (fileType === 'docx') {
      try {
        const controller = new AbortController();
        cleanup = () => controller.abort();
        const res = await fetch(fileUrl, { signal: controller.signal });
        if (!res.ok) throw new Error('Не удалось загрузить файл.');
        const buf = await res.arrayBuffer();
        if (current !== revision) return;
        if (!window.docx) throw new Error('Обновите страницу для загрузки просмотрщика DOCX.');
        const scroll = document.createElement('div');
        scroll.className = 'document-scroll';
        const content = document.createElement('div');
        content.className = 'docx-content';
        scroll.append(content);
        await docx.renderAsync(buf, content, null, {
          inWrapper: true, breakPages: true, ignoreLastRenderedPageBreak: false,
          useBase64URL: true, renderAltChunks: false,
        });
        if (current !== revision) return;
        // Keep document links from opening a separate, unprotected view.
        content.querySelectorAll('a').forEach(link => {
          link.removeAttribute('href');
          link.removeAttribute('tabindex');
        });
        viewer.replaceChildren(scroll);
      } catch (e) {
        if (current === revision) showError(e);
      }
    }
    else if (fileType === 'mp4') {
      viewer.innerHTML = `
        <div class="bg-black h-[75vh] flex items-center justify-center">
          <video src="${fileUrl}" controls controlslist="nodownload noremoteplayback"
                 disablepictureinpicture oncontextmenu="return false"
                 class="max-h-full max-w-full"></video>
        </div>`;
    }
    else if (fileType === 'mp3') {
      viewer.innerHTML = `
        <div class="p-10 flex flex-col items-center justify-center h-[50vh] bg-gradient-to-br from-graphite-900 to-graphite-700 text-white">
          <div class="w-24 h-24 rounded-full bg-amber-500 flex items-center justify-center mb-6">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#1a1d23" stroke-width="2"><path d="M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"/></svg>
          </div>
          <div class="font-semibold mb-6" data-audio-name></div>
          <audio src="${fileUrl}" controls controlslist="nodownload" oncontextmenu="return false" class="w-full max-w-md"></audio>
        </div>`;
      viewer.querySelector('[data-audio-name]').textContent = fileName;
    }
  }

  // Защита от копирования
  ['contextmenu', 'selectstart', 'copy', 'cut', 'dragstart'].forEach(type => {
    viewer.addEventListener(type, event => event.preventDefault(), true);
  });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && ['s','p'].includes(e.key.toLowerCase())) {
      if (document.querySelector('.protected-viewer')) e.preventDefault();
    }
    if (viewer.contains(e.target) && (e.ctrlKey || e.metaKey) && ['a', 'c', 'x'].includes(e.key.toLowerCase())) {
      e.preventDefault();
    }
  });
});
