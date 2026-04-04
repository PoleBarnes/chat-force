"""Create GitHub PRs from approved changesets via the gh CLI."""

import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

from pipeline.config import PipelineConfig

log = logging.getLogger(__name__)


def _slugify(text: str, max_len: int = 60) -> str:
    """Lowercase, replace spaces/non-alphanum with hyphens, collapse runs."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_len].rstrip("-")


def _run(cmd: list[str], *, cwd: str | None = None, check: bool = True) -> str:
    """Run a subprocess and return stripped stdout. Raises on failure."""
    log.debug("$ %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


class PRCreator:
    """Creates a GitHub PR from an approved changeset using the gh CLI."""

    def __init__(self, config: PipelineConfig, run_id: str):
        self.config = config
        self.run_id = run_id

    # -- public API -----------------------------------------------------------

    def create(self, changeset: dict, verdict: dict) -> str:
        """Create a PR with the approved files. Returns the PR URL.

        *changeset* is the bundle from ChangesetExtractor.extract().
        *verdict* is the Mechanic's decision dict containing:
            - pr_title, pr_body
            - files_to_include (list of relative paths)
        """
        pr_title = verdict.get("pr_title", f"Auto: {changeset.get('task', 'update')}")
        pr_body = verdict.get("pr_body", "Automated PR created by the pipeline.")
        files_to_include = verdict.get("files_to_include", [])

        if not files_to_include:
            raise ValueError("Verdict has no files_to_include -- nothing to PR")

        branch = self._make_branch_name(pr_title)
        file_contents = changeset.get("git_changes", {}).get("file_contents", {})
        container_id = changeset.get("worker_container")
        tmp_dir = tempfile.mkdtemp(prefix=f"pr-{self.run_id}-")

        try:
            # 1. Clone the repo into a temp directory
            repo_url = self.config.config_repo_url
            log.info("[%s] Cloning %s into temp dir", self.run_id, repo_url)
            _run(["git", "clone", "--depth=1", repo_url, tmp_dir])

            # 2. Create and checkout the branch
            log.info("[%s] Creating branch %s", self.run_id, branch)
            _run(["git", "checkout", "-b", branch], cwd=tmp_dir)

            # 3. Copy each approved file into the checkout
            for fpath in files_to_include:
                self._write_file(tmp_dir, fpath, file_contents, container_id)

            # 3b. Remove deleted files from the checkout
            deleted_files = changeset.get("git_changes", {}).get("deleted_files", [])
            for fpath in deleted_files:
                target = os.path.join(tmp_dir, fpath)
                if os.path.exists(target):
                    _run(["git", "rm", fpath], cwd=tmp_dir)
                    log.debug("Deleted %s from PR branch", fpath)

            # 4. Stage, commit, push
            _run(["git", "add", "-A"], cwd=tmp_dir)

            # Check if there's anything to commit
            status = _run(["git", "status", "--porcelain"], cwd=tmp_dir)
            if not status:
                raise RuntimeError("No changes staged after copying files -- nothing to commit")

            _run(
                [
                    "git", "commit",
                    "-m", f"{pr_title}\n\nRun: {self.run_id}\n\nAutomated by chat-force pipeline.",
                ],
                cwd=tmp_dir,
            )
            _run(["git", "push", "-u", "origin", branch], cwd=tmp_dir)

            # 5. Create the PR via gh
            log.info("[%s] Creating PR: %s", self.run_id, pr_title)
            pr_url = _run(
                [
                    "gh", "pr", "create",
                    "--repo", self.config.github_repo,
                    "--base", "main",
                    "--head", branch,
                    "--title", pr_title,
                    "--body", pr_body,
                ],
                cwd=tmp_dir,
            )

            log.info("[%s] PR created: %s", self.run_id, pr_url)
            return pr_url

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # -- internals ------------------------------------------------------------

    def _make_branch_name(self, title: str) -> str:
        """Return a branch name like ``agent-sdk/auto/20260402-153022-refactor-auth``."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        slug = _slugify(title)
        return f"{self.config.pr_branch_prefix}/{ts}-{slug}"

    def _write_file(
        self,
        checkout_dir: str,
        fpath: str,
        file_contents: dict,
        container_id: str | None,
    ) -> None:
        """Write a single file into the temp checkout.

        Tries the in-memory file_contents dict first; falls back to
        ``docker cp`` from the worker container if the content isn't cached.
        """
        dest = os.path.join(checkout_dir, fpath)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        # Prefer content already in the changeset bundle
        if fpath in file_contents:
            log.debug("Writing %s from changeset bundle", fpath)
            with open(dest, "w") as f:
                f.write(file_contents[fpath])
            return

        # Fallback: docker cp from the worker container
        if container_id:
            log.info("File %s not in bundle -- falling back to docker cp", fpath)
            src = f"{container_id}:/workspace/config/{fpath}"
            try:
                _run(["docker", "cp", src, dest])
                return
            except RuntimeError:
                log.warning("docker cp failed for %s", fpath)

        raise FileNotFoundError(
            f"Cannot obtain content for {fpath}: "
            "not in changeset bundle and docker cp unavailable or failed"
        )
