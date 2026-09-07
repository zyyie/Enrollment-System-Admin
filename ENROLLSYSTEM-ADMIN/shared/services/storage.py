"""Supabase Storage helpers for admission documents."""

import mimetypes
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ADMISSION_BUCKET = "admission-documents"
ENROLLMENT_BUCKET = "enrollment-photos"


def _guess_content_type(filename):
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def storage_object_path(application_id, field, filename):
    safe_name = re.sub(r"[^\w.\-]", "_", Path(filename).name) or f"{field}.bin"
    return f"{application_id}/{field}_{safe_name}"


def enrollment_photo_path(student_id, photo_type, filename):
    safe_name = re.sub(r"[^\w.\-]", "_", Path(filename).name) or f"{photo_type}.jpg"
    return f"{student_id}/{photo_type}_{safe_name}"


def upload_enrollment_photo(supabase_url, secret_key, student_id, photo_type, filename, content):
    if not supabase_url or not secret_key:
        return None, "Supabase storage not configured"

    object_path = enrollment_photo_path(student_id, photo_type, filename)
    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{ENROLLMENT_BUCKET}/{object_path}"
    request = Request(
        url,
        data=content,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "apikey": secret_key,
            "Content-Type": _guess_content_type(filename),
            "x-upsert": "true",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            response.read()
        return object_path, None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        return None, detail or err.reason
    except URLError as err:
        return None, str(err.reason)


def public_enrollment_photo_url(supabase_url, object_path):
    if not supabase_url or not object_path:
        return None
    path = str(object_path).replace("\\", "/").lstrip("/")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{ENROLLMENT_BUCKET}/{path}"


def upload_admission_document(supabase_url, secret_key, application_id, field, filename, content):
    if not supabase_url or not secret_key:
        return None, "Supabase storage not configured"

    object_path = storage_object_path(application_id, field, filename)
    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{ADMISSION_BUCKET}/{object_path}"
    request = Request(
        url,
        data=content,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "apikey": secret_key,
            "Content-Type": _guess_content_type(filename),
            "x-upsert": "true",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            response.read()
        return object_path, None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        return None, detail or err.reason
    except URLError as err:
        return None, str(err.reason)


def upload_admission_files_to_supabase(supabase_url, secret_key, application_id, files, local_paths):
    if not supabase_url or not secret_key:
        return dict(local_paths)

    stored = dict(local_paths)
    for field, info in files.items():
        if field not in stored:
            continue
        object_path, error = upload_admission_document(
            supabase_url,
            secret_key,
            application_id,
            field,
            info.get("filename") or f"{field}.bin",
            info.get("content") or b"",
        )
        if object_path:
            stored[field] = object_path
        elif error:
            print(f"[Storage upload failed] {field}: {error}")
    return stored


def public_document_url(supabase_url, object_path):
    if not supabase_url or not object_path:
        return None
    path = str(object_path).replace("\\", "/").lstrip("/")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("uploads/"):
        return None
    return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{ADMISSION_BUCKET}/{path}"


def resolve_document_view_url(path, *, supabase_url="", student_portal_url="http://localhost:8000"):
    if not path:
        return None

    path = str(path).replace("\\", "/").strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path

    public_url = public_document_url(supabase_url, path)
    if public_url:
        return public_url

    if path.startswith("uploads/"):
        return f"/api/admission/file?path={quote(path, safe='')}"

    return f"/api/admission/file?path={quote(path, safe='')}"


def admin_document_view_url(path):
    """Always route admin document views through the local file proxy."""
    if not path:
        return None
    path = str(path).replace("\\", "/").strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("/api/admission/file"):
        return path
    return f"/api/admission/file?path={quote(path, safe='')}"


def fetch_admission_storage_object(supabase_url, secret_key, object_path):
    if not supabase_url or not secret_key or not object_path:
        return None, None

    path = str(object_path).replace("\\", "/").lstrip("/")
    if path.startswith("uploads/"):
        return None, None

    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{ADMISSION_BUCKET}/{path}"
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "apikey": secret_key,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read(), path.split("/")[-1]
    except HTTPError:
        return None, None
    except URLError:
        return None, None


def find_local_document_by_basename(filename, local_roots):
    if not filename:
        return None

    safe_name = Path(str(filename).replace("\\", "/")).name
    if not safe_name or ".." in safe_name:
        return None

    for root in local_roots:
        admissions_dir = Path(root).resolve() / "uploads" / "admissions"
        if not admissions_dir.is_dir():
            continue
        for app_dir in admissions_dir.iterdir():
            if not app_dir.is_dir():
                continue
            candidate = app_dir / safe_name
            if candidate.is_file():
                return candidate
            for item in app_dir.iterdir():
                if item.is_file() and item.name == safe_name:
                    return item
    return None


def load_admission_file_content(file_path, *, local_roots, supabase_url="", secret_key=""):
    """Resolve admission files from local disk, Supabase storage, or fuzzy local match."""
    normalized = str(file_path or "").replace("\\", "/").strip()
    if not normalized:
        return None, None, None

    local_file = find_local_document(normalized, local_roots)
    if local_file:
        return local_file.read_bytes(), local_file.name, local_file

    content, filename = fetch_admission_storage_object(supabase_url, secret_key, normalized)
    if content is not None:
        return content, filename or normalized.split("/")[-1], None

    basename = normalized.split("/")[-1]
    fuzzy = find_local_document_by_basename(basename, local_roots)
    if fuzzy:
        return fuzzy.read_bytes(), fuzzy.name, fuzzy

    return None, None, None


def find_local_document(path, local_roots):
    if not path:
        return None

    normalized = str(path).replace("\\", "/").lstrip("/")
    if ".." in normalized.split("/"):
        return None

    for root in local_roots:
        root_path = Path(root).resolve()
        candidate = (root_path / normalized).resolve()
        try:
            candidate.relative_to(root_path)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None
