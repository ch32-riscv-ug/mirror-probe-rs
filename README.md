# mirror-probe-rs

Mirror of [probe-rs](https://github.com/probe-rs/probe-rs) releases, repackaged
so package managers that require a single root directory can install them.

**This is not the probe-rs project and not affiliated with it.** The binaries
are probe-rs's, unmodified. probe-rs is licensed `Apache-2.0 OR MIT` by its
authors, and both license files travel inside every archive.

The root [`LICENSE`](LICENSE) (MIT) covers only this repository's own files —
`update.py`, the workflow and the documentation. See
[`THIRD-PARTY-NOTICE.md`](THIRD-PARTY-NOTICE.md).

> 日本語は[下](#日本語)。

## Why this exists

`arduino-cli` requires a tool archive to contain exactly one root directory.
probe-rs's Linux and macOS tarballs do. The Windows zip does not — its seven
files sit at the archive root — so installing probe-rs as an Arduino Board
Manager tool fails on Windows:

```text
Cannot install tool <packager>:probe-rs@0.32.0:
  searching package root dir: files in archive must be placed in a subdirectory
```

That asymmetry is [dist's documented convention][dist-archives] rather than a
probe-rs bug ("tarballs get a root dir, zips don't, for compatibility/legacy
reasons"), and the equivalent request to relax `arduino-cli` was
[declined][cli-325]. So the archive is adjusted here instead.

Nothing about this is Arduino-specific: any consumer that requires a single root
directory can use these archives.

[dist-archives]: https://github.com/axodotdev/cargo-dist/blob/main/book/src/artifacts/archives.md
[cli-325]: https://github.com/arduino/arduino-cli/issues/325

## What it does, and does not

- **Payloads are byte-identical to upstream.** No binary is modified. Only the
  container of an archive that lacks a root directory is rewritten.
- **Whether to repack is decided by inspection**, not by a hardcoded list. The
  day upstream ships a rooted Windows zip, this mirror passes it through
  untouched with no change here.
- **Repacking is reproducible** — entries sorted, one fixed timestamp, fixed
  compression — so anyone can rebuild an archive from upstream and get the same
  checksum.
- **It adds no verification.** Upstream's published checksums are recorded and
  forwarded. If upstream is compromised, so is this mirror.
- **It decides nothing about versions.** Consumers pin a version and adopt new
  ones deliberately.

## Layout

```text
LICENSE                   MIT, for this repository's own files only
THIRD-PARTY-NOTICE.md     what is mirrored, whose it is, what was changed
update.py                 fetch, verify, repack, emit the tool definition
versions/<version>.json   record of every mirrored version (committed)
.github/workflows/        daily refresh; creates the releases
```

Each release is tagged `v<version>` to match upstream exactly, and carries every
host's archive plus `tools_probe_rs.json` — an Arduino tool definition fragment
whose entries record the upstream URL and checksum they came from.

## Ingestion is automatic, adoption is not

The daily job mirrors anything newer than what is already here. That is safe
because publishing a version has no effect on anyone until a consumer bumps the
version it pins.

It is **append-only**: an existing tag is never re-uploaded. If upstream alters
a version that was already mirrored, the job fails and alerts rather than
overwriting — a silent content change is the worst possible outcome. Old
versions are never deleted either: a consumer pinning an old version must keep
being able to install it.

The scheduled run only picks up releases newer than the newest mirrored one.
To take in an older release deliberately, run the workflow manually with a
version, or locally:

```sh
./update.py --version 0.32.0
./update.py --dry-run          # build into dist/ without recording
```

## Verifying a mirrored archive against upstream

Every entry in `versions/<version>.json` carries `upstreamUrl` and
`upstreamChecksum`. For a passed-through archive the mirrored checksum equals
upstream's. For a repacked one, rebuild it and compare:

```sh
./update.py --version <version> --dry-run
sha256sum dist/v<version>/*
```

---

## 日本語

[probe-rs](https://github.com/probe-rs/probe-rs) のリリースを、単一のroot
ディレクトリを要求するパッケージマネージャがinstallできる形へ詰め直して
ミラーしています。

**probe-rsプロジェクトではなく、関係もありません。** releaseにあるものは
probe-rsのバイナリそのままです。probe-rsは作者により`Apache-2.0 OR MIT`で
ライセンスされており、両方のライセンスファイルが各アーカイブに同梱されています。

ルートの[`LICENSE`](LICENSE)(MIT)は**このrepository自身のファイル**
(`update.py`、workflow、文書)にのみ適用されます。
[`THIRD-PARTY-NOTICE.md`](THIRD-PARTY-NOTICE.md)を参照してください。

### 理由

`arduino-cli`はtoolアーカイブに単一のrootディレクトリを要求します。probe-rsの
Linux/macOS向けtarballは満たしていますが、**Windows向けzipは平坦**(7ファイルが
root直下)なため、Arduino Board Manager経由のinstallがWindowsだけ失敗します。

これはprobe-rsの不具合ではなく[distの意図的な規約][dist-archives]で、
arduino-cli側の緩和は[declined][cli-325]で終わっています。そのためこちらで
形を整えています。

Arduino専用ではありません。単一rootを要求するconsumerであれば何にでも使えます。

### やること・やらないこと

- **中身はupstreamとバイト単位で同一。** バイナリは一切変更しません。rootディレクトリを
  持たないアーカイブの「入れ物」だけを書き直します
- **詰め直すかは実物を見て判定します。** upstreamがWindows zipを直せば、
  こちらを変更しなくても自動的に素通しへ戻ります
- **詰め直しは再現可能です**(entry順・timestamp・圧縮方式を固定)。誰でもupstreamから
  同じchecksumを再現できます
- **検証を上乗せしません。** upstreamが公開しているchecksumを記録して転送するだけです。
  upstreamが汚染されればミラーも汚染されます
- **versionの採用は決めません。** 利用側がpinし、意図的に上げます

### 取り込みは自動、採用は手動

日次ジョブが未取り込みのversionをミラーします。公開しても利用側がpinを上げるまで
誰にも影響しないため、取り込みは自動で構いません。

**append-onlyです。** 既存tagを再uploadすることはありません。取り込み済みのversionが
upstreamで差し替えられていたら、上書きせず**失敗させて通知**します。黙って中身が
変わるのが最悪だからです。古いversionも消しません。古いversionをpinしている利用者が
installできなくなるためです。

定期実行は「取り込み済みより新しいもの」しか拾いません。古いreleaseを遡って
取り込むときは、workflowを手動実行してversionを指定するか、ローカルで実行します。
