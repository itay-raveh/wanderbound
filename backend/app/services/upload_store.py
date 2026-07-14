from typing import Any, BinaryIO, TypedDict

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings


class ProviderPart(TypedDict):
    PartNumber: int
    Size: int
    ETag: str


class CompletionPart(TypedDict):
    PartNumber: int
    ETag: str


class UploadStoreError(RuntimeError):
    def __init__(self, code: str = "ProviderError") -> None:
        super().__init__("upload store operation failed")
        self.code = code


class UploadStoreService:
    def __init__(
        self,
        internal_client: Any,
        signing_client: Any,
        *,
        bucket: str,
        presign_ttl: int,
    ) -> None:
        self.internal_client = internal_client
        self.signing_client = signing_client
        self._bucket = bucket
        self._presign_ttl = presign_ttl

    def _run(self, method: Any, **params: Any) -> dict[str, Any]:
        try:
            return method(**params)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "ProviderError"))
            raise UploadStoreError(code) from None
        except BotoCoreError:
            raise UploadStoreError from None

    def create(self, key: str, content_type: str) -> str:
        response = self._run(
            self.internal_client.create_multipart_upload,
            Bucket=self._bucket,
            Key=key,
            ContentType=content_type,
        )
        return str(response["UploadId"])

    def sign_part(
        self,
        key: str,
        provider_upload_id: str,
        part_number: int,
        content_length: int,
    ) -> str:
        try:
            return self.signing_client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "UploadId": provider_upload_id,
                    "PartNumber": part_number,
                    "ContentLength": content_length,
                },
                ExpiresIn=self._presign_ttl,
                HttpMethod="PUT",
            )
        except BotoCoreError, ClientError:
            raise UploadStoreError from None

    def list_parts(self, key: str, provider_upload_id: str) -> list[ProviderPart]:
        response = self._run(
            self.internal_client.list_parts,
            Bucket=self._bucket,
            Key=key,
            UploadId=provider_upload_id,
        )
        return [
            ProviderPart(
                PartNumber=int(part["PartNumber"]),
                Size=int(part["Size"]),
                ETag=str(part["ETag"]),
            )
            for part in response.get("Parts", [])
        ]

    def complete(
        self, key: str, provider_upload_id: str, parts: list[CompletionPart]
    ) -> None:
        self._run(
            self.internal_client.complete_multipart_upload,
            Bucket=self._bucket,
            Key=key,
            UploadId=provider_upload_id,
            MultipartUpload={"Parts": parts},
        )

    def head(self, key: str) -> int:
        response = self._run(
            self.internal_client.head_object, Bucket=self._bucket, Key=key
        )
        return int(response["ContentLength"])

    def abort(self, key: str, provider_upload_id: str) -> None:
        try:
            self._run(
                self.internal_client.abort_multipart_upload,
                Bucket=self._bucket,
                Key=key,
                UploadId=provider_upload_id,
            )
        except UploadStoreError as exc:
            if exc.code != "NoSuchUpload":
                raise

    def download(self, key: str, target: BinaryIO) -> int:
        response = self._run(
            self.internal_client.get_object, Bucket=self._bucket, Key=key
        )
        body = response["Body"]
        written = 0
        try:
            while chunk := body.read(1024 * 1024):
                target.write(chunk)
                written += len(chunk)
        finally:
            body.close()
        return written

    def delete(self, key: str) -> None:
        try:
            self._run(self.internal_client.delete_object, Bucket=self._bucket, Key=key)
        except UploadStoreError as exc:
            if exc.code != "NoSuchKey":
                raise

    def close(self) -> None:
        self.internal_client.close()
        self.signing_client.close()


def build_upload_store(settings: Settings) -> UploadStoreService:
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": settings.UPLOAD_S3_ADDRESSING_STYLE},
    )
    common = {
        "region_name": settings.UPLOAD_S3_REGION,
        "aws_access_key_id": settings.UPLOAD_S3_ACCESS_KEY_ID,
        "aws_secret_access_key": (
            settings.UPLOAD_S3_SECRET_ACCESS_KEY.get_secret_value()
        ),
        "config": config,
    }
    internal = boto3.client(
        "s3", endpoint_url=str(settings.UPLOAD_S3_INTERNAL_ENDPOINT_URL), **common
    )
    signing = boto3.client(
        "s3", endpoint_url=str(settings.UPLOAD_S3_PUBLIC_ENDPOINT_URL), **common
    )
    return UploadStoreService(
        internal,
        signing,
        bucket=settings.UPLOAD_S3_BUCKET,
        presign_ttl=settings.UPLOAD_S3_PRESIGN_TTL_SECONDS,
    )
