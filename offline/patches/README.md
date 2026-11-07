# offline/patches

The launcher patches that turn upstream Horizon into this fork's offline build.
`auto-offline-release.yml` applies them with `git am --3way` on top of the
newest upstream `launcher@x.y.z` tag and builds the release from the result.

**Language tables are not patched.** Upstream re-translates
`launcher/lang/*.json` constantly, so a static patch against those files broke
on almost every release. The patches below touch Rust only; right after
`git am`, the release workflow runs [`../lang-sync.py`](../lang-sync.py), which
applies the key operations stored in [`../lang-overrides.json`](../lang-overrides.json):
it drops the keys of the strings the offline build removed and adds the offline
card's key to every table, falling back to English for languages the data does
not know yet. Upstream re-translations can no longer break the release. Both
files are part of the phash, so changing them re-releases too.

When upstream changes the patched files, `git am` fails, CI records an
`offline-failed/<version>-<phash>` tag and opens an issue. Rebase the failing
patch onto the upstream tag and push the new patches; CI retries the version
automatically (patch content changes the phash, so old failure markers no
longer block it).

| Patch | What it does |
| --- | --- |
| `0001-offline-accounts.patch` | Offline accounts: add and play with no Microsoft account (launcher UI, CLI, owner gate, tests) |
| `0003-offline-update-notice.patch` | Offline-build update notice; adds the fork's Ed25519 release key to `crates/horizon-release-sign/release-keys.txt` |
| `0004-Ad-free-remove-the-partner-banners.patch` | Removes the partner banners from the launcher (ad-free) |
| `0005-Offline-build-quiet-sign-in-notices-and-fork-repo.patch` | Quiets sign-in notices; points the launcher's self-update at this fork (`LAUNCHER_REPO`) |
| `0007-Play-the-glass-home-button-without-the-ownership-check.patch` | The glass home's Play button calls the reduced `play_press`, so the offline build compiles |
| `0008-Offline-build-the-glass-look-keeps-only-the-offline-account.patch` | The glass top bar and Settings' Account card drop the Microsoft button and card; the offline account fills them |
| `0009-Java-Edition-plays-without-a-Microsoft-account.patch` | A Java instance plays with an offline name (vanilla `OfflinePlayer` UUID, no token) and Mojang's public game files download without an owner |
| `0010-restore-042-game-architecture.patch` | Restores the 0.2.42 game-architecture CLI setting |
| `0011-The-Wardrobe-and-the-Shop-work-for-an-offline-name.patch` | The Wardrobe and the Shop work with an offline name |

The numbered gaps (0002, 0006) are retired patches; the file names are the
stable API. The removed strings' keys live under "delete" in
`../lang-overrides.json` (16 of them), the offline card's key with its 86
translations under "add".

See also [`../verify-release.py`](../verify-release.py): a dependency-free
script users can run to check a downloaded release against `SHA256SUMS.sig`
(the same Ed25519 key patch 0003 installs).
