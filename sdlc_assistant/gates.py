"""Human-in-the-loop approval gates."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Decision:
    action: str  # "approve" | "revise" | "edit" | "reject"
    feedback: str = ""
    edited: Any = None


class AutoApprove:
    """Approves every gate. For demos, CI and batch evaluation — not for real use."""

    def review(self, gate: str, title: str, body: str, data: Any, allow_revise: bool = True) -> Decision:
        print(f"\n[{gate}] {title}: auto-approved")
        return Decision("approve")


def _editor_command() -> list[str]:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return shlex.split(editor, posix=os.name != "nt")
    if os.name == "nt":
        return ["notepad"]
    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return [candidate]
    return []


class ConsoleGate:
    """Pauses the pipeline, shows the artifact, and waits for a human decision."""

    def __init__(self, ask: Callable[[str], str] = input):
        self.ask = ask

    def _choose(self, allow_revise: bool) -> str:
        options = "[a]pprove"
        if allow_revise:
            options += "  [r]evise with feedback  [e]dit JSON"
        options += "  [x] reject and stop"
        valid = {"a": "approve", "x": "reject"}
        if allow_revise:
            valid.update({"r": "revise", "e": "edit"})
        while True:
            reply = self.ask(f"\n{options}\n> ").strip().lower()[:1]
            if reply in valid:
                return valid[reply]
            print("Please type one of the letters shown.")

    def _edit(self, data: Any) -> Any | None:
        command = _editor_command()
        if not command:
            print("No text editor found. Set the EDITOR environment variable, or choose revise instead.")
            return None
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            path = fh.name
        try:
            subprocess.call(command + [path])
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as err:
            print(f"That edit isn't valid JSON ({err}); keeping the original.")
            return None
        finally:
            os.unlink(path)

    def review(self, gate: str, title: str, body: str, data: Any, allow_revise: bool = True) -> Decision:
        bar = "=" * 72
        print(f"\n{bar}\n{gate.upper()} — {title}\n{bar}\n{body}")
        if not sys.stdin.isatty() and self.ask is input:
            raise RuntimeError("Approval gates need an interactive terminal. Use --auto-approve for unattended runs.")
        while True:
            action = self._choose(allow_revise)
            if action == "revise":
                feedback = self.ask("What should change? (answers to open questions go here too)\n> ").strip()
                if feedback:
                    return Decision("revise", feedback=feedback)
                print("Feedback was empty.")
                continue
            if action == "edit":
                edited = self._edit(data)
                if edited is not None:
                    return Decision("edit", edited=edited)
                continue
            return Decision(action)
