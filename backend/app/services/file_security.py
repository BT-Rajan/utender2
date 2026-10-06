import re
import uuid

from fastapi import HTTPException

_UNSAFE_CHARS = re.compile(r"[^a-zA-Z0-9._-]")

ALLOWED_DRAWING_EXTENSIONS = {"pdf", "dwg", "jpg", "jpeg", "png", "zip"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def assert_allowed_extension(filename: str, allowed: set[str]) -> None:
    ext = _extension(filename)
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"'.{ext or filename}' is not an allowed file type. Allowed: {', '.join(sorted(allowed))}.",
        )


# Storage paths can't safely contain arbitrary characters from a user- or
# zip-supplied filename — keep the slashes (subfolders) but strip anything
# else that could break a path segment. Critically, "." and "-" are both
# in the allowed character set, so a naive character filter alone lets a
# ".." segment straight through unchanged — this drops "." and ".."
# segments outright (not just filters their characters) so a filename or
# zip entry named "../../../etc/passwd" can never resolve outside
# STORAGE_ROOT. Spec §69-70.
# The name shown to users and used as the member name in the "download all
# drawings" zip. Unlike sanitize_path_segment this keeps the characters people
# actually use in file names (spaces, accents) -- it only removes what makes a
# name dangerous: parent-directory and "." segments, absolute/drive-letter
# prefixes, backslash separators and control characters. A zip entry named
# "../../x.pdf" or "/etc/x.pdf" would otherwise be written verbatim into the
# archive handed to service providers, where a naive extractor honours the path.
def safe_relative_name(name: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f]", "", name)
    parts = [p for p in re.split(r"[\\/]+", cleaned) if p not in ("", ".", "..")]
    if parts and re.fullmatch(r"[A-Za-z]:", parts[0]):
        parts = parts[1:]
    return "/".join(parts) or f"file-{uuid.uuid4().hex[:8]}"


def sanitize_path_segment(name: str) -> str:
    parts = [_UNSAFE_CHARS.sub("_", part) for part in name.split("/") if part not in ("", ".", "..")]
    return "/".join(parts) or f"file-{uuid.uuid4().hex[:8]}"
