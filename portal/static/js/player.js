document.addEventListener('DOMContentLoaded', () => {
  const tabs = document.querySelectorAll('.file-tab');
  const viewer = document.getElementById('viewer');
  if (!tabs.length || !viewer) return;

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(b => b.classList.remove('bg-amber-500','text-graphite-900','border-amber-500'));
      tab.classList.add('bg-amber-500','text-graphite-900','border-amber-500');
      renderFile(tab.dataset);
    });
  });
  tabs[0].click();

  async function renderFile(data){
    const { fileType, fileUrl, fileName } = data;
    viewer.classList.toggle('pdf-viewer', fileType === 'pdf');
    viewer.innerHTML = '<div class="flex items-center justify-center h-[500px] text-gray-400">Загрузка…</div>';

    if (fileType === 'pdf') {
      viewer.innerHTML = `
        <div class="pdf-wrap">
          <iframe src="${fileUrl}#page=1&view=Fit&toolbar=0&navpanes=0"
                  title="Просмотр PDF" oncontextmenu="return false"></iframe>
        </div>`;
    }
    else if (fileType === 'docx') {
      try {
        const res = await fetch(fileUrl);
        const buf = await res.arrayBuffer();
        const result = await mammoth.convertToHtml({ arrayBuffer: buf });
        viewer.innerHTML = `<div class="p-8 prose max-w-none h-[75vh] overflow-y-auto" oncontextmenu="return false">${result.value}</div>`;
      } catch (e) {
        viewer.innerHTML = `<div class="p-8 text-red-500">Ошибка: ${e.message}</div>`;
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
          <div class="font-semibold mb-6">${fileName}</div>
          <audio src="${fileUrl}" controls controlslist="nodownload" oncontextmenu="return false" class="w-full max-w-md"></audio>
        </div>`;
    }
  }

  // Защита от копирования
  document.addEventListener('contextmenu', e => {
    if (e.target.closest('.protected-viewer')) e.preventDefault();
  });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && ['s','p'].includes(e.key.toLowerCase())) {
      if (document.querySelector('.protected-viewer')) e.preventDefault();
    }
  });
});
