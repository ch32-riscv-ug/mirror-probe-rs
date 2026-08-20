# Third-party content

The root [`LICENSE`](LICENSE) (MIT) covers **only this repository's own files** —
`update.py`, the workflow, and the documentation. It does **not** apply to
anything published on the releases.

## probe-rs

Everything attached to a release of this repository is
[probe-rs](https://github.com/probe-rs/probe-rs), produced and licensed by the
probe-rs project:

- **Copyright** the probe-rs authors
- **License** `Apache-2.0 OR MIT`
- `LICENSE-APACHE` and `LICENSE-MIT` are inside every archive, exactly as
  upstream ships them

### What was changed

**No file is modified.** Every payload is byte-identical to the corresponding
upstream release, and each entry in `versions/<version>.json` records the
`upstreamUrl` and `upstreamChecksum` it came from so this can be checked.

The only change is to the **container** of archives that place their files at
the archive root: those are rewritten so the same files sit under a single root
directory, which is what `arduino-cli` requires. Today that is the Windows zip
only. Whether to rewrite is decided by inspecting the archive, so if upstream
starts shipping a rooted Windows archive it is passed through untouched.

Repacked archives are given a `-rooted` suffix in their filename so they are
never mistaken for the upstream asset of the same name.

### This is not an endorsement

This mirror is operated by the CH32 RISC-V User Group and is **not affiliated
with, endorsed by, or supported by the probe-rs project**. Report problems with
probe-rs itself to probe-rs; report problems with the packaging here.

---

## 日本語

ルートの[`LICENSE`](LICENSE)(MIT)は**このrepository自身のファイル**
(`update.py`、workflow、文書)にのみ適用されます。releaseへ添付したものには
**適用されません**。

releaseに添付されているものはすべて
[probe-rs](https://github.com/probe-rs/probe-rs)であり、probe-rsプロジェクトの
著作物です(`Apache-2.0 OR MIT`)。`LICENSE-APACHE`と`LICENSE-MIT`はupstreamが
同梱しているまま、各アーカイブの中に入っています。

**ファイルは一切変更していません。** 中身はupstreamのreleaseとバイト単位で同一で、
取得元URLとchecksumは`versions/<version>.json`に記録してあります。
変えているのは、ファイルがアーカイブのroot直下に並んでいるものの**入れ物だけ**で、
同じファイルを単一のrootディレクトリの下へ入れ直しています(`arduino-cli`の要求)。
現在該当するのはWindows zipのみです。詰め直すかは実物を見て判定するため、
upstreamがroot付きのWindowsアーカイブを出せばそのまま素通しになります。

詰め直したアーカイブはファイル名に`-rooted`を付け、upstreamの同名資産と
取り違えられないようにしています。

このミラーはCH32 RISC-V User Groupが運用しており、**probe-rsプロジェクトとは
無関係**です。推奨・支援を受けているものでもありません。
