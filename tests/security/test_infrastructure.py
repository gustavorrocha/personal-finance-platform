from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "infra/compose.yaml").read_text())


def test_tmpfs_mount_options_stay_in_a_single_absolute_mount():
    for name, size in (("api", "32m"), ("web", "32m"), ("ollama", "64m")):
        mounts = COMPOSE["services"][name]["tmpfs"]
        assert len(mounts) == 1, f"{name}: YAML split the mount at its option commas"
        target, options = mounts[0].split(":", maxsplit=1)
        assert target == "/tmp"
        assert set(options.split(",")) == {"rw", "noexec", "nosuid", f"size={size}"}
    for mount in COMPOSE["services"]["restore"]["tmpfs"]:
        assert mount.split(":", maxsplit=1)[0].startswith("/")


def test_private_networks_and_only_loopback_publications():
    assert set(COMPOSE["networks"]) == {"frontend", "data", "ai", "egress", "recovery"}
    for name in ("data", "ai", "egress", "recovery"):
        assert COMPOSE["networks"][name]["internal"]
    frontend = COMPOSE["networks"]["frontend"]
    assert not frontend.get("internal", False)
    assert frontend["driver_opts"] == {
        "com.docker.network.bridge.enable_ip_masquerade": "false",
        "com.docker.network.bridge.host_binding_ipv4": "127.0.0.1",
    }
    for name, service in COMPOSE["services"].items():
        assert "network_mode" not in service
        assert "privileged" not in service
        assert set(service["networks"]) <= set(COMPOSE["networks"])
        assert "egress" not in service["networks"]
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:")
            assert name in {"api", "web"}
    for name in ("clickhouse", "ollama", "restore"):
        assert not COMPOSE["services"][name].get("ports")
    assert COMPOSE["services"]["web"]["networks"] == ["frontend"]
    assert COMPOSE["services"]["clickhouse"]["networks"] == ["data"]
    assert COMPOSE["services"]["ollama"]["networks"] == ["ai"]
    assert COMPOSE["services"]["api"]["networks"] == ["frontend", "data", "ai"]
    assert COMPOSE["services"]["restore"]["networks"] == ["recovery"]


def test_non_root_no_capabilities_and_no_docker_socket():
    for name, service in COMPOSE["services"].items():
        assert service["user"].split(":")[0] not in {"0", "root"}
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["mem_limit"]
        assert service["pids_limit"] <= (512 if name == "clickhouse" else 256)
        assert "docker.sock" not in str(service)


def test_secrets_are_files_and_no_remote_ai():
    assert set(COMPOSE["services"]["api"]["secrets"]) == {"api_password", "dashboard_password"}
    assert {
        "source": "dashboard_user",
        "target": "/etc/clickhouse-server/users.d/market-rates-dashboard.xml",
    } in COMPOSE["services"]["clickhouse"]["secrets"]
    assert all(
        s["file"].startswith("${FINANCE_PRIVATE_DIR}/secrets/") for s in COMPOSE["secrets"].values()
    )
    assert COMPOSE["services"]["ollama"]["environment"]["OLLAMA_NO_CLOUD"] == "1"
    assert "environment" not in COMPOSE["services"]["clickhouse"]
    assert not COMPOSE.get("volumes")


def test_optional_gui_exposes_only_the_loopback_http_proxy():
    override = yaml.safe_load((ROOT / "infra/compose.gui.yaml").read_text())
    assert "ports" not in override["services"]["clickhouse"]
    assert "networks" not in override["services"]["clickhouse"]
    proxy = override["services"]["clickhouse-gui"]
    assert proxy["ports"] == ["127.0.0.1:8123:8080"]
    assert proxy["networks"] == ["gui", "data"]
    assert proxy["read_only"] and proxy["cap_drop"] == ["ALL"]
    assert "clickhouse-gui" not in COMPOSE["services"]


def test_recovery_override_only_changes_clickhouse_storage():
    override = yaml.safe_load((ROOT / "infra/compose.volume.yaml").read_text())
    assert override["services"] == {
        "clickhouse": {"volumes": ["clickhouse-storage:/var/lib/clickhouse"]}
    }
    assert override["volumes"]["clickhouse-storage"]["external"] is True


def test_clickhouse_local_admin_and_no_sensitive_query_logs():
    users = ElementTree.parse(ROOT / "infra/clickhouse/users.d/local.xml")
    networks = users.findall("./users/default/networks/ip")
    assert {ip.text for ip in networks} == {"127.0.0.1", "::1"}
    config = ElementTree.parse(ROOT / "infra/clickhouse/config.d/local.xml")
    for name in ("query_log", "query_thread_log", "text_log", "trace_log", "crash_log"):
        assert config.find(name).get("remove") == "1"
    assert users.find("./profiles/health/readonly").text == "1"


def test_single_database_engine_and_versioned_migration():
    images = [s["image"] for s in COMPOSE["services"].values() if "image" in s]
    assert all(image.startswith(("clickhouse/", "ollama/")) for image in images)
    sql = (ROOT / "infra/migrations/0001_foundation.sql").read_text()
    for database in ("core", "analytics", "metadata"):
        assert f"CREATE DATABASE IF NOT EXISTS {database};" in sql
    assert "Decimal(18, 2)" in sql
    assert "DateTime64(3, 'UTC')" in sql
    assert "bronze_objects" not in sql
