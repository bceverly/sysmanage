"""Tests for script execution delete endpoints."""

import pytest

from backend.persistence import models


class TestScriptExecutionDelete:
    """Test cases for DELETE /api/scripts/executions/{execution_id} endpoint."""

    def test_delete_script_execution_success(self, client, session, auth_headers):
        """Test successful deletion of a script execution."""
        from unittest.mock import patch

        # Force creation of script_execution_log table if it doesn't exist
        from backend.persistence.db import Base

        models.ScriptExecutionLog.__table__.create(session.get_bind(), checkfirst=True)

        # Patch db.engine to use the test engine
        test_engine = session.get_bind()
        with patch("backend.persistence.db.engine", test_engine):
            # Create a test host
            host = models.Host(
                fqdn="test.example.com",
                ipv4="192.168.1.1",
                status="up",
                active=True,
                approval_status="approved",
            )
            session.add(host)
            session.commit()

            # Create a test script execution
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            execution = models.ScriptExecutionLog(
                execution_id="test-exec-123",
                script_name="Test Script",
                script_content="echo 'test'",
                shell_type="bash",
                host_id=host.id,
                status="completed",
                requested_by="test_user",  # Using string as required by model
                exit_code=0,
                stdout_output="test",
                created_at=now,
                updated_at=now,
            )
            session.add(execution)
            session.commit()
            session.flush()  # Ensure the data is written to the database
            execution_id = execution.execution_id

            # Delete the execution
            response = client.delete(
                f"/api/scripts/executions/{execution_id}", headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "deleted successfully" in data["message"]

            # Verify execution is deleted
            deleted_execution = (
                session.query(models.ScriptExecutionLog)
                .filter(models.ScriptExecutionLog.execution_id == execution_id)
                .first()
            )
            assert deleted_execution is None

    def test_delete_script_execution_not_found(self, client, auth_headers):
        """Test deletion of non-existent script execution."""
        response = client.delete(
            "/api/scripts/executions/nonexistent-id", headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]

    def test_delete_script_execution_unauthorized(self, client):
        """Test deletion without authentication."""
        response = client.delete("/api/scripts/executions/test-id")

        # Should return 401 or 403, not 404
        assert response.status_code in [401, 403]
