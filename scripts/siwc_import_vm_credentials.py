#!/usr/bin/env python3
"""Import a Mac-created SIWC credential file onto the VM it was registered for."""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.siwc import (
    REQUIRED_PLAN_SCOPE,
    SIWCError,
    default_credentials_path,
    load_credentials,
    save_credentials,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a protected SIWC credential file to its matching self-hosted VM."
    )
    parser.add_argument("--source", required=True, help="Temporary protected credential file copied to this VM.")
    parser.add_argument("--keep-source", action="store_true", help="Keep the temporary file after a successful import.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing VM credential file after validation.")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    target = default_credentials_path()
    host_id_path = Path(os.environ.get("SIWC_HOST_ID_PATH", str(target.parent / "host_id"))).expanduser()

    if source.is_symlink() or not source.is_file():
        parser.error("--source must be a regular, non-symlink credential file.")
    source_mode = stat.S_IMODE(source.stat().st_mode)
    if source_mode & 0o077:
        parser.error("The transferred credential file has broad permissions. Restrict it to mode 0600 first.")
    if not host_id_path.is_file() or host_id_path.is_symlink():
        parser.error("This VM has no prepared SIWC host ID. Run scripts/siwc_prepare_vm.sh first.")
    host_mode = stat.S_IMODE(host_id_path.stat().st_mode)
    if host_mode & 0o077:
        parser.error("The VM host ID file has broad permissions. Restrict it to mode 0600 first.")
    host_id = host_id_path.read_text(encoding="utf-8").strip()
    if not host_id.startswith("urn:uuid:"):
        parser.error("The VM host ID file is not a supported UUID URI.")

    try:
        record = load_credentials(source)
    except SIWCError as exc:
        parser.error(str(exc))
    if record.get("ext_agent_host_id") != host_id:
        parser.error("Credential file host ID does not match this VM. Nothing was imported.")
    scopes = set(record.get("scopes") or [])
    if REQUIRED_PLAN_SCOPE not in scopes:
        parser.error("ChatGPT plan-use scope was not granted. Reconnect on the Mac with plan usage enabled.")
    if target.exists() and not args.replace:
        parser.error("A VM credential file already exists. Review it locally and pass --replace only when intentionally reauthorising.")
    if source.resolve() == target.resolve():
        parser.error("Source and destination resolve to the same path; no import is needed.")

    save_credentials(target, record)
    if not args.keep_source:
        source.unlink(missing_ok=True)

    print("SIWC credentials imported to this VM.")
    print("Plan-use permission: granted")
    print("Protected credential path: " + str(target))
    print("Temporary transfer file: " + ("retained by request" if args.keep_source else "removed"))
    print("No token values were displayed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, SIWCError, ValueError) as exc:
        print("Credential import failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
