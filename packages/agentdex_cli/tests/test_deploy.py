"""test_deploy — Unit tests for the adx deploy command.

Tests:
1. Command parser accepts deploy options.
2. cmd_deploy triggers deploy and polls status successfully (healthy path).
3. cmd_deploy handles deploy failure status (unhealthy/error path) and fetches build logs.
4. cmd_deploy fails when no AI_BUILDER_TOKEN / AI_BUILDERS_KEY is present.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentdex_cli.cli import build_parser, cmd_deploy


def test_deploy_parser_arguments():
    parser = build_parser()
    # Test typical args parsing
    args = parser.parse_args(
        [
            "deploy",
            "--service-name",
            "my-test-service",
            "--repo-url",
            "https://github.com/test/repo",
            "--branch",
            "feature-branch",
            "--env-vars",
            "FOO=bar,BAZ=qux",
            "--token",
            "test-token",
            "--no-poll",
            "--poll-interval",
            "5",
            "--poll-timeout",
            "30",
        ]
    )
    assert args.cmd == "deploy"
    assert args.service_name == "my-test-service"
    assert args.repo_url == "https://github.com/test/repo"
    assert args.branch == "feature-branch"
    assert args.env_vars == "FOO=bar,BAZ=qux"
    assert args.token == "test-token"
    assert args.no_poll is True
    assert args.poll_interval == 5
    assert args.poll_timeout == 30


@patch("httpx.post")
@patch("httpx.get")
@patch("subprocess.check_output")
def test_cmd_deploy_success_path(mock_check_output, mock_get, mock_post, monkeypatch):
    # Setup mocks
    mock_check_output.side_effect = lambda cmd, **kwargs: {
        ("git", "config", "--get", "remote.origin.url"): "https://github.com/origin/repo.git\n",
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main-branch\n",
    }[tuple(cmd)]

    # Mock POST /deployments
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.json.return_value = {
        "status": "queued",
        "message": "Deployment queued",
        "streaming_logs": "building...",
    }
    mock_post.return_value = mock_post_resp

    # Mock GET /deployments/agentdex
    mock_get_resp_1 = MagicMock()
    mock_get_resp_1.status_code = 200
    mock_get_resp_1.json.return_value = {
        "status": "deploying",
        "message": "Deploying container",
    }
    mock_get_resp_2 = MagicMock()
    mock_get_resp_2.status_code = 200
    mock_get_resp_2.json.return_value = {
        "status": "HEALTHY",
        "message": "Deployment succeeded",
        "public_url": "https://agentdex.ai-builders.space",
    }
    mock_get.side_effect = [mock_get_resp_1, mock_get_resp_2]

    # Run command
    monkeypatch.setenv("AI_BUILDER_TOKEN", "fake-token")
    parser = build_parser()
    args = parser.parse_args(["deploy", "--poll-interval", "0"])

    with patch("time.sleep", return_value=None):
        exit_code = cmd_deploy(args)

    assert exit_code == 0
    mock_post.assert_called_once()
    assert mock_get.call_count == 2


@patch("httpx.post")
@patch("httpx.get")
def test_cmd_deploy_failure_path(mock_get, mock_post, monkeypatch):
    # Mock POST /deployments
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.json.return_value = {
        "status": "queued",
        "message": "Deployment queued",
    }
    mock_post.return_value = mock_post_resp

    # Mock GET /deployments/agentdex status check -> fails
    mock_get_status = MagicMock()
    mock_get_status.status_code = 200
    mock_get_status.json.return_value = {
        "status": "ERROR",
        "message": "Deployment crashed",
    }

    # Mock GET /deployments/agentdex/logs
    mock_get_logs = MagicMock()
    mock_get_logs.status_code = 200
    mock_get_logs.json.return_value = {
        "logs": "Traceback: error in starting gateway",
    }
    mock_get.side_effect = [mock_get_status, mock_get_logs]

    # Run command
    monkeypatch.setenv("AI_BUILDER_TOKEN", "fake-token")
    parser = build_parser()
    args = parser.parse_args(
        [
            "deploy",
            "--repo-url",
            "https://github.com/test/repo",
            "--branch",
            "main",
        ]
    )

    exit_code = cmd_deploy(args)

    assert exit_code == 1
    mock_post.assert_called_once()
    assert mock_get.call_count == 2  # one for status check, one for logs


def test_cmd_deploy_fails_if_no_token(monkeypatch):
    monkeypatch.delenv("AI_BUILDER_TOKEN", raising=False)
    monkeypatch.delenv("AI_BUILDERS_KEY", raising=False)

    parser = build_parser()
    args = parser.parse_args(
        [
            "deploy",
            "--repo-url",
            "https://github.com/test/repo",
            "--branch",
            "main",
        ]
    )

    exit_code = cmd_deploy(args)
    assert exit_code == 1


@patch("httpx.post")
@patch("subprocess.check_output")
def test_cmd_deploy_credentials_stripping_and_detached_head(
    mock_check_output, mock_post, monkeypatch
):
    monkeypatch.setenv("AI_BUILDER_TOKEN", "fake-token")
    # Simulate a git remote URL with credentials, and a detached HEAD branch outputting 'HEAD'
    mock_check_output.side_effect = (
        lambda cmd, **kwargs: {
            (
                "git",
                "config",
                "--get",
                "remote.origin.url",
            ): "https://username:secretpassword@github.com/origin/repo.git\n",  # pragma: allowlist secret
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): "HEAD\n",
        }[tuple(cmd)]
    )

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.json.return_value = {
        "status": "queued",
        "message": "Deployment queued",
    }
    mock_post.return_value = mock_post_resp

    parser = build_parser()
    args = parser.parse_args(["deploy", "--no-poll"])
    exit_code = cmd_deploy(args)

    assert exit_code == 0
    mock_post.assert_called_once()
    called_payload = mock_post.call_args[1]["json"]
    # Credentials should be stripped from the URL
    assert called_payload["repo_url"] == "https://github.com/origin/repo.git"
    # Detached HEAD should be treated as main
    assert called_payload["branch"] == "main"
    # port should not be in the payload
    assert "port" not in called_payload


@patch("httpx.post")
@patch("subprocess.check_output")
def test_cmd_deploy_forwards_sidecar_scale_envvars(mock_check_output, mock_post, monkeypatch):
    """OPS-P1-forward-scale-envvars: `adx deploy` must forward the ADX_SIDECAR_*
    sidecar scale knobs (pool size, heap cap, protocol caps) the server reads at
    boot — not just ARENA_*. Without them a scaled deploy silently runs at the
    single-sidecar 96MB defaults. Unrelated env vars must NOT be forwarded.
    """
    mock_check_output.side_effect = lambda cmd, **kwargs: {
        ("git", "config", "--get", "remote.origin.url"): "https://github.com/origin/repo.git\n",
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n",
    }[tuple(cmd)]

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.json.return_value = {"status": "queued", "message": "Deployment queued"}
    mock_post.return_value = mock_post_resp

    monkeypatch.setenv("AI_BUILDER_TOKEN", "fake-token")
    monkeypatch.setenv("ADX_SIDECAR_POOL_SIZE", "4")
    monkeypatch.setenv("ADX_SIDECAR_MAX_OLD_SPACE_MB", "512")
    monkeypatch.setenv("ARENA_MAX_BATTLES", "64")
    # An unrelated var that must NOT be forwarded to the deployed container.
    monkeypatch.setenv("HOME_SECRET_NOT_FORWARDED", "leak")

    parser = build_parser()
    args = parser.parse_args(["deploy", "--no-poll"])
    exit_code = cmd_deploy(args)

    assert exit_code == 0
    env_vars = mock_post.call_args[1]["json"]["env_vars"]
    assert env_vars.get("ADX_SIDECAR_POOL_SIZE") == "4"
    assert env_vars.get("ADX_SIDECAR_MAX_OLD_SPACE_MB") == "512"
    assert env_vars.get("ARENA_MAX_BATTLES") == "64"
    assert "HOME_SECRET_NOT_FORWARDED" not in env_vars
