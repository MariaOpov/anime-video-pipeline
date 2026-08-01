"""Local asset metadata indexing and safe path checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import load_yaml, validate


def build_asset_index(asset_roots: list[Path], schema_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    assets: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    for root in asset_roots:
        if not root.exists():
            warnings.append(f"Asset library does not exist: {root}")
            continue
        for sidecar in sorted(root.rglob("*.asset.yaml")):
            try:
                item = load_yaml(sidecar)
                validate(item, schema_path, str(sidecar))
                asset_id = item["asset_id"]
                if asset_id in seen_ids:
                    warnings.append(f"Duplicate asset_id '{asset_id}' ignored: {sidecar}")
                    continue
                resolved = (sidecar.parent / item["file_path"]).resolve()
                if not resolved.is_relative_to(root.resolve()):
                    warnings.append(f"Asset path escapes library root, ignored: {sidecar}")
                    continue
                item["resolved_path"] = str(resolved)
                item["available"] = resolved.is_file()
                item["metadata_path"] = str(sidecar.resolve())
                if not item["available"]:
                    warnings.append(f"Missing asset file for '{asset_id}': {resolved}")
                license_data = item.get("license", {})
                if not license_data.get("name") or license_data.get("commercial_use") is None:
                    warnings.append(f"Incomplete licensing for '{asset_id}'")
                seen_ids.add(asset_id)
                assets.append(item)
            except (OSError, ValueError) as exc:
                warnings.append(f"Invalid asset metadata {sidecar}: {exc}")
    return assets, warnings

