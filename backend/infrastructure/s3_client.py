"""
AWS S3 client for Butler object storage.

Production-grade object storage with:
- Tenant-scoped buckets
- Lifecycle policies
- Encryption at rest
- Versioning
- Presigned URLs
"""

from typing import Any

import boto3
import structlog
from botocore.exceptions import ClientError
from redis.asyncio import Redis

from infrastructure.config import settings

logger = structlog.get_logger(__name__)


class S3Client:
    """AWS S3 client wrapper for object storage."""

    def __init__(
        self,
        redis: Redis | None = None,
        bucket_name: str | None = None,
    ):
        """
        Initialize S3 client.

        Args:
            redis: Optional Redis client for caching
            bucket_name: S3 bucket name (default: butler-<environment>)
        """
        self._redis = redis
        self._bucket_name = bucket_name or f"butler-{settings.ENVIRONMENT}"
        self._client = None
        self._region_name = settings.AWS_REGION

    def _get_client(self) -> Any:
        """Lazy initialization of boto3 S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                region_name=self._region_name,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
        return self._client

    def _get_object_key(self, tenant_id: str, object_key: str) -> str:
        """
        Generate S3 object key with tenant prefix.

        Args:
            tenant_id: Tenant ID
            object_key: Original object key

        Returns:
            Full S3 object key with tenant prefix
        """
        return f"tenants/{tenant_id}/{object_key}"

    async def put_object(
        self,
        tenant_id: str,
        object_key: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """
        Upload an object to S3.

        Args:
            tenant_id: Tenant ID
            object_key: Object key
            data: Object data
            content_type: Content type
            metadata: Optional metadata

        Returns:
            Object URL
        """
        try:
            client = self._get_client()
            full_key = self._get_object_key(tenant_id, object_key)

            params = {
                "Bucket": self._bucket_name,
                "Key": full_key,
                "Body": data,
            }

            if content_type:
                params["ContentType"] = content_type

            if metadata:
                params["Metadata"] = metadata

            client.put_object(**params)

            url = f"s3://{self._bucket_name}/{full_key}"

            logger.info(
                "object_uploaded",
                tenant_id=tenant_id,
                object_key=object_key,
                content_type=content_type,
                url=url,
            )

            return url

        except ClientError as e:
            logger.exception(
                "object_upload_failed",
                tenant_id=tenant_id,
                object_key=object_key,
                error=str(e),
            )
            raise S3Error(f"Failed to upload object: {object_key}")

    async def get_object(
        self,
        tenant_id: str,
        object_key: str,
    ) -> tuple[bytes, dict[str, str] | None]:
        """
        Download an object from S3.

        Args:
            tenant_id: Tenant ID
            object_key: Object key

        Returns:
            Tuple of (object data, metadata)
        """
        try:
            client = self._get_client()
            full_key = self._get_object_key(tenant_id, object_key)

            response = client.get_object(
                Bucket=self._bucket_name,
                Key=full_key,
            )

            data = response["Body"].read()
            metadata = response.get("Metadata", {})

            logger.debug(
                "object_downloaded",
                tenant_id=tenant_id,
                object_key=object_key,
            )

            return data, metadata

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "NoSuchKey":
                logger.error(
                    "object_not_found",
                    tenant_id=tenant_id,
                    object_key=object_key,
                )
                raise S3NotFoundError(f"Object not found: {object_key}")

            logger.exception(
                "object_download_failed",
                tenant_id=tenant_id,
                object_key=object_key,
                error=str(e),
            )
            raise S3Error(f"Failed to download object: {object_key}")

    async def delete_object(
        self,
        tenant_id: str,
        object_key: str,
    ) -> None:
        """
        Delete an object from S3.

        Args:
            tenant_id: Tenant ID
            object_key: Object key
        """
        try:
            client = self._get_client()
            full_key = self._get_object_key(tenant_id, object_key)

            client.delete_object(
                Bucket=self._bucket_name,
                Key=full_key,
            )

            logger.info(
                "object_deleted",
                tenant_id=tenant_id,
                object_key=object_key,
            )

        except ClientError as e:
            logger.exception(
                "object_deletion_failed",
                tenant_id=tenant_id,
                object_key=object_key,
                error=str(e),
            )
            raise S3Error(f"Failed to delete object: {object_key}")

    async def generate_presigned_url(
        self,
        tenant_id: str,
        object_key: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a presigned URL for an object.

        Args:
            tenant_id: Tenant ID
            object_key: Object key
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL
        """
        try:
            client = self._get_client()
            full_key = self._get_object_key(tenant_id, object_key)

            url = client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket_name,
                    "Key": full_key,
                },
                ExpiresIn=expires_in,
            )

            logger.debug(
                "presigned_url_generated",
                tenant_id=tenant_id,
                object_key=object_key,
                expires_in=expires_in,
            )

            return url

        except ClientError as e:
            logger.exception(
                "presigned_url_generation_failed",
                tenant_id=tenant_id,
                object_key=object_key,
                error=str(e),
            )
            raise S3Error(f"Failed to generate presigned URL: {object_key}")

    async def list_objects(
        self,
        tenant_id: str,
        prefix: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        List objects for a tenant.

        Args:
            tenant_id: Tenant ID
            prefix: Optional prefix filter
            limit: Maximum number of objects to return

        Returns:
            List of object metadata
        """
        try:
            client = self._get_client()
            tenant_prefix = f"tenants/{tenant_id}/"

            full_prefix = f"{tenant_prefix}{prefix}" if prefix else tenant_prefix

            response = client.list_objects_v2(
                Bucket=self._bucket_name,
                Prefix=full_prefix,
                MaxKeys=limit,
            )

            objects = []
            if "Contents" in response:
                for obj in response["Contents"]:
                    objects.append(
                        {
                            "key": obj["Key"],
                            "size": obj["Size"],
                            "last_modified": obj["LastModified"],
                            "etag": obj["ETag"],
                        }
                    )

            logger.debug(
                "objects_listed",
                tenant_id=tenant_id,
                prefix=prefix,
                count=len(objects),
            )

            return objects

        except ClientError as e:
            logger.exception(
                "object_listing_failed",
                tenant_id=tenant_id,
                prefix=prefix,
                error=str(e),
            )
            raise S3Error(f"Failed to list objects: {prefix}")

    async def create_bucket_if_not_exists(self) -> None:
        """Create the bucket if it doesn't exist."""
        try:
            client = self._get_client()

            try:
                client.head_bucket(Bucket=self._bucket_name)
                logger.info("bucket_exists", bucket_name=self._bucket_name)
            except ClientError as e:
                error_code = e.response["Error"]["Code"]

                if error_code == "404" or error_code == "NoSuchBucket":
                    # Create bucket
                    if self._region_name == "us-east-1":
                        client.create_bucket(Bucket=self._bucket_name)
                    else:
                        client.create_bucket(
                            Bucket=self._bucket_name,
                            CreateBucketConfiguration={
                                "LocationConstraint": self._region_name,
                            },
                        )

                    # Enable versioning
                    client.put_bucket_versioning(
                        Bucket=self._bucket_name,
                        VersioningConfiguration={
                            "Status": "Enabled",
                        },
                    )

                    # Enable encryption
                    client.put_bucket_encryption(
                        Bucket=self._bucket_name,
                        ServerSideEncryptionConfiguration={
                            "Rules": [
                                {
                                    "ApplyServerSideEncryptionByDefault": {
                                        "SSEAlgorithm": "AES256",
                                    },
                                },
                            ],
                        },
                    )

                    logger.info(
                        "bucket_created",
                        bucket_name=self._bucket_name,
                        region=self._region_name,
                    )
                else:
                    raise

        except ClientError as e:
            logger.exception(
                "bucket_creation_failed",
                bucket_name=self._bucket_name,
                error=str(e),
            )
            raise S3Error(f"Failed to create bucket: {self._bucket_name}")


class S3Error(Exception):
    """Base exception for S3 errors."""


class S3NotFoundError(S3Error):
    """Raised when an object is not found."""
