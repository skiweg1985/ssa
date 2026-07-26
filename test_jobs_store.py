"""Tests für app/services/jobs_store.py (DB-Layer, Config-Bridge)"""
import pytest

from app.services.jobs_store import (
    ConnectionInUseError,
    JobsStore,
    NotFoundError,
)
from app.services.security import reset_key_cache


@pytest.fixture(autouse=True)
def _fixed_secret_key(monkeypatch):
    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
    reset_key_cache()
    yield
    reset_key_cache()


@pytest.fixture
def store(tmp_path):
    return JobsStore(tmp_path / "test.db")


@pytest.fixture
def connection(store):
    return store.create_connection(
        name="Test-NAS",
        host="192.168.1.10",
        username="syno",
        password="geheim",
        port=5001,
    )


class TestConnections:
    def test_create_and_get(self, store, connection):
        assert connection["id"] == 1
        assert connection["name"] == "Test-NAS"
        assert connection["job_count"] == 0
        # Öffentliche Sicht enthält NIE ein Passwort(-Feld)
        assert "password" not in connection
        assert "password_encrypted" not in connection

    def test_password_encrypted_at_rest(self, store, connection):
        row = store.get_connection_row(connection["id"])
        assert row["password_encrypted"] != "geheim"
        assert store.get_connection_password(connection["id"]) == "geheim"

    def test_update_keeps_password_when_empty(self, store, connection):
        store.update_connection(
            connection["id"],
            name="Umbenannt",
            host="192.168.1.10",
            username="syno",
            password=None,
        )
        assert store.get_connection_password(connection["id"]) == "geheim"
        assert store.get_connection(connection["id"])["name"] == "Umbenannt"

    def test_update_changes_password_when_given(self, store, connection):
        store.update_connection(
            connection["id"],
            name="Test-NAS",
            host="192.168.1.10",
            username="syno",
            password="neues-pw",
        )
        assert store.get_connection_password(connection["id"]) == "neues-pw"

    def test_delete_free_connection(self, store, connection):
        store.delete_connection(connection["id"])
        assert store.get_connection(connection["id"]) is None

    def test_delete_in_use_refused(self, store, connection):
        store.create_job(
            name="Mein Scan",
            nas_connection_id=connection["id"],
            interval="6h",
            paths=["/homes"],
        )
        with pytest.raises(ConnectionInUseError) as exc:
            store.delete_connection(connection["id"])
        assert "Mein Scan" in str(exc.value)

    def test_delete_missing_raises(self, store):
        with pytest.raises(NotFoundError):
            store.delete_connection(999)


class TestJobs:
    def test_create_generates_slug(self, store, connection):
        job = store.create_job(
            name="Mein Backup Scan",
            nas_connection_id=connection["id"],
            interval="30m",
            paths=["/backup"],
        )
        assert job["slug"] == "mein-backup-scan"
        assert job["enabled"] is True

    def test_slug_uniqueness(self, store, connection):
        job1 = store.create_job(
            name="Scan", nas_connection_id=connection["id"],
            interval="1h", paths=["/a"],
        )
        job2 = store.create_job(
            name="Scan", nas_connection_id=connection["id"],
            interval="1h", paths=["/b"],
        )
        assert job1["slug"] == "scan"
        assert job2["slug"] == "scan-2"

    def test_get_by_slug_or_name(self, store, connection):
        store.create_job(
            name="Mein Scan", nas_connection_id=connection["id"],
            interval="1h", paths=["/a"],
        )
        assert store.get_job("mein-scan")["name"] == "Mein Scan"
        assert store.get_job("Mein Scan")["slug"] == "mein-scan"
        assert store.get_job("gibts-nicht") is None

    def test_update_slug_immutable(self, store, connection):
        job = store.create_job(
            name="Alt", nas_connection_id=connection["id"],
            interval="1h", paths=["/a"],
        )
        updated = store.update_job(
            job["slug"],
            name="Ganz Neuer Name",
            nas_connection_id=connection["id"],
            interval="12h",
            enabled=False,
            paths=["/a", "/b"],
        )
        assert updated["slug"] == "alt"  # unverändert -> Historie bleibt intakt
        assert updated["name"] == "Ganz Neuer Name"
        assert updated["enabled"] is False
        assert updated["paths"] == ["/a", "/b"]

    def test_delete(self, store, connection):
        job = store.create_job(
            name="Weg", nas_connection_id=connection["id"],
            interval="1h", paths=["/a"],
        )
        store.delete_job(job["slug"])
        assert store.get_job("weg") is None
        with pytest.raises(NotFoundError):
            store.delete_job("weg")

    def test_create_with_missing_connection(self, store):
        with pytest.raises(NotFoundError):
            store.create_job(
                name="X", nas_connection_id=42, interval="1h", paths=["/a"]
            )


class TestToScanConfig:
    def test_builds_full_config_with_decrypted_password(self, store, connection):
        job = store.create_job(
            name="Mein Scan",
            nas_connection_id=connection["id"],
            interval="0 3 * * *",
            paths=["/homes", "/backup"],
        )
        config = store.to_scan_config(job)
        assert config.slug == "mein-scan"
        assert config.nas.host == "192.168.1.10"
        assert config.nas.password == "geheim"  # entschlüsselt
        assert config.nas.port == 5001
        assert config.paths == ["/homes", "/backup"]
        assert config.interval == "0 3 * * *"

    def test_shares_folders_preserved(self, store, connection):
        job = store.create_job(
            name="Share Scan",
            nas_connection_id=connection["id"],
            interval="6h",
            shares=["homes"],
            folders=["alice", "bob"],
        )
        config = store.to_scan_config(job)
        assert config.shares == ["homes"]
        assert config.folders == ["alice", "bob"]

