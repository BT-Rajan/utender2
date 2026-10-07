from fastapi import APIRouter, HTTPException, Response

from app.services.storage import LocalFileStorage, content_headers, get_storage

router = APIRouter(tags=["files"])


# Only meaningful when STORAGE_BACKEND=local — S3 presigned URLs point
# straight at S3 and never touch this route. Verifies the same HMAC scheme
# LocalFileStorage.signed_url() generates, so a local "signed URL" behaves
# like a real one: it expires, and it can't be forged without the secret.
@router.get("/files/{bucket}/{key:path}")
def serve_file(bucket: str, key: str, exp: int, sig: str, name: str | None = None):
    if not LocalFileStorage.verify(bucket, key, exp, sig, name):
        raise HTTPException(status_code=403, detail="Link expired or invalid")

    storage = get_storage()
    content = storage.download(bucket, key)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")

    # Stage 4.6: under its real name -- PDFs and images shown in place, other
    # types downloaded -- never sniffed into something else, never cached.
    media, disposition = content_headers(name, key)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": disposition, "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )
