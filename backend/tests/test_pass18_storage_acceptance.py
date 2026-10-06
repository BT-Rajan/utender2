"""PASS 18 -- file repository acceptance test: runs the IDENTICAL scenario
against LocalFileStorage and against S3Storage (moto-mocked, real botocore
signing/HTTP path, not just a call-recorder), proving the STORAGE_BACKEND
config switch changes nothing about caller-visible behavior.

Unlike the other test modules here, this one doesn't touch the FastAPI
app or the database at all -- it exercises the Storage classes directly
-- so `conftest.py`'s DB-isolation fixture is irrelevant to it, though
still harmless since it runs regardless.
"""
import shutil
import tempfile

import pytest

moto = pytest.importorskip("moto", reason="moto is a test-only dependency (see requirements-dev.txt)")


def run_acceptance_suite(storage, label, results, check, prefix_check_url=None):
    """The same battery of assertions, run against whatever Storage
    implementation is passed in. If the interface (and thus caller
    behavior) has genuinely stayed identical across backends, every
    assertion should hold true for BOTH."""
    bucket = "project-drawings"
    key = f"acceptance/{label}/plan.pdf"
    content = f"hello from {label}".encode()

    check(f"[{label}] exists() is False before anything is saved", storage.exists(bucket, key) is False)
    check(f"[{label}] download() returns None before anything is saved", storage.download(bucket, key) is None)

    storage.save(bucket, key, content, "application/pdf")
    check(f"[{label}] exists() is True after save()", storage.exists(bucket, key) is True)
    check(f"[{label}] download() returns exactly what was saved (byte-identical)", storage.download(bucket, key) == content)

    # Overwriting the same key with new content is a real replace, not an append.
    revised = f"revised content from {label}".encode()
    storage.save(bucket, key, revised, "application/pdf")
    check(f"[{label}] re-saving the same key replaces content (no append/corruption)", storage.download(bucket, key) == revised)

    url = storage.signed_url(bucket, key, expires_in=3600)
    check(f"[{label}] signed_url() returns a non-empty string", isinstance(url, str) and len(url) > 0)
    if prefix_check_url:
        prefix_check_url(url)

    # A second, unrelated key never collides with the first.
    other_key = f"acceptance/{label}/elevation.pdf"
    storage.save(bucket, other_key, b"a different file", "application/pdf")
    check(f"[{label}] two distinct keys stay independent", storage.download(bucket, other_key) == b"a different file")
    check(f"[{label}] first key is untouched by saving the second", storage.download(bucket, key) == revised)

    # delete() is idempotent-safe and only removes what's named.
    storage.delete(bucket, [key])
    check(f"[{label}] deleted key no longer exists", storage.exists(bucket, key) is False)
    check(f"[{label}] deleted key's content is gone", storage.download(bucket, key) is None)
    check(f"[{label}] the OTHER key survives a delete() naming only the first", storage.exists(bucket, other_key) is True)

    # Deleting a key that was never there doesn't raise.
    try:
        storage.delete(bucket, [f"acceptance/{label}/never-existed.pdf"])
        check(f"[{label}] delete() of a nonexistent key does not raise", True)
    except Exception as exc:  # noqa: BLE001
        check(f"[{label}] delete() of a nonexistent key does not raise", False)
        print("   ->", exc)

    # A separate bucket namespace (service-provider-documents) is independent of project-drawings.
    doc_bucket = "service-provider-documents"
    doc_key = f"acceptance/{label}/license.pdf"
    storage.save(doc_bucket, doc_key, b"license content", "application/pdf")
    check(f"[{label}] a different bucket has its own independent keyspace", storage.download(doc_bucket, doc_key) == b"license content")
    check(f"[{label}] a key that exists in one bucket does not exist under the same name in another", storage.exists(bucket, doc_key) is False)
    storage.delete(doc_bucket, [doc_key])

    storage.delete(bucket, [other_key])


def test_pass18_storage_acceptance():
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)

    # ---------- local backend ----------
    from app.services.storage import LocalFileStorage
    import app.config as config_module
    import app.services.storage as storage_module

    tmp_root = tempfile.mkdtemp(prefix="utender-storage-acceptance-")
    original_storage_root = storage_module.settings.storage_root
    storage_module.settings.storage_root = tmp_root
    storage_module._storage_instance = None
    local_storage = LocalFileStorage()

    def check_local_url(url):
        check("[local] signed_url() points at the local /files route", url.startswith(config_module.get_settings().api_url + "/files/"))
        check("[local] signed_url() carries an exp and sig query param", "exp=" in url and "sig=" in url)

    run_acceptance_suite(local_storage, "local", results, check, prefix_check_url=check_local_url)

    # Path traversal is still refused directly at the storage layer (defense in depth,
    # independent of the app-layer sanitization already covered in PASS 3).
    try:
        local_storage.save("project-drawings", "../../../etc/passwd", b"pwned", "text/plain")
        check("[local] direct path traversal attempt at the storage layer is refused", False)
    except ValueError:
        check("[local] direct path traversal attempt at the storage layer is refused", True)

    shutil.rmtree(tmp_root, ignore_errors=True)
    storage_module.settings.storage_root = original_storage_root

    # ---------- S3 backend (moto-mocked -- real botocore request signing/HTTP path) ----------
    from moto import mock_aws

    with mock_aws():
        import boto3

        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="project-drawings")
        client.create_bucket(Bucket="service-provider-documents")

        from app.services.storage import S3Storage

        s3_storage = S3Storage()

        def check_s3_url(url):
            check("[s3] signed_url() is a real presigned S3 URL, not a local /files link", "/files/" not in url)
            check("[s3] signed_url() targets the resolved bucket", "project-drawings" in url)

        run_acceptance_suite(s3_storage, "s3", results, check, prefix_check_url=check_s3_url)

        # S3_OBJECT_PREFIX actually changes the underlying key, config-only,
        # same as switching STORAGE_BACKEND itself requires no code change.
        # storage.py binds `settings = get_settings()` once at import time (by
        # design -- config is read once at process start, not hot-reloaded), so
        # simulating "a process started with this config value" means setting
        # the attribute directly rather than re-triggering an import that
        # already happened in this process.
        original_prefix = storage_module.settings.s3_object_prefix
        storage_module.settings.s3_object_prefix = "staging/"
        prefixed_storage = S3Storage()
        prefixed_storage.save("project-drawings", "prefix-test.pdf", b"prefixed", "application/pdf")
        raw = client.get_object(Bucket="project-drawings", Key="staging/prefix-test.pdf")
        check("[s3] S3_OBJECT_PREFIX is actually applied to the real underlying key", raw["Body"].read() == b"prefixed")
        check("[s3] exists() respects the same prefix it saved under", prefixed_storage.exists("project-drawings", "prefix-test.pdf") is True)
        storage_module.settings.s3_object_prefix = original_prefix

    # ---------- config-only switch: get_storage() picks the class purely from settings ----------
    storage_module._storage_instance = None
    storage_module.settings.storage_backend = "local"
    switch_root = tempfile.mkdtemp(prefix="utender-storage-switch-")
    storage_module.settings.storage_root = switch_root
    check("[switch] STORAGE_BACKEND=local resolves to LocalFileStorage", isinstance(storage_module.get_storage(), LocalFileStorage))

    storage_module._storage_instance = None
    storage_module.settings.storage_backend = "s3"
    with mock_aws():
        check("[switch] STORAGE_BACKEND=s3 resolves to S3Storage", isinstance(storage_module.get_storage(), S3Storage))
    storage_module._storage_instance = None
    storage_module.settings.storage_backend = "local"
    storage_module.settings.storage_root = original_storage_root
    shutil.rmtree(switch_root, ignore_errors=True)

    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)
