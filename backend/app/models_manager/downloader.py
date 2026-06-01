"""
Git-based model downloader.

clone_or_pull(repo_url, dest_path) → AsyncGenerator[str, None]

Streams progress lines while cloning or pulling a git repo.
Yields short status strings suitable for SSE or WebSocket streaming.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator

from app.core import git_safe

logger = logging.getLogger(__name__)


async def clone_or_pull(
    repo_url: str,
    dest_path: str | Path,
    do_pull: bool = True,
) -> AsyncGenerator[str, None]:
    """
    Async generator that clones repo_url into dest_path (if not present)
    or runs git pull (if dest_path already exists and do_pull=True).

    Yields progress / status lines as strings.
    Raises RuntimeError on git failure.
    """
    dest = Path(dest_path)

    if dest.exists() and (dest / ".git").exists():
        if not do_pull:
            yield f"already_installed:{dest}"
            return
        cmd = ["git", "-C", str(dest), "pull", "--ff-only"]
        action = "pull"
    else:
        dest.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", "--progress", repo_url, str(dest)]
        action = "clone"

    yield f"starting_{action}"

    try:
        proc = await asyncio.create_subprocess_exec(
            *git_safe(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "git not found. Install git and make sure it is in PATH."
        )

    assert proc.stdout is not None
    async for raw_line in proc.stdout:
        line = raw_line.decode(errors="replace").rstrip()
        if line:
            yield line

    returncode = await proc.wait()
    if returncode != 0:
        raise RuntimeError(f"git {action} failed (exit code {returncode})")

    yield f"done_{action}"


async def get_installed_version(repo_path: str | Path) -> str | None:
    """Returns the current HEAD commit hash (short) or None if not a git repo."""
    path = Path(repo_path)
    if not (path / ".git").exists():
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            *git_safe(["git", "-C", str(path), "rev-parse", "--short", "HEAD"]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return stdout.decode().strip() or None
    except Exception:
        return None


async def check_for_updates(repo_path: str | Path) -> bool:
    """
    Returns True if remote has commits ahead of local HEAD.
    Runs git fetch first (requires network access).
    """
    path = Path(repo_path)
    if not (path / ".git").exists():
        return False
    try:
        fetch = await asyncio.create_subprocess_exec(
            *git_safe(["git", "-C", str(path), "fetch", "--quiet"]),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(fetch.wait(), timeout=15.0)

        proc = await asyncio.create_subprocess_exec(
            *git_safe(["git", "-C", str(path), "rev-list", "HEAD..@{u}", "--count"]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        count = int(stdout.decode().strip() or "0")
        return count > 0
    except Exception:
        return False
