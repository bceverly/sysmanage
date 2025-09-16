"""
Comprehensive tests for backend/api/profile.py module.
Tests password change and image handling functionality.
"""

import io
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from PIL import Image

from backend.api.profile import (
    MAX_DIMENSIONS,
    MAX_FILE_SIZE,
    change_password,
    delete_profile_image,
    get_profile_image,
    upload_profile_image,
    validate_and_process_image,
)


class MockUser:
    """Mock user object for testing."""

    def __init__(
        self,
        userid="test@example.com",
        hashed_password="$argon2id$v=19$m=65536,t=3,p=4$test",
    ):
        self.userid = userid
        self.first_name = "Test"
        self.last_name = "User"
        self.active = True
        self.hashed_password = hashed_password
        self.profile_image = None
        self.profile_image_type = None
        self.profile_image_uploaded_at = None
        self.last_access = datetime.now(timezone.utc)


class MockPasswordChange:
    """Mock password change object for testing."""

    def __init__(
        self,
        current_password="current123",
        new_password="newpassword123",
        confirm_password="newpassword123",
    ):
        self.current_password = current_password
        self.new_password = new_password
        self.confirm_password = confirm_password


class MockUploadFile:
    """Mock upload file object for testing."""

    def __init__(self, content=b"test content", filename="test.png"):
        self.content = content
        self.filename = filename

    async def read(self):
        """Return the file content."""
        return self.content


class TestPasswordChange:
    """Test password change functionality."""

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    @patch("backend.api.profile.argon2_hasher")
    @patch("backend.api.profile.password_policy")
    async def test_change_password_success(
        self, mock_password_policy, mock_hasher, mock_get_engine, mock_sessionmaker
    ):
        """Test successful password change."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_user = MockUser()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        mock_password_policy.validate_password.return_value = (True, [])
        mock_hasher.verify.return_value = True
        mock_hasher.hash.return_value = "new_hashed_password"

        password_data = MockPasswordChange()

        result = await change_password(password_data, "test@example.com")

        assert result["message"] is not None
        mock_hasher.verify.assert_called_once()
        mock_hasher.hash.assert_called_once_with("newpassword123")
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_password_confirmation_mismatch(self):
        """Test password change with confirmation mismatch."""
        password_data = MockPasswordChange(confirm_password="different123")

        with pytest.raises(HTTPException) as exc_info:
            await change_password(password_data, "test@example.com")

        assert exc_info.value.status_code == 400
        assert "do not match" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.profile.password_policy")
    async def test_change_password_policy_validation_failed(self, mock_password_policy):
        """Test password change with policy validation failure."""
        mock_password_policy.validate_password.return_value = (
            False,
            ["Password too short", "No uppercase letter"],
        )

        password_data = MockPasswordChange()

        with pytest.raises(HTTPException) as exc_info:
            await change_password(password_data, "test@example.com")

        assert exc_info.value.status_code == 400
        assert "Password too short" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    @patch("backend.api.profile.password_policy")
    async def test_change_password_user_not_found(
        self, mock_password_policy, mock_get_engine, mock_sessionmaker
    ):
        """Test password change with nonexistent user."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_password_policy.validate_password.return_value = (True, [])

        password_data = MockPasswordChange()

        with pytest.raises(HTTPException) as exc_info:
            await change_password(password_data, "nonexistent@example.com")

        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    @patch("backend.api.profile.argon2_hasher")
    @patch("backend.api.profile.password_policy")
    async def test_change_password_current_password_incorrect(
        self, mock_password_policy, mock_hasher, mock_get_engine, mock_sessionmaker
    ):
        """Test password change with incorrect current password."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_user = MockUser()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        mock_password_policy.validate_password.return_value = (True, [])
        mock_hasher.verify.side_effect = Exception("Verification failed")

        password_data = MockPasswordChange()

        with pytest.raises(HTTPException) as exc_info:
            await change_password(password_data, "test@example.com")

        assert exc_info.value.status_code == 400
        assert "incorrect" in str(exc_info.value.detail)


class TestImageValidation:
    """Test image validation and processing functionality."""

    def create_test_image(self, width=100, height=100, format="PNG", mode="RGB"):
        """Create a test image for testing."""
        image = Image.new(mode, (width, height), color="red")
        img_bytes = io.BytesIO()
        image.save(img_bytes, format=format)
        img_bytes.seek(0)
        return img_bytes.getvalue()

    def test_validate_and_process_image_success(self):
        """Test successful image validation and processing."""
        image_content = self.create_test_image()

        result_bytes, result_format = validate_and_process_image(
            image_content, "test.png"
        )

        assert isinstance(result_bytes, bytes)
        assert result_format == "png"
        assert len(result_bytes) > 0

    def test_validate_and_process_image_too_large(self):
        """Test image validation with file size too large."""
        # Create content larger than MAX_FILE_SIZE
        large_content = b"x" * (MAX_FILE_SIZE + 1)

        with pytest.raises(HTTPException) as exc_info:
            validate_and_process_image(large_content, "large.png")

        assert exc_info.value.status_code == 413
        assert "too large" in str(exc_info.value.detail)

    def test_validate_and_process_image_invalid_format(self):
        """Test image validation with invalid format."""
        # Create a fake BMP image
        bmp_content = b"BM" + b"\x00" * 100

        with pytest.raises(HTTPException) as exc_info:
            validate_and_process_image(bmp_content, "test.bmp")

        assert exc_info.value.status_code == 400
        assert "Invalid image file" in str(exc_info.value.detail)

    def test_validate_and_process_image_resize_large(self):
        """Test image validation with oversized image that needs resizing."""
        large_image = self.create_test_image(width=1000, height=1000)

        result_bytes, result_format = validate_and_process_image(
            large_image, "large.png"
        )

        # Verify image was processed and resized
        assert isinstance(result_bytes, bytes)
        assert result_format == "png"

        # Check that the processed image is within max dimensions
        processed_image = Image.open(io.BytesIO(result_bytes))
        assert processed_image.size[0] <= MAX_DIMENSIONS[0]
        assert processed_image.size[1] <= MAX_DIMENSIONS[1]

    def test_validate_and_process_image_rgba_conversion(self):
        """Test RGBA image conversion to RGB."""
        rgba_image = self.create_test_image(mode="RGBA")

        result_bytes, result_format = validate_and_process_image(rgba_image, "rgba.png")

        assert isinstance(result_bytes, bytes)
        assert result_format == "png"

    def test_validate_and_process_image_palette_conversion(self):
        """Test palette mode image conversion."""
        # Create a palette mode image
        image = Image.new("P", (100, 100))
        img_bytes = io.BytesIO()
        image.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        result_bytes, result_format = validate_and_process_image(
            img_bytes.getvalue(), "palette.png"
        )

        assert isinstance(result_bytes, bytes)
        assert result_format == "png"

    def test_validate_and_process_image_not_an_image(self):
        """Test image validation with non-image content."""
        text_content = b"This is not an image file"

        with pytest.raises(HTTPException) as exc_info:
            validate_and_process_image(text_content, "text.txt")

        assert exc_info.value.status_code == 400
        assert "Invalid image file" in str(exc_info.value.detail)


class TestImageUpload:
    """Test profile image upload functionality."""

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    @patch("backend.api.profile.validate_and_process_image")
    async def test_upload_profile_image_success(
        self, mock_validate, mock_get_engine, mock_sessionmaker
    ):
        """Test successful profile image upload."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_user = MockUser()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        mock_validate.return_value = (b"processed_image_bytes", "png")

        file = MockUploadFile()

        result = await upload_profile_image(file, "test@example.com")

        assert result["message"] is not None
        assert result["image_format"] == "png"
        assert "uploaded_at" in result
        mock_session.commit.assert_called_once()
        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_profile_image_no_file(self):
        """Test profile image upload with no file."""
        with pytest.raises(HTTPException) as exc_info:
            await upload_profile_image(None, "test@example.com")

        assert exc_info.value.status_code == 400
        assert "No file provided" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    @patch("backend.api.profile.validate_and_process_image")
    async def test_upload_profile_image_user_not_found(
        self, mock_validate, mock_get_engine, mock_sessionmaker
    ):
        """Test profile image upload with nonexistent user."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_validate.return_value = (b"processed_image_bytes", "png")

        file = MockUploadFile()

        with pytest.raises(HTTPException) as exc_info:
            await upload_profile_image(file, "nonexistent@example.com")

        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_upload_profile_image_read_error(self):
        """Test profile image upload with file read error."""
        file = Mock()
        file.read.side_effect = Exception("Read error")

        with pytest.raises(HTTPException) as exc_info:
            await upload_profile_image(file, "test@example.com")

        assert exc_info.value.status_code == 400
        assert "Error reading uploaded file" in str(exc_info.value.detail)


class TestImageGet:
    """Test profile image retrieval functionality."""

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    async def test_get_profile_image_success(self, mock_get_engine, mock_sessionmaker):
        """Test successful profile image retrieval."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_user = MockUser()
        mock_user.profile_image = b"image_bytes"
        mock_user.profile_image_type = "png"
        mock_user.profile_image_uploaded_at = datetime.now(timezone.utc)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        result = await get_profile_image("test@example.com")

        assert result.body == b"image_bytes"
        assert result.media_type == "image/png"
        assert "Cache-Control" in result.headers

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    async def test_get_profile_image_jpeg_content_type(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test profile image retrieval with JPEG content type."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_user = MockUser()
        mock_user.profile_image = b"jpeg_bytes"
        mock_user.profile_image_type = "jpg"
        mock_user.profile_image_uploaded_at = datetime.now(timezone.utc)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        result = await get_profile_image("test@example.com")

        assert result.media_type == "image/jpeg"

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    async def test_get_profile_image_user_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test profile image retrieval with nonexistent user."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_profile_image("nonexistent@example.com")

        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    async def test_get_profile_image_no_image(self, mock_get_engine, mock_sessionmaker):
        """Test profile image retrieval with no image."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_user = MockUser()
        mock_user.profile_image = None
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_profile_image("test@example.com")

        assert exc_info.value.status_code == 404
        assert "No profile image found" in str(exc_info.value.detail)


class TestImageDelete:
    """Test profile image deletion functionality."""

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    async def test_delete_profile_image_success(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test successful profile image deletion."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_user = MockUser()
        mock_user.profile_image = b"image_bytes"
        mock_user.profile_image_type = "png"
        mock_user.profile_image_uploaded_at = datetime.now(timezone.utc)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        result = await delete_profile_image("test@example.com")

        assert result["message"] is not None
        assert mock_user.profile_image is None
        assert mock_user.profile_image_type is None
        assert mock_user.profile_image_uploaded_at is None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    async def test_delete_profile_image_user_not_found(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test profile image deletion with nonexistent user."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await delete_profile_image("nonexistent@example.com")

        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("backend.api.profile.sessionmaker")
    @patch("backend.api.profile.db.get_engine")
    async def test_delete_profile_image_no_image(
        self, mock_get_engine, mock_sessionmaker
    ):
        """Test profile image deletion with no image."""
        mock_session = Mock()
        mock_sessionmaker.return_value.return_value.__enter__.return_value = (
            mock_session
        )

        mock_user = MockUser()
        mock_user.profile_image = None
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with pytest.raises(HTTPException) as exc_info:
            await delete_profile_image("test@example.com")

        assert exc_info.value.status_code == 404
        assert "No profile image to delete" in str(exc_info.value.detail)


class TestImageUploadIntegration:
    """Integration tests for image upload functionality."""

    def test_image_security_constants(self):
        """Test that security constants are properly defined."""
        assert MAX_FILE_SIZE == 5 * 1024 * 1024  # 5MB
        assert MAX_DIMENSIONS == (512, 512)

    def create_test_image_content(self, format="PNG", width=100, height=100):
        """Create test image content."""
        image = Image.new("RGB", (width, height), color="blue")
        img_bytes = io.BytesIO()
        image.save(img_bytes, format=format)
        img_bytes.seek(0)
        return img_bytes.getvalue()

    def test_validate_and_process_image_format_detection(self):
        """Test image format detection and processing."""
        # Test PNG
        png_content = self.create_test_image_content("PNG")
        result_bytes, result_format = validate_and_process_image(
            png_content, "test.png"
        )
        assert result_format == "png"

        # Test JPEG
        jpeg_content = self.create_test_image_content("JPEG")
        result_bytes, result_format = validate_and_process_image(
            jpeg_content, "test.jpg"
        )
        assert result_format == "png"  # Always converts to PNG

    def test_validate_and_process_image_edge_cases(self):
        """Test edge cases in image validation."""
        # Test exactly maximum dimensions
        max_size_image = self.create_test_image_content(
            width=MAX_DIMENSIONS[0], height=MAX_DIMENSIONS[1]
        )
        result_bytes, result_format = validate_and_process_image(
            max_size_image, "max.png"
        )
        assert result_format == "png"

        # Test minimum size
        tiny_image = self.create_test_image_content(width=1, height=1)
        result_bytes, result_format = validate_and_process_image(tiny_image, "tiny.png")
        assert result_format == "png"

    def test_mock_upload_file_functionality(self):
        """Test MockUploadFile functionality."""
        file = MockUploadFile(b"test content", "test.png")
        assert file.filename == "test.png"

        # Test async read
        import asyncio

        async def test_read():
            content = await file.read()
            return content

        content = asyncio.run(test_read())
        assert content == b"test content"
