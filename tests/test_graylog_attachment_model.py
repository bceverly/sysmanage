"""
Tests for backend/persistence/models/graylog_attachment.py module.
Tests GraylogAttachment model structure and methods.
"""

import uuid
from datetime import datetime, timezone

import pytest


class TestGraylogAttachmentModel:
    """Tests for GraylogAttachment model."""

    def test_graylog_attachment_table_name(self):
        """Test GraylogAttachment table name."""
        from backend.persistence.models.graylog_attachment import GraylogAttachment

        assert GraylogAttachment.__tablename__ == "graylog_attachment"

    def test_graylog_attachment_columns_exist(self):
        """Test GraylogAttachment has expected columns."""
        from backend.persistence.models.graylog_attachment import GraylogAttachment

        assert hasattr(GraylogAttachment, "id")
        assert hasattr(GraylogAttachment, "host_id")
        assert hasattr(GraylogAttachment, "is_attached")
        assert hasattr(GraylogAttachment, "target_hostname")
        assert hasattr(GraylogAttachment, "target_ip")
        assert hasattr(GraylogAttachment, "mechanism")
        assert hasattr(GraylogAttachment, "port")
        assert hasattr(GraylogAttachment, "detected_at")
        assert hasattr(GraylogAttachment, "updated_at")


class TestGraylogAttachmentRepr:
    """Tests for GraylogAttachment __repr__ method."""

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.graylog_attachment import GraylogAttachment

        attachment = GraylogAttachment()
        attachment.host_id = uuid.uuid4()
        attachment.is_attached = True
        attachment.mechanism = "syslog_tcp"

        repr_str = repr(attachment)

        assert "GraylogAttachment" in repr_str
        assert "True" in repr_str
        assert "syslog_tcp" in repr_str


class TestGraylogAttachmentToDict:
    """Tests for GraylogAttachment.to_dict method."""

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all fields."""
        from backend.persistence.models.graylog_attachment import GraylogAttachment

        attachment = GraylogAttachment()
        attachment.id = uuid.uuid4()
        attachment.host_id = uuid.uuid4()
        attachment.is_attached = True
        attachment.target_hostname = "graylog.example.com"
        attachment.target_ip = "192.168.1.100"
        attachment.mechanism = "gelf_tcp"
        attachment.port = 12201
        attachment.detected_at = datetime.now(timezone.utc)
        attachment.updated_at = datetime.now(timezone.utc)

        result = attachment.to_dict()

        assert result["id"] == str(attachment.id)
        assert result["host_id"] == str(attachment.host_id)
        assert result["is_attached"] is True
        assert result["target_hostname"] == "graylog.example.com"
        assert result["target_ip"] == "192.168.1.100"
        assert result["mechanism"] == "gelf_tcp"
        assert result["port"] == 12201
        assert result["detected_at"] is not None
        assert result["updated_at"] is not None

    def test_to_dict_with_none_values(self):
        """Test to_dict handles None values."""
        from backend.persistence.models.graylog_attachment import GraylogAttachment

        attachment = GraylogAttachment()
        attachment.id = uuid.uuid4()
        attachment.host_id = uuid.uuid4()
        attachment.is_attached = False
        attachment.target_hostname = None
        attachment.target_ip = None
        attachment.mechanism = None
        attachment.port = None
        attachment.detected_at = None
        attachment.updated_at = None

        result = attachment.to_dict()

        assert result["is_attached"] is False
        assert result["target_hostname"] is None
        assert result["target_ip"] is None
        assert result["mechanism"] is None
        assert result["port"] is None
        assert result["detected_at"] is None
        assert result["updated_at"] is None
