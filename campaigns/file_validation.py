"""Bounded, dependency-free container checks for newly uploaded deliverables."""
import re
import struct
import zlib
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError


VIDEO_TYPES = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"}
ALLOWED_EXTENSIONS = ("pdf", "docx", "jpg", "jpeg", "png", *VIDEO_TYPES)


def _read(file, start, length):
    file.seek(start)
    data = file.read(length)
    if len(data) != length:
        raise ValueError("Truncated file")
    return data


def _boxes(file, start, end):
    count = 0
    while start < end:
        count += 1
        if count > 50000:
            raise ValueError("Excessive box count")
        size, kind = struct.unpack(">I4s", _read(file, start, 8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", _read(file, start + 8, 8))[0]
            header = 16
        elif size == 0:
            size = end - start
        if size < header or start + size > end:
            raise ValueError("Invalid box size")
        yield kind, start + header, start + size
        start += size


def _isobmff(file, size, extension):
    boxes = list(_boxes(file, 0, size))
    brands, video, media, samples, description = set(), False, False, False, False
    for kind, start, end in boxes:
        if kind == b"ftyp":
            if end - start < 8 or end - start > 4096 or (end - start) % 4:
                raise ValueError("Invalid file type box")
            payload = _read(file, start, end - start)
            brands = {payload[:4], *(payload[i:i + 4] for i in range(8, len(payload), 4))}
        elif kind == b"mdat":
            media |= end > start
        elif kind in (b"moov", b"moof"):
            pending = [(start, end, 0)]
            while pending:
                first, last, depth = pending.pop()
                if depth > 8:
                    raise ValueError("Excessive nesting")
                for child, left, right in _boxes(file, first, last):
                    if child in (b"trak", b"mdia", b"minf", b"stbl", b"traf"):
                        pending.append((left, right, depth + 1))
                    elif child == b"hdlr" and depth == 2 and right - left >= 12:
                        video |= _read(file, left + 8, 4) == b"vide"
                    elif child == b"stsd" and depth == 4 and right - left >= 8:
                        for codec, first, last in _boxes(file, left + 8, right):
                            if last - first >= 78:
                                width, height = struct.unpack(">HH", _read(file, first + 24, 4))
                                description |= width > 0 and height > 0
                    elif child == b"stsz" and right - left >= 12:
                        samples |= int.from_bytes(_read(file, left + 8, 4), "big") > 0
                    elif child == b"trun" and right - left >= 8:
                        samples |= int.from_bytes(_read(file, left + 4, 4), "big") > 0
    if extension == "mov":
        brand_ok = b"qt  " in brands or (not brands and boxes and boxes[0][0] in (b"moov", b"mdat", b"wide"))
    else:
        brand_ok = bool(brands & {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"dash"}) and b"qt  " not in brands
    return brand_ok and video and media and samples and description


def _vint(file, offset, identifier=False):
    first = _read(file, offset, 1)[0]
    if not first:
        raise ValueError("Invalid EBML integer")
    length = 9 - first.bit_length()
    if length > (4 if identifier else 8):
        raise ValueError("Invalid EBML integer length")
    raw = int.from_bytes(_read(file, offset, length), "big")
    if identifier:
        return raw, length
    value = raw & ((1 << (7 * length)) - 1)
    return (None if value == (1 << (7 * length)) - 1 else value), length


def _elements(file, start, end):
    count = 0
    while start < end:
        count += 1
        if count > 50000:
            raise ValueError("Excessive element count")
        kind, id_length = _vint(file, start, True)
        size, size_length = _vint(file, start + id_length)
        left = start + id_length + size_length
        if size is None and kind not in (0x18538067, 0x1F43B675):
            raise ValueError("Unsupported unknown EBML size")
        right = end if size is None else left + size
        if right > end or left > right:
            raise ValueError("Truncated EBML element")
        yield kind, left, right
        start = right


def _webm(file, size):
    top = list(_elements(file, 0, size))
    if not top or top[0][0] != 0x1A45DFA3:
        return False
    doctype = False
    for kind, start, end in _elements(file, top[0][1], top[0][2]):
        if kind == 0x4282:
            doctype = end - start == 4 and _read(file, start, 4) == b"webm"
    video_tracks, block_tracks = set(), set()
    for kind, start, end in top:
        if kind != 0x18538067:
            continue
        for child, left, right in _elements(file, start, end):
            if child == 0x1654AE6B:
                for track, first, last in _elements(file, left, right):
                    if track != 0xAE:
                        continue
                    values = {}
                    for key, a, b in _elements(file, first, last):
                        if key in (0xD7, 0x83, 0x86):
                            if b - a > 64:
                                raise ValueError("Invalid track metadata")
                            values[key] = _read(file, a, b - a)
                        elif key == 0xE0:
                            for dimension, x, y in _elements(file, a, b):
                                if dimension in (0xB0, 0xBA) and 0 < y - x <= 8:
                                    values[dimension] = int.from_bytes(_read(file, x, y - x), "big")
                    if (values.get(0x83) == b"\x01" and values.get(0x86) in (b"V_VP8", b"V_VP9", b"V_AV1")
                            and values.get(0xB0) and values.get(0xBA)):
                        video_tracks.add(int.from_bytes(values.get(0xD7, b"\x00"), "big"))
            elif child == 0x1F43B675:
                pending = [(left, right)]
                while pending:
                    first, last = pending.pop()
                    for key, a, b in _elements(file, first, last):
                        if key in (0xA0, 0x1F43B675):
                            pending.append((a, b))
                        elif key in (0xA3, 0xA1):
                            number, length = _vint(file, a)
                            if b - a > length + 3:
                                block_tracks.add(number)
    return doctype and bool(video_tracks & block_tracks - {0, None})


def _pdf(file, size):
    if not re.match(rb"%PDF-[12]\.[0-9]", _read(file, 0, min(8, size))):
        return False
    tail = _read(file, max(0, size - 2048), min(2048, size))
    match = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*\Z", tail)
    if not match:
        return False
    offset = int(match[1])
    if offset >= size:
        return False
    target = _read(file, offset, min(80, size - offset))
    return target.startswith(b"xref") or bool(re.match(rb"\d+\s+\d+\s+obj", target))


def _docx(file, size):
    with ZipFile(file) as archive:
        names = archive.namelist()
        required = ("[Content_Types].xml", "_rels/.rels", "word/document.xml")
        if any(name not in names for name in required) or len(names) != len(set(names)):
            return False
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            return False
        roots = []
        for name in required:
            info = archive.getinfo(name)
            # Bound metadata parsing and reject encrypted or expansion-bomb archives.
            if info.file_size > 20 * 1024 * 1024 or info.flag_bits & 1:
                return False
            xml = archive.read(name)
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                return False
            roots.append(ElementTree.fromstring(xml))
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        return (any(node.get("PartName") == "/word/document.xml" and node.get("ContentType") == content_type for node in roots[0])
                and roots[2].tag == "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document")


def _png(file, size):
    if _read(file, 0, min(8, size)) != b"\x89PNG\r\n\x1a\n":
        return False
    position, header, pixels = 8, False, False
    while position < size:
        length, kind = struct.unpack(">I4s", _read(file, position, 8))
        if position + 12 + length > size:
            return False
        crc = zlib.crc32(kind)
        for offset in range(0, length, 65536):
            crc = zlib.crc32(_read(file, position + 8 + offset, min(65536, length - offset)), crc)
        if crc != int.from_bytes(_read(file, position + 8 + length, 4), "big"):
            return False
        if position == 8:
            if kind != b"IHDR" or length != 13:
                return False
            width, height = struct.unpack(">II", _read(file, position + 8, 8))
            header = width > 0 and height > 0
        pixels |= kind == b"IDAT" and length > 0
        position += length + 12
        if kind == b"IEND":
            return header and pixels and length == 0 and position == size
    return False


def _jpeg(file, size):
    if _read(file, 0, min(size, 2)) != b"\xff\xd8" or _read(file, max(0, size - 2), min(size, 2)) != b"\xff\xd9":
        return False
    position, dimensions = 2, False
    while position < size - 2:
        marker = _read(file, position, 2)
        if marker[0] != 255:
            return False
        if marker[1] == 255:
            position += 1
            continue
        length = int.from_bytes(_read(file, position + 2, 2), "big")
        if length < 2 or position + 2 + length > size:
            return False
        if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC9, 0xCA, 0xCB) and length >= 8:
            height, width = struct.unpack(">HH", _read(file, position + 5, 4))
            dimensions = width > 0 and height > 0
        if marker[1] == 0xDA:
            return dimensions and position + 2 + length < size - 2
        position += 2 + length
    return False


def validate_deliverable_content(file):
    # Historical stored files are not rewritten/revalidated by metadata edits.
    if getattr(file, "_committed", False):
        return
    extension = Path(file.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError("Unsupported file type.")
    position = file.tell()
    try:
        file.seek(0, 2)
        size = file.tell()
        if extension in VIDEO_TYPES and size > settings.DELIVERABLE_VIDEO_MAX_BYTES:
            raise ValidationError("Video files cannot exceed %(limit)s MB.", params={"limit": settings.DELIVERABLE_VIDEO_MAX_BYTES // (1024 * 1024)})
        checks = {"pdf": _pdf, "docx": _docx, "png": _png, "jpg": _jpeg, "jpeg": _jpeg, "webm": _webm}
        valid = _isobmff(file, size, extension) if extension in ("mp4", "mov") else checks[extension](file, size)
        if not valid:
            raise ValueError("Content does not match the extension")
    except (ValueError, OSError, struct.error, BadZipFile, ElementTree.ParseError, RuntimeError, OverflowError) as error:
        raise ValidationError("The file content is invalid or does not match its extension.") from error
    finally:
        file.seek(position)
