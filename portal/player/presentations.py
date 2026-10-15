"""Prepare private slide previews without sending presentations to third parties."""
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError


def presentation_pdf(upload):
    if upload.size > 100 * 1024 * 1024:
        raise ValidationError('Презентация должна быть не больше 100 МБ.')
    try:
        with ZipFile(upload) as archive:
            names = set(archive.namelist())
            if not {'[Content_Types].xml', 'ppt/presentation.xml'} <= names:
                raise BadZipFile
            if sum(item.file_size for item in archive.infolist()) > 500 * 1024 * 1024:
                raise ValidationError('Содержимое презентации слишком большое.')
    except (BadZipFile, OSError):
        raise ValidationError('Файл повреждён или не является презентацией PPTX.')
    finally:
        upload.seek(0)

    executable = getattr(settings, 'LIBREOFFICE_BINARY', None) or shutil.which('soffice')
    if not executable:
        raise ValidationError('Просмотр презентаций пока недоступен: на сервере требуется LibreOffice Impress.')
    with TemporaryDirectory(prefix='lecture-slides-') as directory:
        root = Path(directory)
        source = root / 'slides.pptx'
        with source.open('wb') as stream:
            for chunk in upload.chunks():
                stream.write(chunk)
        upload.seek(0)
        try:
            subprocess.run([
                executable, f'-env:UserInstallation={(root / "profile").as_uri()}',
                '--headless', '--convert-to', 'pdf:impress_pdf_Export',
                '--outdir', str(root), str(source),
            ], check=True, capture_output=True, timeout=120)
            result = (root / 'slides.pdf').read_bytes()
            if not result.startswith(b'%PDF-'):
                raise ValueError('Invalid PDF')
        except (OSError, subprocess.SubprocessError, ValueError):
            raise ValidationError('Не удалось подготовить слайды. Проверьте презентацию и повторите загрузку.')
        return result
