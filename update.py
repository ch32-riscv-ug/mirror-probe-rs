#!/usr/bin/env -S uv run --no-project --script
# /// script
# requires-python = ">=3.10"
# ///
"""
Mirror probe-rs releases in a layout package managers can install.

This file is the CH32 RISC-V User Group's own work, under the repository's root
MIT LICENSE. The archives it publishes are not: they are probe-rs's, under
Apache-2.0 OR MIT, and the root LICENSE does not apply to them. See
THIRD-PARTY-NOTICE.md.
このファイルは我々の著作物でルートのMIT。publishするアーカイブはprobe-rsの
著作物であり、ルートのMITは適用されない。

probe-rs のリリースを、パッケージマネージャが install できる形でミラーする。

Run by GitHub Actions (.github/workflows/update.yml); the workflow creates the
release and commits the record. This script only produces files.
GitHub Actions から実行される。release 作成と commit はワークフローが行う。

Why this mirror exists / このミラーの理由:
  arduino-cli requires a tool archive to contain exactly one root directory.
  probe-rs's Linux and macOS tarballs do; the Windows zip does not - its seven
  files sit at the archive root - so `arduino-cli core install` fails on
  Windows with "searching package root dir: files in archive must be placed in
  a subdirectory". That asymmetry is dist's documented convention, not a
  probe-rs bug, and the equivalent request to relax arduino-cli was declined
  (arduino/arduino-cli#325).
  arduino-cli は tool アーカイブに単一の root ディレクトリを要求する。
  probe-rs の tarball は満たすが Windows zip は平坦なため install に失敗する。

What this does NOT do / やらないこと:
  - It does not modify any binary. Payloads are byte-identical to upstream.
    バイナリは一切変更しない。中身は upstream とバイト単位で同一。
  - It does not add verification. Upstream checksums are recorded and
    forwarded; if upstream is compromised, so is this mirror.
    検証を上乗せしない。upstream の checksum を記録して転送するだけ。
  - It does not decide which version anyone uses. Consumers pin a version.
    どの version を使うかは決めない。利用側が pin する。

Repacking is decided by inspection, not by a hardcoded list: an archive is
repacked only if it actually lacks a root directory. If upstream fixes the
Windows zip, this mirror stops repacking it without any change here.
詰め直すかは実物を見て決める。upstream が直せば自動的に素通しへ戻る。

Determinism / 決定性:
  A repacked archive is byte-reproducible - entries sorted, one fixed
  timestamp, fixed compression - so anyone can rebuild it from the upstream
  archive and get the same checksum.
  詰め直しは決定的。誰でも upstream から同じ checksum を再現できる。

Failure policy / 失敗時の方針:
  - upstream changed an already-mirrored version -> fail the job (alert).
    Never overwrite: a silent content change is the worst outcome.
    ミラー済み version の中身が変わっていたらジョブを失敗させる。上書きしない。
  - HTTP error status (4xx/5xx) -> fail the job (alert).
    HTTP エラー応答はジョブを失敗させる。
  - transport-level glitch (timeout, reset, truncated) -> skip this run; the
    next daily run retries.
    伝送レベルの一時障害はスキップ。日次実行が再試行を兼ねる。

A record in versions/ means "mirrored and published": the workflow writes it in
the same run that creates the release, so the two never drift. --version
rebuilds even an already-recorded version, which is what lets a run be repeated
after a partial failure; the publish step still refuses to touch a tag that
already exists.
versions/ の記録は「公開済み」を意味する。--version は記録済みでも作り直す
(部分失敗のやり直し用)。既存tagへの再uploadはpublish側が拒否する。

Usage:
  ./update.py                    # mirror releases newer than the newest we have
  ./update.py --version 0.32.0   # this version specifically, even if recorded
  ./update.py --dry-run          # build into dist/ but write no record
"""
import argparse
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
RECORDS = HERE / "versions"
DIST = HERE / "dist"

UPSTREAM = "probe-rs/probe-rs"
TOOL_NAME = "probe-rs"

# Arduino host string -> upstream target triple. Two Windows hosts share one
# archive: upstream ships no 32-bit Windows build, and a 32-bit arduino-cli on
# a 64-bit Windows runs the x86_64 binary fine.
# 32bit Windows 版は upstream に無く、64bit バイナリで動くため同じものを指す。
HOSTS = {
    "x86_64-pc-linux-gnu": "x86_64-unknown-linux-gnu",
    "aarch64-linux-gnu": "aarch64-unknown-linux-gnu",
    "x86_64-apple-darwin": "x86_64-apple-darwin",
    "arm64-apple-darwin": "aarch64-apple-darwin",
    "x86_64-mingw32": "x86_64-pc-windows-msvc",
    "i686-mingw32": "x86_64-pc-windows-msvc",
}

# One fixed timestamp for every entry of a repacked archive. Any value works as
# long as it never changes.
# 詰め直し時の timestamp。値は何でもよいが変えないこと。
FIXED_DATE = (1980, 1, 1, 0, 0, 0)

REPACK_SUFFIX = "-rooted"

HARD_FAILS = []   # genuine error -> fail the job
SOFT_FAILS = []   # transient -> skip, retry next run


def log(msg):
    print(msg, flush=True)


def get(url, binary=True, timeout=900):
    """One attempt. Returns bytes, or None after recording the failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "mirror-probe-rs"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310
            data = r.read()
    except urllib.error.HTTPError as e:
        log(f"  -> HTTP {e.code}: genuine error (URL changed or server error)")
        HARD_FAILS.append(f"{url}  HTTP {e.code}")
        return None
    except Exception as e:                                        # noqa: BLE001
        log(f"  -> transient failure ({e}); will retry next run")
        SOFT_FAILS.append(f"{url}  {e}")
        return None
    if not data:
        log("  -> empty response; will retry next run")
        SOFT_FAILS.append(f"{url}  empty")
        return None
    return data if binary else data.decode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upstream_releases():
    """[(version, tag)] for published, non-draft releases, newest first."""
    raw = get(f"https://api.github.com/repos/{UPSTREAM}/releases?per_page=100",
              binary=False)
    if raw is None:
        return []
    out = []
    for r in json.loads(raw):
        if r.get("draft") or r.get("prerelease"):
            continue
        tag = r["tag_name"]
        m = re.fullmatch(r"v?(\d+\.\d+\.\d+)", tag)
        if m:
            out.append((m.group(1), tag))
    return out


def version_key(v: str):
    return tuple(int(x) for x in v.split("."))


def mirrored():
    return sorted((p.stem for p in RECORDS.glob("*.json")), key=version_key)


def is_flat(name: str, data: bytes) -> bool:
    """True if the archive has files at its root rather than one root directory.

    Inspected, not assumed: the day upstream ships a rooted Windows zip this
    returns False and the archive is passed through untouched.
    実物を見て判定する。upstream が直せば自動的に素通しになる。
    """
    if not name.endswith(".zip"):
        return False        # dist tarballs always carry a root directory
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
    return any("/" not in n for n in names)


def repack(data: bytes, root: str) -> bytes:
    """Rewrite a flat zip with every entry under `root/`. Byte-reproducible."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        names = sorted(n for n in src.namelist() if not n.endswith("/"))
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
            for name in names:
                info = zipfile.ZipInfo(f"{root}/{name}", date_time=FIXED_DATE)
                # Regular file, rw-r--r--. The executable bit is meaningless on
                # Windows, which is the only platform whose archive is a zip.
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(info, src.read(name))
    return out.getvalue()


def asset_urls(version: str, tag: str, triple: str):
    base = f"https://github.com/{UPSTREAM}/releases/download/{tag}"
    name = f"probe-rs-tools-{triple}." + ("zip" if "windows" in triple else "tar.xz")
    return name, f"{base}/{name}", f"{base}/{name}.sha256"


def upstream_checksum(url: str):
    """The sha256 upstream publishes beside the archive."""
    text = get(url, binary=False, timeout=120)
    if text is None:
        return None
    # "<hex>  <filename>"
    m = re.match(r"([0-9a-f]{64})", text.strip())
    if not m:
        log(f"  -> unreadable checksum file: {text[:80]!r}")
        HARD_FAILS.append(f"{url}  unreadable")
        return None
    return m.group(1)


def build(version: str, tag: str, out_dir: pathlib.Path):
    """Produce every asset for one version. Returns the record, or None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    systems, done = [], {}

    for host, triple in HOSTS.items():
        name, url, sha_url = asset_urls(version, tag, triple)
        if name in done:
            systems.append(dict(done[name], host=host))
            continue

        log(f"  {host}  <- {name}")
        want = upstream_checksum(sha_url)
        if want is None:
            return None
        data = get(url)
        if data is None:
            return None
        got = sha256(data)
        if got != want:
            log(f"  -> checksum mismatch: got {got}, upstream says {want}")
            HARD_FAILS.append(f"{name}  checksum mismatch")
            return None

        if is_flat(name, data):
            root = name[: -len(".zip")]
            payload = repack(data, root)
            out_name = f"{root}{REPACK_SUFFIX}.zip"
            log(f"     flat archive -> repacked under {root}/")
        else:
            payload = data
            out_name = name
            log("     already rooted -> passed through unchanged")

        (out_dir / out_name).write_bytes(payload)
        entry = {
            "url": (f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'ch32-riscv-ug/mirror-probe-rs')}"
                    f"/releases/download/v{version}/{out_name}"),
            "archiveFileName": out_name,
            "checksum": "SHA-256:" + sha256(payload),
            "size": str(len(payload)),
            "upstreamUrl": url,
            "upstreamArchiveFileName": name,
            "upstreamChecksum": "SHA-256:" + want,
            "repacked": out_name != name,
        }
        done[name] = entry
        systems.append(dict(entry, host=host))

    # host first, for readability
    systems = [{"host": s.pop("host"), **s} for s in systems]
    return {
        "comment": (
            f"probe-rs {version}, mirrored by ch32-riscv-ug/mirror-probe-rs. "
            "Payloads are byte-identical to the upstream release recorded in "
            "upstreamUrl/upstreamChecksum. Archives whose files sat at the "
            "archive root are repacked under a single root directory, which is "
            "what arduino-cli requires; the rest are passed through unchanged. "
            "Rebuild and verify with update.py."),
        "name": TOOL_NAME,
        "version": version,
        "upstreamTag": tag,
        "systems": systems,
    }


def verify_unchanged(version: str) -> bool:
    """An already-mirrored version must still match upstream, or we alert.

    Only the tiny .sha256 sidecars are fetched, so this is cheap enough to run
    for every mirrored version on every scheduled run.
    小さな .sha256 だけを取得するので毎回全 version を確認できる。
    """
    record = json.loads((RECORDS / f"{version}.json").read_text(encoding="utf-8"))
    seen = set()
    for s in record["systems"]:
        name = s["upstreamArchiveFileName"]
        if name in seen:
            continue
        seen.add(name)
        got = upstream_checksum(s["upstreamUrl"] + ".sha256")
        if got is None:
            return False
        if "SHA-256:" + got != s["upstreamChecksum"]:
            log(f"  -> {name}: upstream now {got}, "
                f"mirrored {s['upstreamChecksum'].split(':')[1]}")
            HARD_FAILS.append(
                f"{name}  upstream changed an already-mirrored version "
                f"({version}); refusing to overwrite")
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="mirror exactly this version (backfill)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build into dist/ but write no record")
    ap.add_argument("--skip-verify", action="store_true",
                    help="do not re-check already-mirrored versions")
    args = ap.parse_args()

    RECORDS.mkdir(exist_ok=True)
    have = mirrored()
    log(f"Mirrored: {', '.join(have) if have else '(none yet)'}")

    releases = upstream_releases()
    if not releases and not args.version:
        finish()
        return 0
    log(f"Upstream: {len(releases)} release(s), newest "
        f"{releases[0][0] if releases else '?'}")

    if not args.skip_verify:
        for v in have:
            log(f"Checking mirrored {v} still matches upstream")
            verify_unchanged(v)
        if HARD_FAILS:
            finish()
            return 1

    tags = dict(releases)
    if args.version:
        if args.version not in tags:
            log(f"{args.version} is not a published upstream release")
            return 2
        # Explicit means explicit: rebuild even if already recorded, so a run
        # can be repeated after a partial failure. Re-publishing is prevented
        # by the workflow, which never touches an existing tag.
        # 明示指定は記録済みでも作り直す。再publishはworkflow側が防ぐ。
        wanted = [args.version]
    elif not have:
        # First run mirrors only the newest. Backfill older ones deliberately
        # with --version; nobody wants a first run that uploads every release
        # probe-rs ever made.
        # 初回は最新のみ。遡りは --version で明示的に。
        wanted = [releases[0][0]]
    else:
        newest = max(have, key=version_key)
        wanted = [v for v, _ in releases if version_key(v) > version_key(newest)]

    if not args.version:
        wanted = [v for v in wanted if v not in have]
    if not wanted:
        log("Nothing to mirror.")
        finish()
        return 0

    for version in sorted(wanted, key=version_key):
        log(f"Mirroring {version}")
        record = build(version, tags[version], DIST / f"v{version}")
        if record is None:
            log(f"  -> {version} incomplete; not recording")
            continue
        (DIST / f"v{version}" / "tools_probe_rs.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if not args.dry_run:
            (RECORDS / f"{version}.json").write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8")
        log(f"  -> built {version} into {DIST / f'v{version}'}")

    finish()
    return 0


def finish():
    if SOFT_FAILS:
        log(f"::warning::skipped {len(SOFT_FAILS)} download(s) due to transient "
            f"errors; will retry next run")
        for f in SOFT_FAILS:
            log(f"  {f}")
    if HARD_FAILS:
        print(f"::error::{len(HARD_FAILS)} genuine failure(s)", file=sys.stderr)
        for f in HARD_FAILS:
            print(f"  {f}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
