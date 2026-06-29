## Artifacts

| File | Description |
|------|-------------|
| `systemd-search-{{VERSION}}` | Self-contained Python zipapp (no installation required) |
| `systemd-search-{{VERSION}}-rocky9.noarch.rpm` | RPM for Rocky Linux 9 |
| `systemd-search-{{VERSION}}-rocky10.noarch.rpm` | RPM for Rocky Linux 10 |
| `systemd-search-{{VERSION}}-debian12.all.deb` | DEB for Debian 12 (Bookworm) |
| `systemd-search-{{VERSION}}-debian13.all.deb` | DEB for Debian 13 (Trixie) |

The package is also available on [PyPI](https://pypi.org/project/systemd-search/): `pip install systemd-search=={{VERSION}}`

Each artifact is accompanied by a `.sha256` checksum file.

### Verify a download

```bash
sha256sum -c systemd-search-{{VERSION}}-rocky9.noarch.rpm.sha256
```
