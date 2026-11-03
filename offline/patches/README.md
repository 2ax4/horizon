# offline/patches

The launcher patches that turn upstream Horizon into this fork's offline build.
`auto-offline-release.yml` applies them with `git am --3way` on top of the
newest upstream `launcher@x.y.z` tag and builds the release from the result.

When upstream changes the patched files, `git am` fails, CI records an
`offline-failed/<version>-<phash>` tag and opens an issue. Rebase the series
onto the failing upstream tag and push the new patches; CI retries the same
version automatically (patch content changes the phash, so old failure
markers no longer block it).

| Patch | What it does |
| --- | --- |
| `0001-offline-accounts.patch` | Offline accounts: add and play with no Microsoft account (launcher UI, CLI, owner gate, translations hooks, tests) |
| `0003-offline-update-notice.patch` | Offline-build update notice; adds the fork's Ed25519 release key to `crates/horizon-release-sign/release-keys.txt` |
| `0004-Ad-free-remove-the-partner-banners.patch` | Removes the partner banners from the launcher (ad-free) |
| `0005-Offline-build-quiet-sign-in-notices-and-fork-repo.patch` | Quiets sign-in notices; points the launcher's self-update at this fork (`LAUNCHER_REPO`) |
| `0006-Drop-the-translations-of-the-removed-strings.patch` | Drops translations for strings the earlier patches removed |

See also [`../verify-release.py`](../verify-release.py): a dependency-free
script users can run to check a downloaded release against `SHA256SUMS.sig`
(the same Ed25519 key patch 0003 installs).
