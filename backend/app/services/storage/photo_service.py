import os
import uuid
import logging
from io import BytesIO

import boto3
from PIL import Image

logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv("S3_BUCKET_NAME", "homescout-tours")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
THUMBNAIL_MAX_SIZE = (300, 300)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
PRESIGNED_URL_EXPIRY = 3600  # 1 hour

# Module-level S3 client (lazy init)
_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


class PhotoService:
    @staticmethod
    def upload_photo(file_data: bytes, content_type: str, user_id: str, tour_id: str) -> dict:
        """Upload photo + thumbnail to S3. Returns {s3_key, thumbnail_s3_key}."""
        # Validate
        if len(file_data) > MAX_FILE_SIZE:
            raise ValueError(f"File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB)")
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"Unsupported file type: {content_type}")

        ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]
        file_id = str(uuid.uuid4())
        s3_key = f"tours/{user_id}/{tour_id}/{file_id}.{ext}"
        thumb_key = f"tours/{user_id}/{tour_id}/thumbs/{file_id}.{ext}"

        s3 = _get_s3_client()

        # Upload original
        s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=file_data, ContentType=content_type)

        # Generate and upload thumbnail
        thumb_data = PhotoService._generate_thumbnail(file_data, content_type)
        s3.put_object(Bucket=S3_BUCKET, Key=thumb_key, Body=thumb_data, ContentType=content_type)

        return {"s3_key": s3_key, "thumbnail_s3_key": thumb_key}

    @staticmethod
    def _generate_thumbnail(file_data: bytes, content_type: str) -> bytes:
        """Generate a thumbnail image, max 300x300 maintaining aspect ratio."""
        img = Image.open(BytesIO(file_data))
        img.thumbnail(THUMBNAIL_MAX_SIZE)

        fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[content_type]
        buffer = BytesIO()
        img.save(buffer, format=fmt)
        return buffer.getvalue()

    @staticmethod
    def get_presigned_url(s3_key: str) -> str:
        """Generate a presigned GET URL for an S3 object."""
        s3 = _get_s3_client()
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key},
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )

    @staticmethod
    def delete_photo(s3_key: str, thumbnail_s3_key: str | None = None):
        """Delete photo (and thumbnail) from S3."""
        s3 = _get_s3_client()
        s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
        if thumbnail_s3_key:
            s3.delete_object(Bucket=S3_BUCKET, Key=thumbnail_s3_key)
