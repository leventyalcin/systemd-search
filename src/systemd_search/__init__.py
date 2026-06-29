"""systemd-search — Query systemd units by custom section labels.

Relies on `systemctl cat` for effective unit config (handles .d/ drop-ins).
"""

import argparse
import configparser
import json
import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def list_unit_files(types):
    """Return [(unit_name, enabled_state)] for the given unit types."""
    args = ["systemctl", "list-unit-files", "--no-legend", "--no-pager"]
    if types:
        args.append("--type=" + ",".join(types))
    result = run(args)
    units = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            units.append((parts[0], parts[1]))
    return units


def parse_cat_output(output):
    """Parse systemctl cat output into {section: {key: value}}.

    Uses configparser so the full INI grammar is handled correctly.
    strict=False lets duplicate sections (base file + drop-ins) merge and
    duplicate keys resolve to the last definition, matching systemd semantics.
    delimiters=('=',) avoids treating ':' as a separator (systemd never does).
    optionxform=str preserves key casing.
    """
    parser = configparser.RawConfigParser(
        strict=False,
        delimiters=("=",),
    )
    parser.optionxform = str  # preserve key case (e.g. ExecStart, not execstart)
    parser.read_string(output)
    return {section: dict(parser.items(section)) for section in parser.sections()}


def get_unit_config(unit):
    result = run(["systemctl", "cat", "--", unit])
    if result.returncode != 0:
        return {}
    return parse_cat_output(result.stdout)


def is_active(unit):
    result = run(["systemctl", "is-active", "--", unit])
    return result.stdout.strip() == "active"


def build_parser():
    p = argparse.ArgumentParser(
        prog="systemd-search",
        description="Query systemd units by custom section labels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  systemd-search --label Project
  systemd-search --verbose --label Project
  systemd-search --label Project=myapp
  systemd-search --label Project=myapp --type service --type timer
  systemd-search --label Project=myapp --type service --enabled
  systemd-search --label Project=myapp --type service --enabled --active
  systemd-search --label Project=myapp --type service --disabled --dead
  systemd-search --label Project=myapp --exclude Domain
  systemd-search --label Project=myapp --exclude Env=staging --type service --enabled
""",
    )
    p.add_argument(
        "--section",
        default="X-Labels",
        metavar="SECTION",
        help="Unit file section to inspect (default: X-Labels)",
    )
    p.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="KEY[=VALUE]",
        help="Filter by label key, or key=value. Repeatable (all must match).",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="KEY[=VALUE]",
        help=(
            "Exclude units where KEY exists, or where KEY=VALUE matches. "
            "Repeatable. Units that lack the section entirely are always excluded."
        ),
    )
    p.add_argument(
        "--type",
        action="append",
        default=[],
        dest="unit_types",
        metavar="TYPE",
        help="Unit type to include (default: service). Repeatable.",
    )

    state = p.add_argument_group("state filters")
    enabled_grp = state.add_mutually_exclusive_group()
    enabled_grp.add_argument(
        "--enabled", action="store_true", default=False, help="Only enabled units"
    )
    enabled_grp.add_argument(
        "--disabled", action="store_true", default=False, help="Only disabled units"
    )

    active_grp = state.add_mutually_exclusive_group()
    active_grp.add_argument(
        "--active", action="store_true", default=False, help="Only active (running) units"
    )
    active_grp.add_argument(
        "--dead", action="store_true", default=False, help="Only inactive/dead units"
    )

    output_grp = p.add_mutually_exclusive_group()
    output_grp.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Print matched label key=value pairs alongside unit name",
    )
    output_grp.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit results as a JSON array with name, enabled, is-active, and labels",
    )
    return p


def parse_label_filters(raw_labels):
    """Return [(key, value_or_None)] from raw --label arguments."""
    filters = []
    for item in raw_labels:
        if "=" in item:
            k, _, v = item.partition("=")
            filters.append((k.strip(), v.strip()))
        else:
            filters.append((item.strip(), None))
    return filters


def section_matches(section_data, label_filters):
    """Return True if section_data satisfies all label_filters."""
    for key, value in label_filters:
        if key not in section_data:
            return False
        if value is not None and section_data[key] != value:
            return False
    return True


def section_excluded(section_data, exclude_filters):
    """Return True if section_data triggers any exclude_filter.

    --exclude KEY   → exclude when KEY is present in the section.
    --exclude KEY=VALUE → exclude when KEY is present and equals VALUE.
    """
    for key, value in exclude_filters:
        if value is None:
            if key in section_data:
                return True
        else:
            if section_data.get(key) == value:
                return True
    return False


def format_json_entry(unit_name, enabled_state, active, section_data):
    """Build one JSON result object."""
    return {
        "name": unit_name,
        "enabled": enabled_state in ENABLED_STATES,
        "is-active": active,
        "labels": dict(section_data),
    }


def format_verbose(unit_name, section_data, label_filters):
    """Build the output line when --verbose is set."""
    if label_filters:
        keys_to_show = [k for k, _ in label_filters]
    else:
        keys_to_show = list(section_data.keys())

    pairs = " ".join(
        f"{k}={section_data[k]}" for k in keys_to_show if k in section_data
    )
    return f"{unit_name}\t{pairs}" if pairs else unit_name


# States that count as "enabled" per systemctl semantics
ENABLED_STATES = {"enabled", "enabled-runtime", "static", "alias", "generated", "transient"}
DISABLED_STATES = {"disabled", "masked", "masked-runtime", "indirect"}


def main():
    parser = build_parser()
    args = parser.parse_args()

    unit_types = args.unit_types if args.unit_types else ["service"]
    label_filters = parse_label_filters(args.label)
    exclude_filters = parse_label_filters(args.exclude)

    units = list_unit_files(unit_types)
    json_results = []
    found = False

    for unit_name, enabled_state in units:
        # --- enabled/disabled filter ---
        if args.enabled and enabled_state not in ENABLED_STATES:
            continue
        if args.disabled and enabled_state not in DISABLED_STATES:
            continue

        # --- section gate (always enforced) ---
        # Units without the section are outside the scope of this tool entirely.
        config = get_unit_config(unit_name)
        if args.section not in config:
            continue
        section_data = config[args.section]

        # --- label / exclude filters ---
        if label_filters and not section_matches(section_data, label_filters):
            continue

        if exclude_filters and section_excluded(section_data, exclude_filters):
            continue

        # --- active/dead filter + active state resolution ---
        # JSON always needs the active state; other modes only fetch it when filtering.
        if args.json or args.active or args.dead:
            active = is_active(unit_name)
            if args.active and not active:
                continue
            if args.dead and active:
                continue
        else:
            active = None

        found = True

        # --- output ---
        if args.json:
            json_results.append(
                format_json_entry(unit_name, enabled_state, active, section_data)
            )
        elif args.verbose:
            print(format_verbose(unit_name, section_data, label_filters))
        else:
            print(unit_name)

    if args.json:
        print(json.dumps(json_results, indent=2))

    if not found:
        sys.exit(1)


if __name__ == "__main__":
    main()
