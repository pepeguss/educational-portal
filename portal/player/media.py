"""Authenticated media delivery with byte ranges for native audio/video seeking."""
import re

from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.utils.http import content_disposition_header


class FileSlice:
    """Bound each response to its range, without loading the media into memory."""
    def __init__(self, stream, start, length):
        self.stream = stream
        self.remaining = length
        stream.seek(start)

    def __iter__(self):
        return self

    def __next__(self):
        if self.remaining <= 0:
            self.close()
            raise StopIteration
        chunk = self.stream.read(min(64 * 1024, self.remaining))
        if not chunk:
            self.close()
            raise StopIteration
        self.remaining -= len(chunk)
        return chunk

    def close(self):
        self.stream.close()


def media_response(request, obj):
    size = obj.file.size
    content_type = {'mp4': 'video/mp4', 'mp3': 'audio/mpeg'}[obj.type]
    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Disposition': content_disposition_header(False, obj.name),
        'Content-Length': str(size),
    }
    if request.method == 'HEAD':
        return HttpResponse(content_type=content_type, headers=headers)

    # Ignore unsupported/malformed ranges and conditional ranges without a validator.
    value = request.headers.get('Range', '') if request.method == 'GET' and not request.headers.get('If-Range') else ''
    match = re.fullmatch(r'bytes=([0-9]*)-([0-9]*)', value.strip())
    if match and any(match.groups()):
        # Very large offsets are outside the file; avoid unbounded int conversion.
        def offset(value):
            digits = value.lstrip('0') or '0'
            return int(digits) if len(digits) <= 20 else size + 1

        first, last = match.groups()
        if first:
            start = offset(first)
            end = min(offset(last), size - 1) if last else size - 1
        else:
            length = offset(last)
            start, end = max(0, size - length), size - 1
        if start >= size or end < start:
            return HttpResponse(status=416, headers={
                'Accept-Ranges': 'bytes', 'Content-Range': f'bytes */{size}',
                'Content-Length': '0',
            })
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
        headers['Content-Length'] = str(end - start + 1)
        return StreamingHttpResponse(
            FileSlice(obj.file.open('rb'), start, end - start + 1),
            status=206, content_type=content_type, headers=headers,
        )
    return FileResponse(obj.file.open('rb'), content_type=content_type, filename=obj.name, headers=headers)
