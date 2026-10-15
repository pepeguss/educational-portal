const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(__dirname, '../static/vendor');
function copy(packageName, source, target) {
  const root = path.join(__dirname, 'node_modules', packageName);
  fs.cpSync(path.join(root, source), path.join(output, target), { recursive: true });
}
copy('jszip', 'dist/jszip.min.js', 'jszip.min.js');
copy('jszip', 'LICENSE.markdown', 'licenses/jszip.txt');
copy('docx-preview', 'dist/docx-preview.min.js', 'docx-preview.min.js');
copy('docx-preview', 'LICENSE', 'licenses/docx-preview.txt');
for (const part of ['build/pdf.min.mjs', 'build/pdf.worker.min.mjs', 'wasm', 'cmaps', 'standard_fonts', 'LICENSE']) {
  copy('pdfjs-dist', part, `pdfjs/${part}`);
}
