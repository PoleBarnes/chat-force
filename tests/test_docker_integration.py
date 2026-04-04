"""Real-Docker integration tests.

These tests exercise flows that can only be verified against a real
container — specifically, operations where permissions, ownership, or
user identity matter and cannot be mocked.

Tests are skipped if Docker is not available, so they're safe to run
in environments without a Docker daemon (though CI should provide one).

Run with:
    uv run --python 3.13 --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0",pytest \\
        pytest tests/test_docker_integration.py -v
"""

import time
import pytest

import docker as docker_mod
from docker.errors import DockerException

from pipeline.config import PipelineConfig
from pipeline.worker_manager import WorkerManager


def _docker_available() -> bool:
    try:
        client = docker_mod.from_env()
        client.ping()
        return True
    except (DockerException, Exception):
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker daemon not available",
)


# =========================================================================
# Regression test for non-root chmod bug
# =========================================================================


@pytest.fixture
def nonroot_worker_container():
    """Start a real container that runs as a non-root user, like the real
    Worker Dockerfile. This reproduces the production conditions where
    docker cp writes as root but the container process runs as worker.
    """
    client = docker_mod.from_env()

    # Step 1: build a tiny image with USER worker — this is what matters.
    # We use python:3.13-slim since it's already on the host.
    dockerfile_content = (
        "FROM python:3.13-slim\n"
        "RUN useradd --create-home --shell /bin/sh worker\n"
        "USER worker\n"
        'CMD ["sleep", "300"]\n'
    )

    import io
    import tarfile

    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        df_bytes = dockerfile_content.encode("utf-8")
        info = tarfile.TarInfo(name="Dockerfile")
        info.size = len(df_bytes)
        tar.addfile(info, io.BytesIO(df_bytes))
    tar_stream.seek(0)

    image, _ = client.images.build(
        fileobj=tar_stream,
        custom_context=True,
        tag="chat-force-test-nonroot:latest",
        rm=True,
    )

    container = client.containers.run(
        image="chat-force-test-nonroot:latest",
        detach=True,
        name=f"chat-force-test-nonroot-{int(time.time())}",
        remove=False,
    )

    try:
        # Wait for container to be running.
        for _ in range(30):
            container.reload()
            if container.status == "running":
                break
            time.sleep(0.2)
        else:
            pytest.fail("Container did not reach running state")

        yield container
    finally:
        try:
            container.remove(force=True)
        except Exception:
            pass


def test_send_message_readable_by_non_root_user(tmp_path, nonroot_worker_container):
    """send_message() must write a file that a non-root container user can read.

    REGRESSION TEST: We previously had a bug where `docker cp` wrote
    /tmp/next-message.txt as root, and the subsequent chmod ran as the
    container's default (worker) user, which couldn't chmod a root-owned
    file. The non-root Worker entrypoint then hit PermissionError trying
    to read the file, crashing the session on every follow-up turn.
    """
    container = nonroot_worker_container
    config = PipelineConfig(output_base=str(tmp_path))
    wm = WorkerManager(config, "regression-test")
    wm._container = container

    wm.send_message("hello from the orchestrator")

    # CRITICAL CHECK 1: the worker (non-root) user — which is the DEFAULT
    # user in this container due to USER worker — must be able to READ
    # /tmp/next-message.txt. If chown wasn't run as root, the file is
    # still root-owned and the worker can't read it.
    result = container.exec_run(["cat", "/tmp/next-message.txt"])
    assert result.exit_code == 0, (
        f"Default (worker) user cannot read /tmp/next-message.txt: "
        f"exit={result.exit_code}, output={result.output!r}"
    )
    assert b"hello from the orchestrator" in result.output

    # CRITICAL CHECK 2: the worker user must also be able to UNLINK the
    # file. The real entrypoint does NEXT_MESSAGE_PATH.unlink() after
    # reading. If the file is root-owned, /tmp's sticky bit blocks the
    # unlink even though the worker has read access.
    result = container.exec_run(["rm", "/tmp/next-message.txt"])
    assert result.exit_code == 0, (
        f"Default (worker) user cannot unlink /tmp/next-message.txt: "
        f"exit={result.exit_code}, output={result.output!r}"
    )


def test_send_message_clears_sentinel(tmp_path, nonroot_worker_container):
    """send_message() must clear /tmp/session-complete before writing
    the next message, otherwise wait_for_completion() returns instantly
    on subsequent turns.
    """
    container = nonroot_worker_container

    # Worker user creates the sentinel (simulates what the Stop hook does).
    assert container.exec_run(["touch", "/tmp/session-complete"]).exit_code == 0
    assert container.exec_run(["test", "-f", "/tmp/session-complete"]).exit_code == 0

    config = PipelineConfig(output_base=str(tmp_path))
    wm = WorkerManager(config, "regression-test")
    wm._container = container

    wm.send_message("follow-up message")

    # Sentinel must be gone after send_message.
    result = container.exec_run(["test", "-f", "/tmp/session-complete"])
    assert result.exit_code != 0, (
        "send_message() did not clear the sentinel file — "
        "wait_for_completion() would return instantly on the next call"
    )
