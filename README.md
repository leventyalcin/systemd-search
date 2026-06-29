# systemd-search

A CLI tool for finding systemd units by custom labels embedded directly in the unit files.

## The problem

Tracking which units belong to which project or domain on a busy system has no good native solution. The usual approach — browsing `/etc/systemd/system/`, grepping file contents, running `systemctl cat` on anything suspicious — is slow and error-prone. There is no built-in way to tag a unit and query by that tag.

`systemd-search` fills that gap. Labels are embedded in a dedicated section inside the unit file itself. The tool reads those labels and filters units by them, covering type, enabled state, and active state in a single command.

## How it works — the `X-` section trick

The `systemd.unit(5)` man page explicitly states:

> *Sections whose name is prefixed with `X-` are ignored by systemd.*
> *Such sections can be used by applications to store additional information in the unit files.*

— [systemd.unit(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#%5BUnit%5D%20Section%20Options)

An `[X-Labels]` section (or any `[X-*]` section) can be added to any unit file and systemd will load and run the unit exactly as if that section were not there. `systemd-search` reads those sections and uses them as a lightweight tagging system on top of systemd.

The tool resolves the final merged configuration through `systemctl cat` before reading any labels, so drop-in override files (`.d/*.conf`) are always taken into account — the search never operates on stale or partial file content.

## Example unit file

```ini
# /etc/systemd/system/myapp-worker.service
[Unit]
Description=My Application Worker
After=network.target

[Service]
User=myapp
ExecStart=/opt/myapp/bin/worker
Restart=on-failure

[X-Labels]
Project=myapp
Domain=backend
Component=worker
Environment=production
ManagedBy=ansible

[Install]
WantedBy=multi-user.target
```

Any section name starting with `X-` is valid. The default section `systemd-search` reads is `X-Labels`. A different section can be specified with `--section`.

## Installation

### pip

The simplest installation on any system with Python 3.9+:

```bash
pip install systemd-search
```

For a user-local install without root:

```bash
pip install --user systemd-search
```

### From GitHub Releases

Each release ships a self-contained zipapp executable, native packages, and checksums:

```bash
# Self-contained zipapp — runs on any host with Python 3.9+, no pip needed
curl -LO https://github.com/leventyalcin/systemd-search/releases/latest/download/systemd-search-1.0.0
chmod +x systemd-search-1.0.0
sudo mv systemd-search-1.0.0 /usr/local/bin/systemd-search

# RPM (Rocky Linux 9)
sudo rpm -i systemd-search-1.0.0-rocky9.noarch.rpm

# DEB (Debian 12)
sudo dpkg -i systemd-search-1.0.0-debian12.all.deb

# Verify checksum before installing
sha256sum -c systemd-search-1.0.0-rocky9.noarch.rpm.sha256
```

### Manual

Copy the script to any directory on the system `PATH`:

```bash
sudo cp systemd-search /usr/local/bin/systemd-search
```

**Requirements:** Python 3.9+ with no third-party packages. On Rocky Linux 9 this is the system default Python and requires no additional installation.

## Usage

```text
systemd-search [--section SECTION] [--label KEY[=VALUE]] [--type TYPE]
               [--enabled | --disabled] [--active | --dead] [--verbose]
```

| Flag                  | Default    | Description                                                                 |
|-----------------------|------------|-----------------------------------------------------------------------------|
| `--label KEY`         | —          | Matches units that have this key in the section                             |
| `--label KEY=VALUE`   | —          | Matches units where the key equals the value                                |
| `--exclude KEY`       | —          | Skips units that have this key in the section. Repeatable.                  |
| `--exclude KEY=VALUE` | —          | Skips units where the key equals the value. Repeatable.                     |
| `--section NAME`      | `X-Labels` | Section to read labels from                                                 |
| `--type TYPE`         | `service`  | Unit type to include (`service`, `timer`, `path`, `socket`, …). Repeatable. |
| `--enabled`           | —          | Limits results to enabled units                                             |
| `--disabled`          | —          | Limits results to disabled units                                            |
| `--active`            | —          | Limits results to active (running) units                                    |
| `--dead`              | —          | Limits results to inactive or failed units                                  |
| `--verbose` / `-v`    | —          | Prints matched label key=value pairs alongside each unit name               |

`--enabled` and `--disabled` are mutually exclusive. So are `--active` and `--dead`. Omitting either pair includes all units regardless of that state.

When `--exclude` is active, units that lack the section entirely are silently dropped — the filter only operates on units that carry the section in their configuration.

## Examples

### Find all services that belong to a project

```bash
systemd-search --label Project=myapp
```

```text
myapp-worker.service
myapp-scheduler.service
myapp-cleanup.service
```

### Print the label values alongside each unit name

```bash
systemd-search --verbose --label Project=myapp
```

```text
myapp-worker.service       Project=myapp
myapp-scheduler.service    Project=myapp
myapp-cleanup.service      Project=myapp
```

### Search across multiple unit types

```bash
systemd-search --label Project=myapp --type service --type timer --type path
```

```text
myapp-worker.service
myapp-cleanup.service
myapp-refresh.timer
myapp-trigger.path
```

### Narrow by a specific label and type

```bash
systemd-search --label Component=worker --type service
```

### Find only the running services for a project

```bash
systemd-search --label Project=myapp --type service --enabled --active
```

### Find services that are enabled but not running

Useful for spotting crashed or failed units:

```bash
systemd-search --label Project=myapp --type service --enabled --dead
```

### Find services that are installed but not enabled

```bash
systemd-search --label Project=myapp --disabled
```

### Use a custom section name

Labels do not have to live in `[X-Labels]`. Any `[X-*]` section works:

```ini
[X-Meta]
Project=myapp
Team=platform
```

```bash
systemd-search --section X-Meta --label Team=platform
```

### Match on multiple labels simultaneously

All supplied `--label` filters must match for a unit to appear in the results:

```bash
systemd-search --label Project=myapp --label Environment=production --type service
```

### Exclude units that have a specific key

`--exclude KEY` skips any unit in the section that carries that key, regardless of its value:

```bash
systemd-search --label Project=myapp --exclude Domain
```

Only units labelled with `Project=myapp` that have no `Domain` key are returned.

### Exclude units where a key matches a specific value

`--exclude KEY=VALUE` skips units only when the key exists and holds that exact value. Units where the key is absent or holds a different value still appear:

```bash
systemd-search --label Project=myapp --exclude Env=staging
```

Returns all `myapp` services except those explicitly labelled `Env=staging`.

### Combine positive and negative filters

`--label` and `--exclude` compose freely. All `--label` conditions must hold and no `--exclude` condition must trigger for a unit to appear:

```bash
systemd-search \
  --label Project=myapp \
  --label Domain=backend \
  --exclude Component=worker \
  --exclude Env=staging \
  --type service \
  --enabled
```

Reads as: *services for the myapp backend, enabled, excluding workers and staging instances.*

### Verbose output with multiple label filters

```bash
systemd-search --verbose --label Project=myapp --label Domain=backend
```

```text
myapp-worker.service    Project=myapp Domain=backend
```

## Monitoring integration

`systemd-search --json` produces machine-readable output that can be piped directly into monitoring agents. Any combination of filters can precede it — label filters, state filters, unit types — and the result carries enough context for downstream tools to slice and count however the use case demands.

A few possibilities:

```bash
# All dead services for a project, as JSON
systemd-search --json --label Project=myapp --dead

# Count of enabled-but-dead units across all labelled services
systemd-search --json | jq '[.[] | select(.enabled and (.["is-active"] | not))] | length'

# Feed into a monitoring agent as a metric
systemd-search --json --label Project=myapp | jq '.[] | select(.["is-active"] | not) | .name'
```

The examples below show one way to wire this into three common monitoring agents. They are starting points, not prescriptions.

---

### Telegraf

The `exec` input plugin runs an arbitrary command on a schedule and parses its output as metrics. A small wrapper script calls `systemd-search --json` once per project and uses `jq` to derive all counters from the single result, avoiding repeated invocations. The output is [InfluxDB line protocol](https://docs.influxdata.com/influxdb/v2/reference/syntax/line-protocol/).

**`/usr/local/bin/systemd-search-metrics.sh`**

```bash
#!/bin/bash
# Emits one influx line per project with unit state counts.
# Add or remove projects to match the labels used on this host.

set -euo pipefail

PROJECTS=(myapp payments auth)

for project in "${PROJECTS[@]}"; do
  units=$(systemd-search --json \
    --label Project="$project" \
    --type service --type timer --type path)

  dead=$(    echo "$units" | jq '[.[] | select(.enabled     and (.["is-active"] | not))] | length')
  active=$(  echo "$units" | jq '[.[] | select(.enabled     and  .["is-active"]       )] | length')
  disabled=$(echo "$units" | jq '[.[] | select(.enabled | not)                         ] | length')

  echo "systemd_units,project=${project} dead=${dead}i,active=${active}i,disabled=${disabled}i"
done
```

**`/etc/telegraf/telegraf.d/systemd-search.conf`**

```toml
[[inputs.exec]]
  ## Script must be executable: chmod +x /usr/local/bin/systemd-search-metrics.sh
  commands = ["/usr/local/bin/systemd-search-metrics.sh"]
  timeout = "15s"
  interval = "60s"
  data_format = "influx"
```

The resulting measurement `systemd_units` carries a `project` tag and `dead`/`active`/`disabled` fields. An alert fires when `dead > 0` for any project.

---

### Datadog

The Datadog Agent supports [custom Python checks](https://docs.datadoghq.com/developers/custom_checks/write_agent_check/) that emit arbitrary metrics. The check below calls `systemd-search --json` once per configured project and derives all counters from the single JSON result.

**`/etc/datadog-agent/checks.d/systemd_labels.py`**

```python
import json
import subprocess
from datadog_checks.base import AgentCheck


class SystemdLabelsCheck(AgentCheck):
    __NAMESPACE__ = "systemd"

    def check(self, instance):
        project   = instance["project"]
        section   = instance.get("section", "X-Labels")
        label_key = instance.get("label_key", "Project")
        types     = instance.get("types", ["service"])

        type_args = []
        for t in types:
            type_args += ["--type", t]

        cmd = [
            "systemd-search", "--json",
            "--section", section,
            "--label", f"{label_key}={project}",
        ] + type_args

        result = subprocess.run(cmd, capture_output=True, text=True)
        units = json.loads(result.stdout) if result.returncode == 0 else []

        dead     = sum(1 for u in units if     u["enabled"] and not u["is-active"])
        active   = sum(1 for u in units if     u["enabled"] and     u["is-active"])
        disabled = sum(1 for u in units if not u["enabled"])

        tags = [f"project:{project}"]
        self.gauge("units.dead",     dead,     tags=tags)
        self.gauge("units.active",   active,   tags=tags)
        self.gauge("units.disabled", disabled, tags=tags)
```

**`/etc/datadog-agent/conf.d/systemd_labels.d/conf.yaml`**

```yaml
instances:
  - project: myapp
    types: [service, timer, path]

  - project: payments
    types: [service]

  - project: auth
    section: X-Meta        # override if a different section name is used
    label_key: Application
    types: [service, timer]
```

The check emits `systemd.units.dead`, `systemd.units.active`, and `systemd.units.disabled` with a `project` tag. A monitor on `systemd.units.dead > 0` grouped by `project` covers all labelled projects in a single alert rule.

---

### Dynatrace

Dynatrace ingests custom metrics through its [Metrics Ingest v2 API](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/metric-v2/metric-ingest). A script pushed by a systemd timer calls `systemd-search --json` once per project and uses `jq` to compute all counters before pushing a single batch payload.

**`/usr/local/bin/systemd-search-dynatrace.sh`**

```bash
#!/bin/bash
# Push unit state metrics for labelled projects to Dynatrace Metrics Ingest v2.

set -euo pipefail

DT_URL="${DYNATRACE_URL}"          # e.g. https://abc12345.live.dynatrace.com
DT_TOKEN="${DYNATRACE_API_TOKEN}"  # Ingest Metrics (metrics.ingest) scope required
PROJECTS=(myapp payments auth)

payload=""

for project in "${PROJECTS[@]}"; do
  units=$(systemd-search --json \
    --label Project="$project" \
    --type service --type timer --type path)

  dead=$(    echo "$units" | jq '[.[] | select(.enabled     and (.["is-active"] | not))] | length')
  active=$(  echo "$units" | jq '[.[] | select(.enabled     and  .["is-active"]       )] | length')
  disabled=$(echo "$units" | jq '[.[] | select(.enabled | not)                         ] | length')

  # Dynatrace line protocol: metric.key,dimensions gauge,value
  payload+="systemd.units.dead,project=${project} gauge,${dead}"$'\n'
  payload+="systemd.units.active,project=${project} gauge,${active}"$'\n'
  payload+="systemd.units.disabled,project=${project} gauge,${disabled}"$'\n'
done

curl -sf -X POST "${DT_URL}/api/v2/metrics/ingest" \
  -H "Authorization: Api-Token ${DT_TOKEN}" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-raw "${payload}"
```

**`/etc/systemd/system/systemd-search-dynatrace.service`**

```ini
[Unit]
Description=Push systemd label metrics to Dynatrace
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/systemd-search/dynatrace.env
ExecStart=/usr/local/bin/systemd-search-dynatrace.sh
```

**`/etc/systemd/system/systemd-search-dynatrace.timer`**

```ini
[Unit]
Description=Run Dynatrace metric push every 60 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
AccuracySec=5s

[Install]
WantedBy=timers.target
```

**`/etc/systemd-search/dynatrace.env`**

```bash
DYNATRACE_URL=https://abc12345.live.dynatrace.com
DYNATRACE_API_TOKEN=dt0c01.XXXXXXXXXXXX...
```

Enable the timer:

```bash
systemctl enable --now systemd-search-dynatrace.timer
```

The metric `systemd.units.dead` is then available in Dynatrace with a `project` dimension. An anomaly detection rule or a fixed threshold alert on that metric covers all labelled projects without any per-service configuration in Dynatrace itself.

---

## Development

All development dependencies are managed with [Pipenv](https://pipenv.pypa.io). The `Pipfile` pins Python 3.9 to match the system Python on Rocky Linux 9 — the primary deployment target.

### First-time setup

Install Pipenv if not already present:

```bash
pip install --user pipenv
```

Then create the virtual environment and install all dev dependencies:

```bash
pipenv install --dev
```

This creates a Python 3.9 virtual environment under `.venv/` (or the Pipenv default location) and installs pytest, Molecule, Ansible, and the Docker driver.

### Entering the environment

```bash
pipenv shell
```

All subsequent commands in this section assume the environment is active. Alternatively, prefix any single command with `pipenv run`:

```bash
pipenv run pytest tests/ -v
```

### Unit tests

```bash
pytest tests/ -v
```

The unit tests target **Python 3.9** — the system Python on Rocky Linux 9. That version ships as the default on Rocky Linux 9 and will not change for the lifetime of the distribution. Running tests against 3.9 ensures the tool works on that platform without any additional Python installation and catches accidental use of language or stdlib features introduced in later versions.

### Integration tests

Molecule tests install the tool inside real systemd containers and exercise every search combination against live units. Docker must be running.

```bash
molecule test -s rocky   # tests Rocky Linux 9 and 10 in parallel
molecule test -s debian  # tests Debian 12 and 13 in parallel
```

The scenarios use the `geerlingguy/docker-*-ansible` images, which are systemd-capable images built for this kind of testing.

### Updating dependencies

```bash
# Add or upgrade a dev dependency
pipenv install --dev some-package
```

### CI/CD

Pull requests must pass unit tests and both molecule scenarios before merging. Pushing a semver tag triggers the packaging and release jobs, which build RPM and DEB packages, publish the wheel to PyPI, and create a GitHub Release. The tag is the version — there is no separate version file.

```bash
git tag 1.2.0
git push origin 1.2.0
```
