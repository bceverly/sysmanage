"""
Tests for tag management API endpoints
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.persistence import models


class TestTagEndpoints:
    """Test cases for tag management endpoints"""

    def test_get_tags_empty(self, client: TestClient, auth_headers):
        """Test getting tags when none exist"""
        response = client.get("/api/tags", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_create_tag_success(self, client: TestClient, auth_headers):
        """Test creating a new tag"""
        tag_data = {"name": "Production", "description": "Production servers"}

        response = client.post("/api/tags", json=tag_data, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Production"
        assert data["description"] == "Production servers"
        assert data["host_count"] == 0
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_tag_duplicate_name(self, client: TestClient, auth_headers, session):
        """Test creating a tag with duplicate name fails"""
        # Create first tag
        tag = models.Tag(
            name="Development",
            description="Dev servers",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()

        tag_data = {"name": "Development", "description": "Another dev tag"}

        response = client.post("/api/tags", json=tag_data, headers=auth_headers)

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_create_tag_no_description(self, client: TestClient, auth_headers):
        """Test creating a tag without description"""
        tag_data = {"name": "Testing"}

        response = client.post("/api/tags", json=tag_data, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Testing"
        assert data["description"] is None

    def test_get_tags_with_data(self, client: TestClient, auth_headers, session):
        """Test getting tags when some exist"""
        # Create test tags
        tag1 = models.Tag(
            name="Web",
            description="Web servers",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        tag2 = models.Tag(
            name="Database",
            description="Database servers",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add_all([tag1, tag2])
        session.commit()

        response = client.get("/api/tags", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [tag["name"] for tag in data]
        assert "Web" in names
        assert "Database" in names

    def test_update_tag_success(self, client: TestClient, auth_headers, session):
        """Test updating a tag"""
        tag = models.Tag(
            name="Old Name",
            description="Old description",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()
        session.refresh(tag)

        update_data = {"name": "New Name", "description": "New description"}

        response = client.put(
            f"/api/tags/{tag.id}", json=update_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["description"] == "New description"

    def test_update_tag_not_found(self, client: TestClient, auth_headers):
        """Test updating non-existent tag"""
        update_data = {"name": "New Name"}

        response = client.put("/api/tags/999", json=update_data, headers=auth_headers)

        assert response.status_code == 404

    def test_delete_tag_success(self, client: TestClient, auth_headers, session):
        """Test deleting a tag"""
        tag = models.Tag(
            name="To Delete",
            description="Will be deleted",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()
        session.refresh(tag)
        tag_id = tag.id

        response = client.delete(f"/api/tags/{tag_id}", headers=auth_headers)

        if response.status_code != 204:
            print(f"Error response: {response.json()}")
        assert response.status_code == 204

        # Verify tag is deleted
        deleted_tag = session.query(models.Tag).filter(models.Tag.id == tag_id).first()
        assert deleted_tag is None

    def test_delete_tag_not_found(self, client: TestClient, auth_headers):
        """Test deleting non-existent tag"""
        response = client.delete("/api/tags/999", headers=auth_headers)

        assert response.status_code == 404


class TestTagHostAssociation:
    """Test cases for tag-host associations"""

    def test_add_tag_to_host_success(self, client: TestClient, auth_headers, session):
        """Test adding a tag to a host"""
        # Create test host using API models
        host = models.Host(
            id=1,
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            ipv6="2001:db8::1",
            active=True,
            status="up",
            approval_status="approved",
        )
        session.add(host)

        tag = models.Tag(
            name="Web Server",
            description="Web server tag",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()
        session.refresh(host)
        session.refresh(tag)

        response = client.post(
            f"/api/hosts/{host.id}/tags/{tag.id}", headers=auth_headers
        )

        if response.status_code != 201:
            print(f"Error response: {response.json()}")
        assert response.status_code == 201

        # Verify association exists
        association = (
            session.query(models.HostTag)
            .filter(models.HostTag.host_id == host.id, models.HostTag.tag_id == tag.id)
            .first()
        )
        assert association is not None

    def test_add_tag_to_host_duplicate(self, client: TestClient, auth_headers, session):
        """Test adding same tag to host twice fails"""
        # Create test host
        host = models.Host(
            id=1,
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            active=True,
            status="up",
            approval_status="approved",
        )
        session.add(host)

        tag = models.Tag(
            name="Duplicate",
            description="Duplicate tag",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()
        session.refresh(host)
        session.refresh(tag)

        # Create association first time
        association = models.HostTag(
            host_id=host.id, tag_id=tag.id, created_at=datetime.now(timezone.utc)
        )
        session.add(association)
        session.commit()

        # Try to add again
        response = client.post(
            f"/api/hosts/{host.id}/tags/{tag.id}", headers=auth_headers
        )

        assert response.status_code == 400
        assert "already associated" in response.json()["detail"]

    def test_add_tag_to_nonexistent_host(
        self, client: TestClient, auth_headers, session
    ):
        """Test adding tag to non-existent host"""
        tag = models.Tag(
            name="Test",
            description="Test tag",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()
        session.refresh(tag)

        response = client.post(f"/api/hosts/999/tags/{tag.id}", headers=auth_headers)

        assert response.status_code == 404
        assert "Host not found" in response.json()["detail"]

    def test_add_nonexistent_tag_to_host(
        self, client: TestClient, auth_headers, session
    ):
        """Test adding non-existent tag to host"""
        # Create test host
        host = models.Host(
            id=1,
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            active=True,
            status="up",
            approval_status="approved",
        )
        session.add(host)
        session.commit()
        session.refresh(host)

        response = client.post(f"/api/hosts/{host.id}/tags/999", headers=auth_headers)

        assert response.status_code == 404
        assert "Tag not found" in response.json()["detail"]

    def test_remove_tag_from_host_success(
        self, client: TestClient, auth_headers, session
    ):
        """Test removing a tag from a host"""
        # Create test host and tag
        host = models.Host(
            id=1,
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            active=True,
            status="up",
            approval_status="approved",
        )
        session.add(host)

        tag = models.Tag(
            name="To Remove",
            description="Will be removed",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()
        session.refresh(host)
        session.refresh(tag)

        # Create association
        association = models.HostTag(
            host_id=host.id, tag_id=tag.id, created_at=datetime.now(timezone.utc)
        )
        session.add(association)
        session.commit()

        response = client.delete(
            f"/api/hosts/{host.id}/tags/{tag.id}", headers=auth_headers
        )

        assert response.status_code == 204

        # Verify association is removed
        removed_association = (
            session.query(models.HostTag)
            .filter(models.HostTag.host_id == host.id, models.HostTag.tag_id == tag.id)
            .first()
        )
        assert removed_association is None

    def test_remove_tag_from_host_not_associated(
        self, client: TestClient, auth_headers, session
    ):
        """Test removing tag that isn't associated with host"""
        # Create test host and tag
        host = models.Host(
            id=1,
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            active=True,
            status="up",
            approval_status="approved",
        )
        session.add(host)

        tag = models.Tag(
            name="Not Associated",
            description="Not associated tag",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()
        session.refresh(host)
        session.refresh(tag)

        response = client.delete(
            f"/api/hosts/{host.id}/tags/{tag.id}", headers=auth_headers
        )

        assert response.status_code == 404

    def test_get_host_tags(self, client: TestClient, auth_headers, session):
        """Test getting all tags for a specific host"""
        # Create test host
        host = models.Host(
            id=1,
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            active=True,
            status="up",
            approval_status="approved",
        )
        session.add(host)

        # Create tags
        tag1 = models.Tag(
            name="Tag1",
            description="First tag",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        tag2 = models.Tag(
            name="Tag2",
            description="Second tag",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add_all([tag1, tag2])
        session.commit()
        session.refresh(host)
        session.refresh(tag1)
        session.refresh(tag2)

        # Create associations
        assoc1 = models.HostTag(
            host_id=host.id, tag_id=tag1.id, created_at=datetime.now(timezone.utc)
        )
        assoc2 = models.HostTag(
            host_id=host.id, tag_id=tag2.id, created_at=datetime.now(timezone.utc)
        )
        session.add_all([assoc1, assoc2])
        session.commit()

        response = client.get(f"/api/hosts/{host.id}/tags", headers=auth_headers)

        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [tag["name"] for tag in data]
        assert "Tag1" in names
        assert "Tag2" in names

    def test_get_tag_hosts(self, client: TestClient, auth_headers, session):
        """Test getting all hosts associated with a specific tag"""
        # Create test host
        host = models.Host(
            id=1,
            fqdn="test.example.com",
            ipv4="192.168.1.100",
            active=True,
            status="up",
            approval_status="approved",
        )
        session.add(host)

        tag = models.Tag(
            name="Host Tag",
            description="Tag with hosts",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tag)
        session.commit()
        session.refresh(host)
        session.refresh(tag)

        # Create association
        association = models.HostTag(
            host_id=host.id, tag_id=tag.id, created_at=datetime.now(timezone.utc)
        )
        session.add(association)
        session.commit()

        response = client.get(f"/api/tags/{tag.id}/hosts", headers=auth_headers)

        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == tag.id
        assert data["name"] == "Host Tag"
        assert len(data["hosts"]) == 1
        assert data["hosts"][0]["id"] == host.id


class TestTagEndpointsAuth:
    """Test authentication requirements for tag endpoints"""

    def test_get_tags_unauthorized(self, client: TestClient):
        """Test that getting tags requires authentication"""
        response = client.get("/api/tags")
        assert response.status_code == 403

    def test_create_tag_unauthorized(self, client: TestClient):
        """Test that creating tags requires authentication"""
        tag_data = {"name": "Test", "description": "Test tag"}
        response = client.post("/api/tags", json=tag_data)
        assert response.status_code == 403

    def test_update_tag_unauthorized(self, client: TestClient):
        """Test that updating tags requires authentication"""
        update_data = {"name": "Updated"}
        response = client.put("/api/tags/1", json=update_data)
        assert response.status_code == 403

    def test_delete_tag_unauthorized(self, client: TestClient):
        """Test that deleting tags requires authentication"""
        response = client.delete("/api/tags/1")
        assert response.status_code == 403

    def test_add_tag_to_host_unauthorized(self, client: TestClient):
        """Test that adding tags to hosts requires authentication"""
        response = client.post("/api/hosts/1/tags/1")
        assert response.status_code == 403

    def test_remove_tag_from_host_unauthorized(self, client: TestClient):
        """Test that removing tags from hosts requires authentication"""
        response = client.delete("/api/hosts/1/tags/1")
        assert response.status_code == 403
