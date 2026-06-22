"""Contract test: the GA pull-CD deploy webhook signing must match the on-box listener.

The on-box deploy listener (``/opt/agentdex/webhook-listener.py`` on the Lightsail
box ``agentdex-arena-1``, fronting agentdex.builders) verifies every inbound deploy
request with::

    expected = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    hmac.compare_digest(expected, request["X-Hub-Signature-256"])

and only accepts a JSON body ``{"tag": "<[A-Za-z0-9._-]+>"}``.

The CI side (``.github/workflows/ga-deploy.yml`` → "Notify on-box deploy listener")
MUST produce a byte-identical signature over the SAME body bytes, or the box
rejects every deploy with 403 and the arena never updates. There is no shared
module between the YAML and the listener, so this test is the seam that keeps them
honest: it (1) proves the documented CI computation round-trips through the
listener's exact verifier, and (2) asserts the workflow file actually implements
that scheme. A regression in either the scheme or the YAML fails here instead of
silently breaking production deploys.

If you change the scheme, change it in all three places: this test, the workflow
notify step, AND webhook-listener.py ``verify_hmac``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path


# --- the listener's verification + tag rule, copied verbatim as the contract ----
def _listener_verify(secret: bytes, body: bytes, sig_header: str) -> bool:
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header or "")


def _listener_tag_ok(tag: object) -> bool:
    # mirrors webhook-listener.py do_POST() tag validation
    return (
        bool(tag)
        and isinstance(tag, str)
        and tag.replace(".", "").replace("-", "").replace("_", "").isalnum()
    )


# --- the CI side: what ga-deploy.yml's notify step computes ---------------------
def _ci_body(tag: str) -> bytes:
    # printf '{"tag":"%s"}' "$DEPLOY_TAG" — compact, no spaces, no trailing newline
    return (f'{{"tag":"{tag}"}}').encode()


def _ci_signature(secret: str, body: bytes) -> str:
    # "sha256=" + hmac.new(env SECRET .encode(), <stdin body bytes>, sha256).hexdigest()
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------------
# 1. scheme correctness: the CI signature must verify on the box, and only then
# ---------------------------------------------------------------------------------
def test_ci_signature_is_accepted_by_listener() -> None:
    secret = "test-secret-not-a-real-key"
    tag = "0123456789abcdef0123456789abcdef01234567"  # git-sha shape
    body = _ci_body(tag)
    sig = _ci_signature(secret, body)
    assert _listener_verify(secret.encode(), body, sig), (
        "CI-produced signature must pass the on-box verify_hmac"
    )


def test_tampered_body_is_rejected() -> None:
    secret = "test-secret-not-a-real-key"
    sig = _ci_signature(secret, _ci_body("abc123"))
    assert not _listener_verify(secret.encode(), _ci_body("def456"), sig)


def test_wrong_secret_is_rejected() -> None:
    body = _ci_body("abc123")
    sig = _ci_signature("right-secret", body)
    assert not _listener_verify(b"wrong-secret", body, sig)


def test_missing_signature_header_is_rejected() -> None:
    assert not _listener_verify(b"k", _ci_body("abc123"), "")


# ---------------------------------------------------------------------------------
# 2. body / tag shape: the body parses and the tag passes the listener's filter
# ---------------------------------------------------------------------------------
def test_ci_body_is_valid_json_with_expected_tag() -> None:
    body = _ci_body("v1.2.3-rc_4")
    assert json.loads(body) == {"tag": "v1.2.3-rc_4"}
    assert _listener_tag_ok("v1.2.3-rc_4")


def test_git_sha_tag_is_listener_valid() -> None:
    assert _listener_tag_ok("0123456789abcdef0123456789abcdef01234567")


def test_branch_slash_tag_is_rejected_by_listener() -> None:
    # documents WHY the workflow rejects non-[A-Za-z0-9._-] tags before signing:
    # a slash would break both the image ref and the listener's tag filter.
    assert not _listener_tag_ok("feat/branch")


# ---------------------------------------------------------------------------------
# 3. bind the YAML: the workflow file must actually implement the scheme above
# ---------------------------------------------------------------------------------
def _workflow_text() -> str:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".github" / "workflows" / "ga-deploy.yml"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    raise AssertionError("ga-deploy.yml not found walking up from the test file")


def test_workflow_implements_the_contract() -> None:
    wf = _workflow_text()
    # endpoint + auth header + signature scheme
    assert "https://agentdex.builders/webhook/deploy" in wf
    assert "X-Hub-Signature-256" in wf
    assert "sha256=" in wf
    assert "hashlib.sha256" in wf and "hexdigest()" in wf
    # secret is read from env, not interpolated into the shell
    assert "ADX_WEBHOOK_SECRET: ${{ secrets.ADX_WEBHOOK_SECRET }}" in wf
    assert 'os.environ["ADX_WEBHOOK_SECRET"]' in wf
    # the body shape we sign + send
    assert '{"tag":"%s"}' in wf
    assert "--data-raw" in wf
    # success is exactly 202 (async accept)
    assert '"$CODE" != "202"' in wf or '!= "202"' in wf
    # builds + pushes the image the box pulls
    assert "ghcr.io/good-night-oppie/agentdex-arena" in wf


def test_workflow_skips_deploy_when_secret_absent() -> None:
    # pre-cutover safety: image still builds/pushes; deploy is a clean no-op.
    wf = _workflow_text()
    assert 'if [ -z "${ADX_WEBHOOK_SECRET:-}" ]; then' in wf
