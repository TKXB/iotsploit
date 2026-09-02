from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_container_build_uses_checkout_and_installs_required_network_tools():
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "COPY . /app/" in dockerfile
    assert "git clone" not in dockerfile
    for package in (
        "iproute2",
        "nmap",
        "util-linux",
        "libcairo2-dev",
        "libdbus-1-dev",
        "libgirepository1.0-dev",
        "pkg-config",
    ):
        assert package in dockerfile
    assert "/usr/local/libexec/iotsploit-privd" in dockerfile
    assert "/usr/local/libexec/iotsploit-run-cap" in dockerfile


def test_supervisor_launches_every_service_through_a_fixed_profile():
    supervisor = (ROOT / "docker/supervisord.conf").read_text()

    assert "run-cap admin /usr/local/libexec/iotsploit-privd" in supervisor
    assert "run-cap raw python -m daphne" in supervisor
    assert "run-cap bind /usr/sbin/nginx" in supervisor
    assert "interface=127.0.0.1" in supervisor
    assert "interface=0.0.0.0" not in supervisor


def test_launcher_drops_bootstrap_capabilities_from_each_child_profile():
    launcher = (ROOT / "docker/run-with-capability.sh").read_text()

    assert "eval" not in launcher
    assert "--bounding-set=-all,+net_admin" in launcher
    assert "--bounding-set=-all,+net_raw" in launcher
    assert "--bounding-set=-all,+net_bind_service" in launcher
    assert "--bounding-set=-all" in launcher
    assert launcher.count("--no-new-privs") == 4
    assert "+setuid" not in launcher.lower()
    assert "+setgid" not in launcher.lower()
    assert "+setpcap" not in launcher.lower()


def test_compose_does_not_publish_backend_or_give_workers_net_admin():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "8888:8888" not in compose
    assert "9999:9999" not in compose
    worker_sections = compose.split("  celery:", 1)[1]
    assert "NET_ADMIN" not in worker_sections
    assert "run-cap raw python -m celery" in worker_sections
    assert "/run/iotsploit" not in worker_sections


def test_nginx_runs_without_root_owned_runtime_paths():
    nginx = (ROOT / "docker/nginx-main.conf").read_text()

    assert "user " not in nginx
    assert "pid /run/iotsploit-nginx/nginx.pid;" in nginx
    assert "error_log /app/logs/nginx/error.log;" in nginx
    assert "_temp_path /var/cache/iotsploit-nginx/" in nginx
