from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from dopie.shared_folder import shared_folder_transaction


def test_nested_transactions_hold_the_lock_until_the_outer_operation_finishes(tmp_path):
    path = tmp_path / ".configuration.lock"
    attempted = Event()
    acquired = Event()

    def change_configuration():
        attempted.set()
        with shared_folder_transaction(path):
            acquired.set()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with shared_folder_transaction(path):
            with shared_folder_transaction(path):
                operation = executor.submit(change_configuration)
                assert attempted.wait(5)
            assert not acquired.wait(0.1)
        operation.result(timeout=5)
    assert acquired.is_set()


def test_transactions_release_after_an_operation_fails(tmp_path):
    path = tmp_path / ".configuration.lock"
    with pytest.raises(ValueError, match="failed"):
        with shared_folder_transaction(path):
            raise ValueError("failed")

    with ThreadPoolExecutor(max_workers=1) as executor:
        def change_configuration():
            with shared_folder_transaction(path):
                return "saved"

        assert executor.submit(change_configuration).result(timeout=5) == "saved"


def test_separate_processes_wait_for_the_transaction_to_finish(tmp_path):
    path = tmp_path / ".configuration.lock"
    acquired = tmp_path / "acquired"
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from dopie.shared_folder import shared_folder_transaction\n"
        "print('waiting', flush=True)\n"
        "with shared_folder_transaction(Path(sys.argv[1])):\n"
        "    Path(sys.argv[2]).write_text('saved')\n"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "application" / "base" / "src")
    process = None
    try:
        with shared_folder_transaction(path):
            process = subprocess.Popen(
                [sys.executable, "-c", script, str(path), str(acquired)],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert process.stdout.readline().strip() == "waiting"
            with pytest.raises(subprocess.TimeoutExpired):
                process.communicate(timeout=0.1)
            assert not acquired.exists()
        _, errors = process.communicate(timeout=5)
        assert process.returncode == 0, errors
        assert acquired.read_text() == "saved"
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_an_exited_process_releases_its_lock_without_deleting_the_lock_file(tmp_path):
    path = tmp_path / ".configuration.lock"
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from dopie.shared_folder import shared_folder_transaction\n"
        "with shared_folder_transaction(Path(sys.argv[1])):\n"
        "    print('locked', flush=True)\n"
        "    sys.stdin.read()\n"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "application" / "base" / "src")
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(path)],
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "locked"
        process.kill()
        process.communicate(timeout=5)
        with shared_folder_transaction(path):
            assert path.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
