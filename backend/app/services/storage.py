import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import get_settings

settings = get_settings()

# Drawings must stay accessible for exactly as long as the owner said
# bidding is open — not an arbitrary short-lived link. Expiry is tied to
# the project's bid_deadline (plus a small buffer so a service provider mid-review
# right at the deadline doesn't get cut off). Ported verbatim from
# src/lib/storage.ts.
ONE_HOUR = 60 * 60
NINETY_DAYS = 60 * 60 * 24 * 90
POST_DEADLINE_BUFFER = 60 * 15  # 15 minutes grace after the deadline


def drawing_url_expiry_seconds(bid_deadline) -> int:
    """Stage 4.6: a requirement document link lasts an hour (less when the
    deadline's grace ends sooner, but never under 15 minutes). Links are
    issued afresh every time the requirement is read, by someone authorized
    to read it then; so a link that's passed on, or kept after access ends
    (a lapsed qualification, a requirement that ended), stops working within
    the hour instead of lasting until the deadline."""
    seconds_remaining = int((bid_deadline.timestamp() + POST_DEADLINE_BUFFER) - time.time())
    return max(min(seconds_remaining, DOCUMENT_LINK_SECONDS), MIN_DOCUMENT_LINK_SECONDS)


DOCUMENT_LINK_SECONDS = ONE_HOUR
MIN_DOCUMENT_LINK_SECONDS = 60 * 15

# File types a browser may show in place (Stage 4.6); everything else is
# offered as a download under its real name.
INLINE_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


def content_headers(filename: str | None, key: str) -> tuple[str, str]:
    """(media type, Content-Disposition) for serving a stored file under its
    real name: inline for PDFs and images, an attachment otherwise."""
    from urllib.parse import quote

    name = (filename or key.rsplit("/", 1)[-1]).replace("\r", "").replace("\n", "").replace('"', "")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    media = INLINE_TYPES.get(ext, "application/octet-stream")
    disposition = "inline" if ext in INLINE_TYPES else "attachment"
    ascii_name = name.encode("ascii", "replace").decode().replace("?", "_")
    return media, f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"



class Storage(ABC):
    @abstractmethod
    def save(self, bucket: str, key: str, content: bytes, content_type: str) -> None: ...

    @abstractmethod
    def signed_url(self, bucket: str, key: str, expires_in: int, filename: str | None = None) -> str: ...

    @abstractmethod
    def download(self, bucket: str, key: str) -> bytes | None: ...

    @abstractmethod
    def delete(self, bucket: str, keys: list[str]) -> None: ...

    @abstractmethod
    def exists(self, bucket: str, key: str) -> bool: ...


class LocalFileStorage(Storage):
    """Files on disk under STORAGE_ROOT. 'Signed' URLs are an HMAC-signed
    path + expiry, verified by the /files route in app/routers/files.py —
    same calling convention and expiry semantics as the S3 backend, so
    switching STORAGE_BACKEND never changes any caller."""

    def __init__(self) -> None:
        self.root = Path(settings.storage_root).resolve()

    def _path(self, bucket: str, key: str) -> Path:
        # Defense in depth: callers (drawings.py, service_provider.py routers)
        # already strip ".."/"."" path segments before a key ever reaches
        # here, but storage itself never trusts that alone — resolve the
        # final path and refuse anything that would land outside root,
        # the way the "app-layer + a second independent check" pattern is
        # used everywhere else in this codebase (see storage-boundary note
        # in the architecture diagram this app was designed from).
        candidate = (self.root / bucket / key).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise ValueError(f"Refusing to access path outside storage root: {bucket}/{key}")
        return candidate

    def save(self, bucket: str, key: str, content: bytes, content_type: str) -> None:
        path = self._path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def signed_url(self, bucket: str, key: str, expires_in: int, filename: str | None = None) -> str:
        from urllib.parse import quote

        expires_at = int(time.time()) + expires_in
        signature = self._sign(bucket, key, expires_at, filename)
        name = f"&name={quote(filename)}" if filename else ""
        return f"{settings.api_url}/files/{bucket}/{key}?exp={expires_at}&sig={signature}{name}"

    def download(self, bucket: str, key: str) -> bytes | None:
        path = self._path(bucket, key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def delete(self, bucket: str, keys: list[str]) -> None:
        for key in keys:
            path = self._path(bucket, key)
            path.unlink(missing_ok=True)

    def exists(self, bucket: str, key: str) -> bool:
        return self._path(bucket, key).is_file()

    @staticmethod
    def _sign(bucket: str, key: str, expires_at: int, name: str | None = None) -> str:
        # The download name, when given, is signed too: a link can't be
        # re-labelled to make one file pass for another.
        message = f"{bucket}:{key}:{expires_at}" + (f":{name}" if name else "")
        return hmac.new(settings.storage_signing_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    @classmethod
    def verify(cls, bucket: str, key: str, expires_at: int, signature: str, name: str | None = None) -> bool:
        if time.time() > expires_at:
            return False
        expected = cls._sign(bucket, key, expires_at, name)
        return hmac.compare_digest(expected, signature)


class S3Storage(Storage):
    """boto3 presigned URLs. Works against real S3 or an S3-compatible
    endpoint (e.g. MinIO) via S3_ENDPOINT_URL for local dev parity."""

    def __init__(self) -> None:
        import boto3

        self._client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

    def _resolve_bucket(self, bucket: str) -> str:
        return {
            "project-drawings": settings.s3_bucket_drawings,
            "service-provider-documents": settings.s3_bucket_documents,
            "owner-documents": settings.s3_bucket_owner_documents,
            # Stage 3.8 response attachments share the documents bucket; their
            # keys are namespaced by project and provider.
            "offer-documents": settings.s3_bucket_documents,
            # Stage 4.7 follow-up: files on questions and answers, keyed by
            # project and question.
            "clarification-documents": settings.s3_bucket_documents,
        }.get(bucket, bucket)

    def _resolve_key(self, key: str) -> str:
        return f"{settings.s3_object_prefix}{key}" if settings.s3_object_prefix else key

    def save(self, bucket: str, key: str, content: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._resolve_bucket(bucket), Key=self._resolve_key(key), Body=content, ContentType=content_type
        )

    def signed_url(self, bucket: str, key: str, expires_in: int, filename: str | None = None) -> str:
        params = {"Bucket": self._resolve_bucket(bucket), "Key": self._resolve_key(key)}
        if filename:  # S3 serves it under its real name and type, as the local route does
            media, disposition = content_headers(filename, key)
            params.update(ResponseContentType=media, ResponseContentDisposition=disposition)
        return self._client.generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)

    def download(self, bucket: str, key: str) -> bytes | None:
        try:
            obj = self._client.get_object(Bucket=self._resolve_bucket(bucket), Key=self._resolve_key(key))
        except self._client.exceptions.NoSuchKey:
            return None
        except Exception:
            return None
        return obj["Body"].read()

    def delete(self, bucket: str, keys: list[str]) -> None:
        if not keys:
            return
        real_bucket = self._resolve_bucket(bucket)
        objects = [{"Key": self._resolve_key(k)} for k in keys]
        self._client.delete_objects(Bucket=real_bucket, Delete={"Objects": objects})

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._resolve_bucket(bucket), Key=self._resolve_key(key))
            return True
        except Exception:
            return False


_storage_instance: Storage | None = None


def get_storage() -> Storage:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = S3Storage() if settings.storage_backend == "s3" else LocalFileStorage()
    return _storage_instance
