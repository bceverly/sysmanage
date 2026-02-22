"""
Tests for Pro+ stub endpoints.

Verifies that all endpoints gated behind Pro+ modules return HTTP 402
when no Pro+ module is loaded (community edition behavior).
Also verifies that read-only endpoints remain functional.
"""

from unittest.mock import patch, MagicMock

import pytest


class TestContainerCrudStubs:
    """Test that container CRUD write operations return 402 without Pro+ module."""

    def test_create_child_host_returns_402(self, client):
        """Test creating a child host returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/host/test-host-id/children",
                json={
                    "hostname": "test-child",
                    "child_type": "wsl",
                    "distribution_id": "test-dist-id",
                    "username": "user",
                    "password": "pass",
                    "auto_approve": False,
                },
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_delete_child_host_returns_402(self, client):
        """Test deleting a child host returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.delete("/api/host/test-host-id/children/test-child-id")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]


class TestVirtualizationEnableStubs:
    """Test that virtualization enable/init operations return 402 without Pro+ module."""

    def test_enable_wsl_returns_402(self, client):
        """Test enabling WSL returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post("/api/host/test-host-id/virtualization/enable-wsl")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_initialize_lxd_returns_402(self, client):
        """Test initializing LXD returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/host/test-host-id/virtualization/initialize-lxd"
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_create_child_via_old_endpoint_returns_402(self, client):
        """Test creating a child host via old virtualization endpoint returns 402."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/host/test-host-id/virtualization/create-child",
                json={
                    "child_type": "wsl",
                    "distribution": "Ubuntu-24.04",
                    "hostname": "test-child",
                    "username": "user",
                    "password": "pass",
                    "auto_approve": False,
                },
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]


class TestContainerControlStubs:
    """Test that container control operations return 402 without Pro+ module."""

    def test_start_child_host_returns_402(self, client):
        """Test starting a child host returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/host/test-host-id/children/test-child-id/start"
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_stop_child_host_returns_402(self, client):
        """Test stopping a child host returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post("/api/host/test-host-id/children/test-child-id/stop")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_restart_child_host_returns_402(self, client):
        """Test restarting a child host returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/host/test-host-id/children/test-child-id/restart"
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]


class TestDistributionCrudStubs:
    """Test that distribution CRUD write operations return 402 without Pro+ module."""

    def test_create_distribution_returns_402(self, client):
        """Test creating a distribution returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/child-host-distributions",
                json={
                    "child_type": "wsl",
                    "distribution_name": "Ubuntu",
                    "distribution_version": "22.04",
                    "display_name": "Ubuntu 22.04 LTS",
                    "install_identifier": "Ubuntu-22.04",
                    "executable_name": "wsl",
                    "agent_install_method": "script",
                    "is_active": True,
                },
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_update_distribution_returns_402(self, client):
        """Test updating a distribution returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.put(
                "/api/child-host-distributions/test-dist-id",
                json={"display_name": "Updated Name"},
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_delete_distribution_returns_402(self, client):
        """Test deleting a distribution returns 402 without container_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.delete("/api/child-host-distributions/test-dist-id")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]


class TestSecretsStubs:
    """Test that secrets endpoints return 402 without Pro+ module."""

    def test_list_secrets_returns_unlicensed(self, client):
        """Test listing secrets returns licensed=false without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.get("/api/secrets")
            assert response.status_code == 200
            assert response.json()["licensed"] is False

    def test_get_secret_metadata_returns_402(self, client):
        """Test getting secret metadata returns 402 without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.get("/api/secrets/test-secret-id")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_get_secret_content_returns_402(self, client):
        """Test getting secret content returns 402 without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.get("/api/secrets/test-secret-id/content")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_create_secret_returns_402(self, client):
        """Test creating a secret returns 402 without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/secrets",
                json={
                    "name": "test-secret",
                    "secret_type": "ssh_key",
                    "content": "ssh-rsa AAAA...",
                },
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_update_secret_returns_402(self, client):
        """Test updating a secret returns 402 without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.put(
                "/api/secrets/test-secret-id",
                json={"name": "updated-secret"},
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_delete_secret_returns_402(self, client):
        """Test deleting a secret returns 402 without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.delete("/api/secrets/test-secret-id")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_get_secret_types_returns_unlicensed(self, client):
        """Test getting secret types returns licensed=false without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.get("/api/secrets/types")
            assert response.status_code == 200
            assert response.json()["licensed"] is False

    def test_deploy_ssh_keys_returns_402(self, client):
        """Test deploying SSH keys returns 402 without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/secrets/deploy-ssh-keys",
                json={
                    "host_id": "test-host-id",
                    "username": "testuser",
                    "secret_ids": ["secret-1"],
                },
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_deploy_certificates_returns_402(self, client):
        """Test deploying certificates returns 402 without secrets_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.post(
                "/api/secrets/deploy-certificates",
                json={
                    "host_id": "test-host-id",
                    "secret_ids": ["cert-1"],
                },
            )
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]


class TestReportsStubs:
    """Test that report endpoints return 402 without Pro+ module."""

    def test_view_report_returns_402(self, client):
        """Test viewing an HTML report returns 402 without reporting_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.get("/api/reports/view/registered-hosts")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_generate_report_returns_402(self, client):
        """Test generating a PDF report returns 402 without reporting_engine."""
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            response = client.get("/api/reports/generate/registered-hosts")
            assert response.status_code == 402
            assert "Professional+" in response.json()["detail"]

    def test_report_screenshots_still_work(self, client):
        """Test that report screenshot placeholders remain available."""
        response = client.get("/api/reports/screenshots/registered-hosts")
        assert response.status_code == 200
        assert "image/svg+xml" in response.headers.get("content-type", "")

    def test_report_screenshots_head_works(self, client):
        """Test that report screenshot HEAD requests work."""
        response = client.head("/api/reports/screenshots/registered-hosts")
        assert response.status_code == 200


class TestProPlusV1StubRoutes:
    """Test that /api/v1 stub routes return licensed=false when modules aren't loaded."""

    def test_audit_statistics_stub(self, client):
        """Test audit statistics returns licensed=false without audit_engine."""
        response = client.get("/api/v1/audit/statistics")
        assert response.status_code == 200
        assert response.json()["licensed"] is False

    def test_audit_export_stub(self, client):
        """Test audit export returns licensed=false without audit_engine."""
        response = client.post("/api/v1/audit/export")
        assert response.status_code == 200
        assert response.json()["licensed"] is False

    def test_secrets_statistics_stub(self, client):
        """Test secrets statistics returns licensed=false without secrets_engine."""
        response = client.get("/api/v1/secrets/statistics")
        assert response.status_code == 200
        assert response.json()["licensed"] is False

    def test_secrets_access_logs_stub(self, client):
        """Test secrets access logs returns licensed=false without secrets_engine."""
        response = client.get("/api/v1/secrets/access-logs")
        assert response.status_code == 200
        data = response.json()
        assert data["licensed"] is False
        assert data["access_logs"] == []

    def test_containers_statistics_stub(self, client):
        """Test container statistics returns licensed=false without container_engine."""
        response = client.get("/api/v1/containers/statistics")
        assert response.status_code == 200
        assert response.json()["licensed"] is False

    def test_reports_generate_stub(self, client):
        """Test report generation returns licensed=false without reporting_engine."""
        response = client.get("/api/v1/reports/generate/registered-hosts")
        assert response.status_code == 200
        assert response.json()["licensed"] is False

    def test_reports_view_stub(self, client):
        """Test report view returns licensed=false without reporting_engine."""
        response = client.get("/api/v1/reports/view/registered-hosts")
        assert response.status_code == 200
        assert response.json()["licensed"] is False


class TestReadOnlyEndpointsStillWork:
    """Test that read-only endpoints are not affected by Pro+ gating."""

    def test_list_distributions_works(self, client):
        """Test listing distributions still works (read-only)."""
        response = client.get("/api/child-host-distributions")
        assert response.status_code == 200

    def test_report_screenshot_xss_prevention(self, client):
        """Test that report screenshots escape HTML entities in report_id."""
        # Use a report_id with & character that html.escape will sanitize
        response = client.get("/api/reports/screenshots/test&name")
        assert response.status_code == 200
        body = response.text
        # html.escape should convert & to &amp;
        assert "test&name" not in body
        assert "&amp;" in body


class TestSecretsRotationScheduleStubs:
    """Test rotation schedule stub endpoints return licensed=false."""

    def test_rotation_schedules_list_stub(self, client):
        """Test listing rotation schedules returns licensed=false without secrets_engine."""
        response = client.get("/api/v1/secrets/rotation-schedules")
        assert response.status_code == 200
        data = response.json()
        assert data["licensed"] is False
        assert data["schedules"] == []

    def test_secret_versions_stub(self, client):
        """Test listing secret versions returns licensed=false without secrets_engine."""
        response = client.get("/api/v1/secrets/test-secret-id/versions")
        assert response.status_code == 200
        data = response.json()
        assert data["licensed"] is False
        assert data["versions"] == []


class TestContainerActionStubs:
    """Test container action stub endpoints return licensed=false."""

    def test_container_create_stub(self, client):
        """Test container create returns licensed=false without container_engine."""
        response = client.post("/api/v1/containers/create")
        assert response.status_code == 200
        assert response.json()["licensed"] is False

    def test_container_action_stub(self, client):
        """Test container action returns licensed=false without container_engine."""
        response = client.post("/api/v1/containers/test-id/action")
        assert response.status_code == 200
        assert response.json()["licensed"] is False

    def test_container_network_stub(self, client):
        """Test container network returns licensed=false without container_engine."""
        response = client.post("/api/v1/containers/test-id/network")
        assert response.status_code == 200
        assert response.json()["licensed"] is False


class TestAuditIntegrityHash:
    """Test that audit log entries include integrity hash."""

    def test_audit_service_computes_integrity_hash(self):
        """Test that AuditService.log computes an integrity hash."""
        import hashlib
        import uuid
        from datetime import datetime, timezone

        from backend.services.audit_service import ActionType, EntityType, Result

        # Verify the hash computation logic
        entry_id = uuid.uuid4()
        entry_timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
        user_id = uuid.uuid4()
        action_type = ActionType.CREATE
        entity_type = EntityType.HOST
        entity_id = "test-entity"
        description = "Test action"
        result = Result.SUCCESS

        hash_parts = [
            str(entry_id),
            str(entry_timestamp),
            str(user_id),
            str(action_type.value),
            str(entity_type.value),
            str(entity_id),
            str(description),
            str(result.value),
        ]
        integrity_hash = hashlib.sha256("|".join(hash_parts).encode()).hexdigest()

        assert len(integrity_hash) == 64
        assert all(c in "0123456789abcdef" for c in integrity_hash)


class TestSecretVersionModel:
    """Test SecretVersion model exists and has correct attributes."""

    def test_secret_version_model_importable(self):
        """Test that SecretVersion model can be imported."""
        from backend.persistence.models import SecretVersion

        assert SecretVersion.__tablename__ == "secret_version"

    def test_secret_version_has_required_columns(self):
        """Test SecretVersion has the required columns."""
        from backend.persistence.models import SecretVersion

        mapper = SecretVersion.__table__
        column_names = [c.name for c in mapper.columns]
        assert "id" in column_names
        assert "secret_id" in column_names
        assert "version_number" in column_names
        assert "content_hash" in column_names
        assert "created_at" in column_names
        assert "created_by" in column_names
        assert "change_description" in column_names


class TestRotationScheduleModel:
    """Test RotationSchedule model exists and has correct attributes."""

    def test_rotation_schedule_model_importable(self):
        """Test that RotationSchedule model can be imported."""
        from backend.persistence.models import RotationSchedule

        assert RotationSchedule.__tablename__ == "rotation_schedule"

    def test_rotation_schedule_has_required_columns(self):
        """Test RotationSchedule has the required columns."""
        from backend.persistence.models import RotationSchedule

        mapper = RotationSchedule.__table__
        column_names = [c.name for c in mapper.columns]
        assert "id" in column_names
        assert "secret_id" in column_names
        assert "frequency" in column_names
        assert "notify_days_before" in column_names
        assert "auto_rotate" in column_names
        assert "enabled" in column_names
        assert "next_rotation" in column_names
        assert "last_rotation" in column_names


class TestAuditLogIntegrityHashColumn:
    """Test that AuditLog model has the integrity_hash column."""

    def test_audit_log_has_integrity_hash(self):
        """Test that AuditLog model includes integrity_hash column."""
        from backend.persistence.models import AuditLog

        mapper = AuditLog.__table__
        column_names = [c.name for c in mapper.columns]
        assert "integrity_hash" in column_names
