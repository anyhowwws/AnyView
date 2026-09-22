"""Where uploaded files live. One Cloud Storage bucket, one prefix per user.

The browser never sends a file to the API: it asks for a signed URL and PUTs
the bytes straight to the bucket (ADR 0010). The API only ever reads an object
back, and only one under the calling user's own prefix.

`UploadStore` is the small surface the rest of the app depends on;
`GcsUploadStore` is the real one, `MemoryUploadStore` is for tests and the
fake-model local run.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Protocol

log = logging.getLogger(__name__)

SIGNED_URL_TTL = dt.timedelta(minutes=15)  # keep in step with extract.SIGNED_URL_TTL_SECONDS


class UploadStore(Protocol):
    def signed_put_url(self, object_name: str, content_type: str) -> str: ...

    def read(self, object_name: str) -> bytes | None:
        """The object's bytes, or None if it does not exist."""
        ...


class GcsUploadStore:
    def __init__(self, *, bucket: str, signer_service_account: str) -> None:
        if not bucket:
            raise RuntimeError("UPLOAD_BUCKET is required for resume uploads")
        # Imported here so importing the app never touches GCP (tests, --help).
        import google.auth
        from google.auth.transport.requests import Request
        from google.cloud import storage

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)
        self._signer = signer_service_account
        self._credentials, _ = google.auth.default()
        self._refresh = Request()

    def _access_token(self) -> str:
        # A V4 signature needs a private key. Neither Cloud Run's metadata
        # credentials nor a developer's ADC have one, so the library asks the
        # IAM signBlob API to sign as `self._signer` using this access token.
        # The caller therefore needs iam.serviceAccounts.signBlob on that SA:
        # the SA on itself in production, the owner locally.
        if not self._credentials.valid:
            self._credentials.refresh(self._refresh)
        return self._credentials.token

    def signed_put_url(self, object_name: str, content_type: str) -> str:
        blob = self._bucket.blob(object_name)
        return blob.generate_signed_url(
            version="v4",
            expiration=SIGNED_URL_TTL,
            method="PUT",
            content_type=content_type,
            service_account_email=self._signer,
            access_token=self._access_token(),
        )

    def read(self, object_name: str) -> bytes | None:
        blob = self._bucket.blob(object_name)
        if not blob.exists():
            return None
        return blob.download_as_bytes()


class MemoryUploadStore:
    """Holds bytes in a dict. `signed_put_url` returns a fake URL; tests and the
    local fake run put bytes in with `put()` directly."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def signed_put_url(self, object_name: str, content_type: str) -> str:
        # Relative on purpose: there is no bucket to PUT to, so the browser
        # sends the bytes back to the API's own fake-mode route instead. The
        # frontend resolves a leading "/" against the API base.
        return f"/uploads/memory/{object_name}"

    def put(self, object_name: str, data: bytes) -> None:
        self.objects[object_name] = data

    def read(self, object_name: str) -> bytes | None:
        return self.objects.get(object_name)
