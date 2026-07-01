#!/usr/bin/env python3
"""Match a keel lifecycle event against resolved triggers and output hook JSON.

Usage: keel ai show-config --json | python3 match_triggers.py <event> <to_status>

Outputs a Claude Code hook JSON response if any triggers match, nothing otherwise.
"""

import json
import sys

ACTION_DESC = {
    "design-sync": lambda t: f"Run /design-sync --{t.get('mode', 'check')}",
    "code-review": lambda t: (
        'Spawn a code-reviewer agent (subagent_type: "superpowers:code-reviewer") '
        "to review the implementation changes on the current branch"
    ),
}


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(0)

    event, to_status = sys.argv[1], sys.argv[2]

    try:
        config = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    resolved = config.get("resolved_triggers", {})

    matching = []
    for trigger in resolved.values():
        if trigger.get("event") != event:
            continue
        when = trigger.get("when")
        if when and when.get("to") and when["to"] != to_status:
            continue
        action = trigger.get("action", "")
        desc_fn = ACTION_DESC.get(action)
        if desc_fn:
            matching.append(desc_fn(trigger))
        else:
            mode = f" --{trigger['mode']}" if trigger.get("mode") else ""
            matching.append(f"Run /{action}{mode}")

    if not matching:
        sys.exit(0)

    entity = "task" if "task" in event else "milestone"
    lines = [f"A keel {entity} status changed to {to_status}. Triggered actions:", ""]
    for i, desc in enumerate(matching, 1):
        lines.append(f"{i}. {desc}")
    lines.append("")
    lines.append("Perform these actions before continuing with the next task.")

    context = "\n".join(lines)
    output = {"hookSpecificOutput": {"additionalContext": context}}
    json.dump(output, sys.stdout)
    print()


if __name__ == "__main__":
    main()
