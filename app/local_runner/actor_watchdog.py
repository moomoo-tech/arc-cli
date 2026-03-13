"""Local runner that watches for review instructions and triggers Aider."""

import json
import subprocess
import time
from pathlib import Path

from config.settings import settings


class ActorWatchdog:
    """Monitors a watch directory for instruction files and dispatches Aider."""

    def __init__(self, watch_dir: str | None = None):
        self.watch_dir = Path(watch_dir or settings.watch_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)

    def poll(self, interval: float = 5.0) -> None:
        """Poll the watch directory for new instruction files."""
        while True:
            for instruction_file in self.watch_dir.glob("*.json"):
                self._process(instruction_file)
            time.sleep(interval)

    def _process(self, instruction_file: Path) -> None:
        """Process a single instruction file and invoke Aider."""
        try:
            data = json.loads(instruction_file.read_text())
            prompt = data.get("prompt", "")
            repo_path = data.get("repo_path", ".")
            if prompt:
                self._run_aider(prompt, repo_path)
            instruction_file.unlink()
        except Exception as e:
            print(f"Error processing {instruction_file}: {e}")

    def _run_aider(self, prompt: str, repo_path: str) -> None:
        """Invoke Aider with the given prompt in the specified repo."""
        subprocess.run(
            ["aider", "--message", prompt],
            cwd=repo_path,
            check=True,
        )
