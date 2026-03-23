"""
S3 service for caching apartment listing images.
Downloads images from external sources and stores them in S3.
"""
import os
import hashlib
import logging
import mimetypes
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class S3Service:
    """
    Service for caching images in AWS S3.

    Features:
    - Download images from external URLs
    - Store with consistent naming (hash-based)
    - Generate CloudFront/S3 URLs
    - Cleanup old cached images
    """

    def __init__(self):
        """Initialize the S3 service."""
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "snugd-images")
        self.region = os.getenv("AWS_REGION", "us-west-2")
        self.cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")

        # Check for boto3 availability
        self._boto3 = None
        self._s3_client = None
        self._load_boto3()

        self._http_client = None

    def _load_boto3(self):
        """Load boto3 if available."""
        try:
            import boto3
            self._boto3 = boto3
            self._s3_client = boto3.client(
                "s3",
                region_name=self.region,
            )
            logger.info("S3 service initialized successfully")
        except ImportError:
            logger.warning("boto3 not installed - S3 caching disabled")
        except Exception as e:
            logger.warning(f"Could not initialize S3 client: {e}")

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._http_client

    @property
    def is_available(self) -> bool:
        """Check if S3 is available."""
        return self._s3_client is not None

    def get_cache_key(self, url: str) -> str:
        """
        Generate a cache key for an image URL.

        Uses MD5 hash of the URL for consistent naming.

        Args:
            url: Original image URL

        Returns:
            Cache key (hash)
        """
        return hashlib.md5(url.encode()).hexdigest()

    def get_file_extension(self, url: str, content_type: Optional[str] = None) -> str:
        """
        Determine file extension from URL or content type.

        Args:
            url: Image URL
            content_type: Optional MIME type

        Returns:
            File extension (e.g., ".jpg")
        """
        # Try content type first
        if content_type:
            ext = mimetypes.guess_extension(content_type)
            if ext:
                return ext

        # Try URL path
        parsed = urlparse(url)
        path = parsed.path.lower()

        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            if path.endswith(ext):
                return ext

        # Default to jpg
        return ".jpg"

    def get_s3_key(self, url: str, extension: Optional[str] = None) -> str:
        """
        Generate S3 object key for an image.

        Args:
            url: Original image URL
            extension: Optional file extension

        Returns:
            S3 object key
        """
        cache_key = self.get_cache_key(url)
        ext = extension or self.get_file_extension(url)

        # Organize by first two characters of hash
        prefix = cache_key[:2]
        return f"images/{prefix}/{cache_key}{ext}"

    def get_cached_url(self, s3_key: str) -> str:
        """
        Get the URL for a cached image.

        Uses CloudFront if configured, otherwise S3 URL.

        Args:
            s3_key: S3 object key

        Returns:
            Public URL for the cached image
        """
        if self.cloudfront_domain:
            return f"https://{self.cloudfront_domain}/{s3_key}"
        else:
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"

    async def cache_image(self, url: str) -> Optional[str]:
        """
        Download and cache an image in S3.

        Args:
            url: Original image URL

        Returns:
            Cached image URL or None if failed
        """
        if not self.is_available:
            logger.debug("S3 not available, skipping cache")
            return None

        try:
            # Check if already cached
            s3_key = self.get_s3_key(url)
            if await self._object_exists(s3_key):
                logger.debug(f"Image already cached: {s3_key}")
                return self.get_cached_url(s3_key)

            # Download image
            image_data, content_type = await self._download_image(url)
            if not image_data:
                return None

            # Update key with correct extension
            s3_key = self.get_s3_key(url, self.get_file_extension(url, content_type))

            # Upload to S3
            success = await self._upload_to_s3(s3_key, image_data, content_type)
            if success:
                logger.info(f"Cached image: {url} -> {s3_key}")
                return self.get_cached_url(s3_key)

            return None

        except Exception as e:
            logger.warning(f"Failed to cache image {url}: {e}")
            return None

    async def cache_images_batch(
        self,
        urls: List[str],
        max_concurrent: int = 5
    ) -> Dict[str, Optional[str]]:
        """
        Cache multiple images concurrently.

        Args:
            urls: List of image URLs to cache
            max_concurrent: Maximum concurrent downloads

        Returns:
            Dict mapping original URLs to cached URLs
        """
        import asyncio

        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def cache_with_semaphore(url: str):
            async with semaphore:
                results[url] = await self.cache_image(url)

        await asyncio.gather(
            *[cache_with_semaphore(url) for url in urls],
            return_exceptions=True
        )

        return results

    async def _download_image(self, url: str) -> tuple[Optional[bytes], Optional[str]]:
        """
        Download an image from URL.

        Args:
            url: Image URL

        Returns:
            Tuple of (image bytes, content type) or (None, None)
        """
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "image/jpeg")

            # Validate it's an image
            if not content_type.startswith("image/"):
                logger.warning(f"Not an image: {url} ({content_type})")
                return None, None

            # Size check (max 10MB)
            if len(response.content) > 10 * 1024 * 1024:
                logger.warning(f"Image too large: {url}")
                return None, None

            return response.content, content_type

        except Exception as e:
            logger.warning(f"Failed to download image {url}: {e}")
            return None, None

    async def _object_exists(self, s3_key: str) -> bool:
        """Check if an object exists in S3."""
        if not self._s3_client:
            return False

        try:
            self._s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except Exception:
            return False

    async def _upload_to_s3(
        self,
        s3_key: str,
        data: bytes,
        content_type: str
    ) -> bool:
        """
        Upload data to S3.

        Args:
            s3_key: S3 object key
            data: File data
            content_type: MIME type

        Returns:
            True if successful
        """
        if not self._s3_client:
            return False

        try:
            self._s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=data,
                ContentType=content_type,
                CacheControl="public, max-age=31536000",  # 1 year cache
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upload to S3: {e}")
            return False

    async def delete_cached_image(self, url: str) -> bool:
        """
        Delete a cached image from S3.

        Args:
            url: Original image URL

        Returns:
            True if deleted successfully
        """
        if not self._s3_client:
            return False

        try:
            s3_key = self.get_s3_key(url)
            self._s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete from S3: {e}")
            return False

    async def cleanup_old_images(self, days_old: int = 90) -> int:
        """
        Delete images not accessed in X days.

        Args:
            days_old: Minimum age in days

        Returns:
            Number of images deleted
        """
        if not self._s3_client:
            return 0

        # This would require S3 lifecycle policies or listing + checking
        # For now, return 0 and recommend using S3 lifecycle policies
        logger.info("Use S3 lifecycle policies for automatic cleanup")
        return 0

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
