"""Tests for the S3 photo upload service."""
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from app.services.storage.photo_service import PhotoService, MAX_FILE_SIZE


def _make_test_image(width=100, height=100, fmt="JPEG") -> bytes:
    """Create a small test image in memory."""
    img = Image.new("RGB", (width, height), color="red")
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestUploadPhoto:
    @patch("app.services.storage.photo_service._get_s3_client")
    def test_upload_photo_succeeds_with_valid_jpeg(self, mock_get_client):
        """upload_photo succeeds with valid JPEG data."""
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        file_data = _make_test_image()
        result = PhotoService.upload_photo(
            file_data=file_data,
            content_type="image/jpeg",
            user_id="user-123",
            tour_id="tour-456",
        )

        assert "s3_key" in result
        assert "thumbnail_s3_key" in result
        assert result["s3_key"].startswith("tours/user-123/tour-456/")
        assert result["s3_key"].endswith(".jpg")
        assert "/thumbs/" in result["thumbnail_s3_key"]

        # Verify two put_object calls (original + thumbnail)
        assert mock_s3.put_object.call_count == 2

    def test_upload_photo_rejects_oversized_file(self):
        """upload_photo raises ValueError for files exceeding 10 MB."""
        oversized_data = b"x" * (MAX_FILE_SIZE + 1)

        with pytest.raises(ValueError, match="File too large"):
            PhotoService.upload_photo(
                file_data=oversized_data,
                content_type="image/jpeg",
                user_id="user-123",
                tour_id="tour-456",
            )

    def test_upload_photo_rejects_invalid_content_type(self):
        """upload_photo raises ValueError for unsupported content types."""
        file_data = b"fake data"

        with pytest.raises(ValueError, match="Unsupported file type"):
            PhotoService.upload_photo(
                file_data=file_data,
                content_type="image/gif",
                user_id="user-123",
                tour_id="tour-456",
            )


class TestThumbnailGeneration:
    def test_thumbnail_produces_smaller_image(self):
        """Thumbnail generation produces a smaller image (<=300x300)."""
        file_data = _make_test_image(width=800, height=600)

        thumb_data = PhotoService._generate_thumbnail(file_data, "image/jpeg")

        thumb_img = Image.open(BytesIO(thumb_data))
        assert thumb_img.width <= 300
        assert thumb_img.height <= 300
        assert len(thumb_data) < len(file_data)


class TestPresignedUrl:
    @patch("app.services.storage.photo_service._get_s3_client")
    def test_get_presigned_url_calls_s3_correctly(self, mock_get_client):
        """get_presigned_url calls generate_presigned_url with correct params."""
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"
        mock_get_client.return_value = mock_s3

        url = PhotoService.get_presigned_url("tours/user-123/tour-456/abc.jpg")

        assert url == "https://s3.example.com/presigned"
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "snugd-tours", "Key": "tours/user-123/tour-456/abc.jpg"},
            ExpiresIn=3600,
        )


class TestDeletePhoto:
    @patch("app.services.storage.photo_service._get_s3_client")
    def test_delete_photo_removes_both_original_and_thumbnail(self, mock_get_client):
        """delete_photo removes both original and thumbnail from S3."""
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        PhotoService.delete_photo(
            s3_key="tours/user-123/tour-456/abc.jpg",
            thumbnail_s3_key="tours/user-123/tour-456/thumbs/abc.jpg",
        )

        assert mock_s3.delete_object.call_count == 2
        mock_s3.delete_object.assert_any_call(
            Bucket="snugd-tours", Key="tours/user-123/tour-456/abc.jpg"
        )
        mock_s3.delete_object.assert_any_call(
            Bucket="snugd-tours", Key="tours/user-123/tour-456/thumbs/abc.jpg"
        )
