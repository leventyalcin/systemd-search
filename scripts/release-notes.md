## Artifacts

| File | Description |
|------|-------------|
| `systemd-search` | Python executable (distro-independent) |
| `systemd-search-rocky9.noarch.rpm` | RPM for Rocky Linux 9 |
| `systemd-search-rocky10.noarch.rpm` | RPM for Rocky Linux 10 |
| `systemd-search-debian12.all.deb` | DEB for Debian 12 (Bookworm) |
| `systemd-search-debian13.all.deb` | DEB for Debian 13 (Trixie) |

Each artifact is accompanied by a `.sha256` checksum file.

### Verify a download

```bash
sha256sum -c systemd-search-rocky9.noarch.rpm.sha256
```
