"""P14-5: delivery files are present and safe. Static checks only: no Docker, no cloud, no network.

These tests prove the files are well formed. They do NOT prove anything is deployed.
"""

import pathlib
import re
import subprocess

import pytest
from app.core.config import Settings

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_DOCKERFILE = ROOT / "backend" / "Dockerfile"
FRONTEND_DOCKERFILE = ROOT / "frontend" / "Dockerfile"


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return out.stdout.splitlines()


# ---------------------------------------------------------------- Dockerfiles


@pytest.mark.parametrize("path", [BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE], ids=["backend", "frontend"])
def test_dockerfile_runs_as_non_root_with_a_healthcheck(path):
    text = path.read_text(encoding="utf-8")
    runtime = text.split("AS runtime", 1)[1]  # only the final stage matters
    assert re.search(r"^USER\s+(?!root\b)\S+", runtime, re.MULTILINE), "final stage must set a non-root USER"
    assert "HEALTHCHECK" in runtime


def test_dockerfiles_use_multi_stage_builds_and_no_latest_app_images():
    for path in (BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE):
        text = path.read_text(encoding="utf-8")
        assert text.count("\nFROM ") + text.startswith("FROM ") >= 2, path.name
        assert "COPY . ." not in text or path is FRONTEND_DOCKERFILE  # backend never copies the repo
    assert "python:3.12-slim" in BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "node:22-alpine" in FRONTEND_DOCKERFILE.read_text(encoding="utf-8")


def test_healthchecks_target_the_documented_routes():
    assert "/health/live" in BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "/api/health" in FRONTEND_DOCKERFILE.read_text(encoding="utf-8")


def test_frontend_uses_standalone_output():
    assert 'output: "standalone"' in (ROOT / "frontend" / "next.config.mjs").read_text(encoding="utf-8")


# ---------------------------------------------------------------- Compose


@pytest.fixture(scope="module")
def compose():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_compose_has_the_four_services(compose):
    assert set(compose["services"]) == {"frontend", "backend", "redis", "qdrant"}


def test_compose_start_order_waits_for_healthy_dependencies(compose):
    services = compose["services"]
    assert services["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"
    for dep in ("redis", "qdrant"):
        assert services["backend"]["depends_on"][dep]["condition"] == "service_healthy"
    for name, service in services.items():
        assert service["restart"] == "unless-stopped", name
        assert "healthcheck" in service, name


def test_compose_uses_named_volumes_and_no_inline_real_secrets(compose):
    assert set(compose["volumes"]) == {"redis-data", "qdrant-data", "backend-data"}
    env = compose["services"]["backend"]["environment"]
    assert env["JWT_SECRET"].startswith("${JWT_SECRET")  # from the shell, with a dev-only fallback
    assert env["LLM_API_KEY"].startswith("${LLM_API_KEY")
    assert env["REDIS_URL"] == "redis://redis:6379/0"  # service name, not localhost


def test_browser_api_url_is_the_published_host_port_not_a_service_name(compose):
    arg = compose["services"]["frontend"]["build"]["args"]["NEXT_PUBLIC_API_URL"]
    assert "localhost:8000" in arg and "backend" not in arg.split(":-")[-1]


# ---------------------------------------------------------------- env and secrets


def test_env_example_lists_every_setting():
    example = ROOT / ".env.example"
    if not example.is_file():
        pytest.skip(".env.example has not been created yet (see the Phase 14 hand-off)")
    names = {
        line.split("=", 1)[0].strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = {n.upper() for n in Settings.model_fields} - {n.upper() for n in names}
    assert not missing, f".env.example is missing {sorted(missing)}"


def test_no_env_file_or_terraform_secret_is_committed():
    forbidden = re.compile(
        r"(^|/)(\.env(\.(?!example$).+)?|terraform\.tfvars|backend\.hcl|tfplan|[^/]+\.tfstate|[^/]+\.db)$"
    )
    bad = [f for f in _tracked_files() if forbidden.search(f)]
    assert not bad, f"secret or state files are tracked: {bad}"


def test_no_real_looking_keys_in_delivery_files():
    pattern = re.compile(r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
    roots = [ROOT / "deployment", ROOT / ".github", ROOT / "docker-compose.yml"]
    for root in roots:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for path in files:
            assert not pattern.search(path.read_text(encoding="utf-8", errors="ignore")), path


# ---------------------------------------------------------------- Terraform and CI


@pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
def test_each_cloud_has_a_root_and_three_environment_var_files(cloud):
    for name in ("main.tf", "variables.tf", "outputs.tf"):
        assert (ROOT / "deployment" / cloud / name).is_file()
    for env in ("dev", "staging", "prod"):
        assert (ROOT / "deployment" / cloud / "environments" / env / "terraform.tfvars.example").is_file()


def test_ci_workflows_exist():
    names = {p.name for p in (ROOT / ".github" / "workflows").glob("*.yml")}
    assert {"test.yml", "security.yml", "docker-build.yml", "terraform-validate.yml", "_deploy.yml"} <= names


def test_deploy_pipeline_requires_prod_reviewers_and_uses_the_git_sha():
    text = (ROOT / ".github" / "workflows" / "_deploy.yml").read_text(encoding="utf-8")
    assert "prod-apply" in text and "github.sha" in text


def test_deploy_script_refuses_auto_approve_outside_dev():
    text = (ROOT / "deployment" / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert '--auto-approve' in text and '"$env" != "dev"' in text
    assert "shell=True" not in text


def test_honest_status_is_not_overclaimed():
    for path in (ROOT / "deployment").rglob("main.tf"):
        text = path.read_text(encoding="utf-8")
        assert "NOT applied" in text, f"{path} must state it is not applied"
