"""`keel hooks list`."""

from __future__ import annotations

import typer
from rich.table import Table

from keel.api import Output
from keel.hooks.hookable import registered_events
from keel.hooks.registry import _REGISTRY, iter_matching_subscribers


def cmd_list(
    ctx: typer.Context,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """List all events keel commands can fire, along with subscribers."""
    out = Output.from_context(ctx, json_mode=json_mode)

    # Trigger plugin entry-point load so we see plugin subscribers too.
    from keel.hooks.dispatcher import _ensure_plugins_loaded

    _ensure_plugins_loaded()

    # Also register the built-in pre-phase listeners (idempotent).
    from keel.hooks.builtin_listeners import register_builtin_listeners

    register_builtin_listeners()

    events = sorted(registered_events())
    payload: dict[str, dict] = {}
    for event_base in events:
        pre_subs = [_fmt_subscriber(s) for s in iter_matching_subscribers(f"{event_base}.pre")]
        post_subs = [_fmt_subscriber(s) for s in iter_matching_subscribers(f"{event_base}.post")]
        payload[event_base] = {
            "pre_subscribers": pre_subs,
            "post_subscribers": post_subs,
        }
    # Also surface any extra subscribers for events that aren't in registered_events
    # (e.g. plugins subscribing to events keel-cli doesn't fire).
    # A registered key like "project.create.pre" has event_base = "project.create";
    # strip the last segment to get the event_base.
    known_bases = set(events)
    extra_keys = set()
    for k in _REGISTRY:
        parts = k.rsplit(".", 1)
        if len(parts) == 2 and parts[0] not in known_bases:
            extra_keys.add(k)
    extra_subs = {k: [_fmt_subscriber(s) for s in _REGISTRY[k]] for k in extra_keys}

    if json_mode:
        out.result(
            {
                "events": payload,
                "extra_subscribers": extra_subs,
            }
        )
        return

    table = Table()
    table.add_column("Event")
    table.add_column("Pre subscribers")
    table.add_column("Post subscribers")
    for event_base in events:
        e = payload[event_base]
        table.add_row(
            event_base,
            "\n".join(e["pre_subscribers"]) or "—",
            "\n".join(e["post_subscribers"]) or "—",
        )
    out.print_rich(table)
    if extra_subs:
        out.info(
            "Note: plugin subscribers registered for events not fired by built-in commands: "
            + ", ".join(sorted(extra_subs.keys()))
        )


def _fmt_subscriber(fn) -> str:
    """Format a subscriber callable as 'module.qualname'."""
    mod = getattr(fn, "__module__", "?")
    name = getattr(fn, "__qualname__", getattr(fn, "__name__", "?"))
    return f"{mod}.{name}"
