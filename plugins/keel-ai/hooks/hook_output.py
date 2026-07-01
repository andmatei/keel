#!/usr/bin/env python3
"""Emit a Claude Code hook JSON response with additionalContext from stdin."""

import json
import sys


def main() -> None:
    text = sys.stdin.read()
    if not text.strip():
        sys.exit(0)
    output = {"hookSpecificOutput": {"additionalContext": text}}
    json.dump(output, sys.stdout)
    print()


if __name__ == "__main__":
    main()
