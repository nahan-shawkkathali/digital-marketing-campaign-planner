"""Stream already-authorized files, including bounded single video ranges."""
import re
from pathlib import Path

from django.http import FileResponse, HttpResponse


class FileSlice:
    def __init__(self, file, start, length):
        self.file = file
        self.remaining = length
        file.seek(start)

    def read(self, size):
        data = self.file.read(min(size, self.remaining)) if self.remaining else b""
        self.remaining -= len(data)
        return data

    def close(self):
        self.file.close()


def protected_file_response(request, deliverable):
    file = deliverable.uploaded_file.open("rb")
    size = file.size
    video_type = deliverable.video_content_type
    start, end, partial, invalid = 0, size - 1, False, False
    requested = request.headers.get("Range", "")
    # Ignore unsupported multi-ranges and conditional ranges without validators.
    if video_type and request.method == "GET" and requested.startswith("bytes=") and "," not in requested and "If-Range" not in request.headers:
        match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", requested)
        invalid = not match or not any(match.groups()) or size == 0
        if not invalid:
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                length = int(last)
                start = max(0, size - length)
                invalid = length == 0
            invalid |= start >= size or end < start
        partial = not invalid
    if invalid:
        file.close()
        response = HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
    else:
        response = FileResponse(
            FileSlice(file, start, end - start + 1) if partial else file,
            status=206 if partial else 200,
            as_attachment=request.GET.get("download") == "1",
            filename=Path(file.name).name,
            content_type=video_type or None,
        )
        response.block_size = 64 * 1024
        response["Content-Length"] = end - start + 1
        if partial:
            response["Content-Range"] = f"bytes {start}-{end}/{size}"
        if request.method == "HEAD":
            headers = dict(response.headers)
            response.close()
            response = HttpResponse(headers=headers)
    if video_type:
        response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
