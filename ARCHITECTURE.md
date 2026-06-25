# Architecture & Design Decisions

This document explains how `systemd-search` is built, why each decision was made, and what trade-offs were accepted. It is written for anyone who needs to extend, debug, or maintain the tool in the future.

---

## Problem statement

systemd has no native concept of user-defined tags on unit files. Finding all units that belong to a project means either maintaining a separate registry, grepping file contents, or knowing the naming convention ahead of time. None of those scale and all of them break when drop-in override files are involved.

`systemd-search` uses a property of the systemd unit file format to solve this without patching systemd or maintaining any external state.

---

## The `X-` section trick

The `systemd.unit(5)` man page specifies that any section whose name begins with `X-` is completely ignored by systemd. The unit loads and runs normally. Third-party applications are explicitly invited to use these sections for their own metadata.

This means an `[X-Labels]` block (or any `[X-*]` block) can be added to an existing unit file at any time with zero risk of affecting systemd behaviour. `systemd-search` reads those sections to provide a tagging layer on top of systemd with no daemon, no database, and no infrastructure.

Reference: <https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html>

---

## How the tool works

### Step 1 — enumerate unit files

`systemctl list-unit-files --type=<type>` returns all installed units of the requested type and their enabled state (`enabled`, `disabled`, `static`, etc.). This is cheap and does not require reading any file on disk.

### Step 2 — read the effective configuration

For every unit that passes the enabled/disabled filter, `systemctl cat <unit>` is called. This command resolves the full configuration: the base unit file plus every drop-in file under `<unit>.d/` directories, concatenated in the correct override order. Later definitions of the same key win, which matches systemd's own merge semantics.

Parsing the raw file on disk would be wrong — it would miss drop-ins that change or add label keys.

### Step 3 — parse

The output of `systemctl cat` is INI-format text. It is parsed with Python's `configparser.RawConfigParser` rather than hand-rolled string splitting. Key decisions:

- `strict=False` — allows duplicate sections (base file and drop-in both define `[X-Labels]`) and duplicate keys. Later definitions overwrite earlier ones, which is exactly what systemd does when merging drop-ins.
- `delimiters=('=',)` — systemd never uses `:` as a key-value separator. Preventing configparser from treating it as one avoids misreading values like `ExecStart=/bin/sh -c 'key:value'`.
- `optionxform = str` — configparser lowercases keys by default. Label keys are case-sensitive (users define `Project`, not `project`), so this must be disabled.
- `RawConfigParser` rather than `ConfigParser` — prevents interpolation of `%`-style variables that may appear in systemd values.

### Step 4 — section gate

Every unit is checked for the presence of the target section **unconditionally**, regardless of what flags were passed. If the section is absent the unit is silently skipped. This is a hard invariant: `systemd-search` only surfaces units that carry the section. Running `systemd-search` with no flags does not list every service on the system — it lists only the services the operator has labelled.

This was a deliberate late decision. An early design allowed unlabelled units to appear when no label filter was set (to allow browsing). It was rejected because `systemd-search` is a tool for labelled infrastructure, not a general unit browser, and mixing unlabelled system services into the output defeats the purpose.

### Step 5 — apply label and exclude filters

`--label KEY` — the key must be present in the section.  
`--label KEY=VALUE` — the key must be present and equal the given value.  
`--exclude KEY` — the unit is dropped if the key is present, regardless of value.  
`--exclude KEY=VALUE` — the unit is dropped only if the key is present *and* equals the value.

Multiple `--label` filters are ANDed: all must match.  
Multiple `--exclude` filters are ORed: any hit drops the unit.

`--label` and `--exclude` compose freely with each other and with state filters.

### Step 6 — active state

`systemctl is-active <unit>` is called only when needed:

- `--active` or `--dead` is passed (state filter)
- `--json` is passed (the output always includes `is-active`)

In all other output modes the active-state subprocess call is skipped for performance. On a system with many labelled units this matters.

### Step 7 — output

Three output modes are mutually exclusive:

| Mode | Flag | Format |
|---|---|---|
| Plain | (default) | One unit name per line |
| Verbose | `--verbose` / `-v` | `unit-name\tkey=value …` |
| JSON | `--json` | JSON array, one object per unit |

`--verbose` shows only the keys that were queried with `--label`. If no `--label` filter is set it shows every key in the section.

`--json` always shows all section keys under `labels`, plus `enabled` (bool) and `is-active` (bool). The `enabled` field is derived from the enabled-state string returned by `systemctl list-unit-files`: the states `enabled`, `enabled-runtime`, `static`, `alias`, `generated`, and `transient` are treated as enabled; `disabled`, `masked`, `masked-runtime`, and `indirect` are treated as disabled.

### Exit code

Exit code `0` — at least one result was returned.  
Exit code `1` — no results matched. This allows shell scripts and monitoring agents to detect the empty case without parsing output.

In JSON mode an empty result produces `[]` on stdout with exit code `1`, so JSON consumers always receive valid JSON regardless of whether results were found.

---

## Python version target

The tool targets **Python 3.9** — the system Python on Rocky Linux 9. Rocky Linux 9 ships 3.9 as its default and that version will not change for the lifetime of the distribution. The tool must work without installing any additional Python version or any third-party packages. All dependencies (`argparse`, `configparser`, `json`, `subprocess`, `sys`) are standard library modules present in 3.9.

Unit tests are run against Python 3.9 in CI for the same reason.

---

## Test strategy

### Unit tests (`tests/`)

Pure function tests with no I/O. They cover every testable function in the script:

- `parse_cat_output` — INI parsing, drop-in merge semantics, edge cases
- `parse_label_filters` — `KEY` and `KEY=VALUE` parsing, whitespace, embedded `=`
- `section_matches` — positive filter logic
- `section_excluded` — negative filter logic
- `format_json_entry` — JSON shape, `enabled` bool derivation, label copy
- `format_verbose` — tab-separated output, key selection

`main()` is not unit-tested directly because it depends on live `systemctl` calls. Integration coverage is provided by molecule.

The script is named `systemd-search` (no `.py` extension) to be installable as a plain executable. Importing a hyphen-named file requires `importlib.machinery.SourceFileLoader` rather than the standard import machinery. `tests/conftest.py` handles this once so test files can do a normal `import systemd_search`.

### Molecule integration tests (`molecule/`)

Two scenarios — `rocky` and `debian` — each define two platforms so a single `molecule test` run covers both versions of the distribution simultaneously. `rocky` tests Rocky Linux 9 and 10; `debian` tests Debian 12 and 13.

The fixture units are designed to exercise every code path:

| Unit | Labels | State |
|---|---|---|
| `fixture-single.service` | `Project=single-app` | enabled, not started |
| `fixture-multi-a.service` | `Project=myapp`, `Domain=foo`, `Env=prod` | enabled, active |
| `fixture-multi.timer` | `Project=myapp`, `Domain=foo`, `Env=prod` | enabled, active |
| `fixture-multi.path` | `Project=myapp`, `Domain=foo`, `Env=prod` | enabled, active |
| `fixture-disabled.service` | `Project=myapp`, `Visibility=disabled-only` | installed, not enabled |
| `fixture-failing.service` | `Project=myapp`, `Status=failing` | enabled, failed |

`fixture-single` deliberately uses `Project=single-app` (different value from the others) to verify that `--verbose` shows per-unit values and that `--exclude Project=myapp` correctly returns only this unit.

`fixture-failing` uses `ExecStart=/bin/false` to produce a genuine failed state. Molecule starts it with `ignore_errors: true` because systemd correctly refuses to report success when the service fails.

Molecule scenarios share converge and verify playbooks via `molecule/common/`. Only `molecule.yml` (the platform definition) differs between scenarios. The binary is staged from the project root into `molecule/common/files/systemd-search` by a `prepare.yml` playbook that runs on the Ansible controller before the container is provisioned, so the tool does not need to be built or packaged for testing.

Every molecule command that is expected to produce empty output has `failed_when: false` to prevent Ansible from treating exit code `1` as a task failure. Assertions on the registered result then check both `rc == 1` and empty stdout/`[]`.

---

## Packaging

### RPM (`scripts/build-rpm.sh`)

Runs inside the target Rocky Linux container (`rockylinux:9` or `rockylinux:10`). Installs `rpm-build`, generates a spec file with the version from the `VERSION` file, and calls `rpmbuild -bb`. The resulting `.noarch.rpm` is copied back to the host workspace. `BuildArch: noarch` is correct because the tool is a Python script with no compiled components.

### DEB (`scripts/build-deb.sh`)

Runs inside the target Debian container (`debian:12` or `debian:13`). Builds a package directory tree under `/build/DEBIAN/` with a `control` file, then calls `dpkg-deb --build`. `Architecture: all` is the Debian equivalent of `noarch`.

### Version

The version is the git tag itself. Both packaging scripts accept it as a second positional argument (`build-rpm.sh <target> <version>`, `build-deb.sh <target> <version>`). In CI the tag is extracted from `GITHUB_REF` and passed through to the container. There is no separate `VERSION` file — the tag is the single source of truth.

---

## CI/CD pipeline

### Pipeline files

The CI/CD configuration is split across three files, following the DRY principle via GitHub Actions reusable workflows:

| File | Trigger | Responsibility |
|---|---|---|
| `tests.yml` | `workflow_call` (never directly) | Unit tests + molecule — the shared task definition |
| `pr.yml` | `pull_request`, push to `master`/`main` | Calls `tests.yml`; nothing else |
| `release.yml` | Push of any tag | Calls `tests.yml`, validates semver, builds packages, publishes release |

`tests.yml` is a reusable workflow (`on: workflow_call`). It is never triggered directly — only called by `pr.yml` and `release.yml`. This is the single definition of what "passing tests" means. Any change to the test suite is made once and is immediately in effect for both contexts.

### Semver validation

GitHub Actions `on.push.tags` only supports glob patterns, not regex. `release.yml` uses `tags: ["*"]` to catch all tag pushes, then a dedicated `validate-tag` job applies the official semver.org ERE regex via `grep -E`. The regex validates:

- `MAJOR.MINOR.PATCH` with no leading zeroes in any component
- Optional pre-release identifier after `-` (e.g. `1.0.0-beta.1`)
- Optional build metadata after `+` (e.g. `1.0.0+20250625`)

`validate-tag` runs in parallel with the `tests` job so a bad tag is rejected immediately without waiting for the full test suite. `package` and `executable` both `need: [tests, validate-tag]` — both gates must be green before a single package is built.

Tags carry no `v` prefix. The tag `1.2.0` produces the release `systemd-search 1.2.0`.

### Release

The `release` job downloads all artifacts uploaded by `package` and `executable`, then calls `gh release create` with the tag name. Each release includes:

- `systemd-search` — plain Python executable, runs on any distro with Python 3.9+
- `systemd-search-<version>-rocky9.noarch.rpm` + `.sha256`
- `systemd-search-<version>-rocky10.noarch.rpm` + `.sha256`
- `systemd-search-<version>-debian12.all.deb` + `.sha256`
- `systemd-search-<version>-debian13.all.deb` + `.sha256`

### Branch protection

Branch protection rules for `master` must require the following status checks (reported by `pr.yml`) to pass before merging:

- `Tests / Unit tests`
- `Tests / Molecule — rocky`
- `Tests / Molecule — debian`

This is configured in GitHub under **Settings → Branches → Branch protection rules** and is not encoded in any workflow file.

---

## Local development

Dependencies are managed with Pipenv. The `Pipfile` pins Python 3.9 to match the production target. CI also uses Pipenv — there is no separate `requirements-test.txt`.

```bash
pipenv install --dev   # create venv and install all dev deps
pipenv shell           # activate

pytest tests/ -v                        # unit tests
molecule test -s rocky                  # integration tests (Docker required)
molecule test -s debian
```

To update dependencies:

```bash
pipenv install --dev some-new-package
```
