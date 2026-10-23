"""Pinned colour/data-map acquisition with bounded archives and offline reuse."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

from PIL import Image
import yaml

MAX_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 160 * 1024 * 1024


def download_bytes(url: str, limit: int = MAX_BYTES) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Material downloads require HTTPS")
    last_error = None
    for _ in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "dataset-generator-m1-material-study"}), timeout=30) as response:
                payload = response.read(limit + 1)
                if len(payload) > limit:
                    raise ValueError("Material download exceeds the configured byte limit")
                return payload
        except (OSError, TimeoutError) as exc:
            last_error = exc
    raise RuntimeError("Material download failed after three attempts") from last_error


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _archive(payload: bytes) -> ZipFile:
    archive = ZipFile(BytesIO(payload))
    infos = archive.infolist()
    if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
        raise ValueError("Material archive expanded size exceeds the limit")
    for info in infos:
        path = PurePosixPath(info.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or ":" in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("Unsafe material archive member")
    return archive


def _verified_maps(payload: bytes, manifest: dict) -> dict[str, bytes]:
    with _archive(payload) as archive:
        result = {}
        for role, item in manifest["maps"].items():
            if role not in {"color", "normal", "roughness", "displacement", "ambient-occlusion"}:
                raise ValueError("Unsupported material map role")
            data = archive.read(item["member"])
            if _digest(data) != item["sha256"]:
                raise ValueError("Material map checksum mismatch")
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 8192 * 8192:
                    raise ValueError("Material map dimensions exceed the limit")
                image.verify()
            result[role] = data
        return result


def fetch_material(manifest: dict, output_dir: str | Path, *, fetch=download_bytes, payload: bytes | None = None) -> dict:
    if manifest.get("schema_version") != 1 or not re.fullmatch(r"[A-Za-z0-9_-]+", manifest.get("asset_id", "")):
        raise ValueError("Invalid pinned material identity")
    if "color" not in manifest.get("maps", {}):
        raise ValueError("Pinned materials require a colour map")
    if set(manifest["maps"]) - {"color", "normal", "roughness", "displacement", "ambient-occlusion"}:
        raise ValueError("Unsupported material map role")
    target = Path(output_dir) / manifest["asset_id"]
    if target.exists():
        stored = json.loads((target / "material.json").read_text(encoding="utf-8"))
        if stored != manifest:
            raise ValueError("Existing material has different provenance; choose a new output root")
        for role, item in manifest["maps"].items():
            if _digest((target / (role + ".jpg")).read_bytes()) != item["sha256"]:
                raise ValueError("Existing material map checksum mismatch")
        return {"status": "complete", "schema_version": 1, "material_id": manifest["material_id"], "path": str(target), "offline_reuse": True}
    payload = payload if payload is not None else fetch(manifest["archive"]["url"])
    if _digest(payload) != manifest["archive"]["sha256"] or len(payload) > MAX_BYTES:
        raise ValueError("Material archive checksum or size mismatch")
    maps = _verified_maps(payload, manifest)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="material-", dir=target.parent) as temporary:
        root = Path(temporary) / "bundle"
        root.mkdir()
        for role, data in maps.items():
            (root / (role + ".jpg")).write_bytes(data)
        (root / "material.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        entries = [{"path": role + ".jpg", "material_id": manifest["material_id"], "excluded": role != "color"} for role in maps]
        (root / "background-catalog.yaml").write_text(yaml.safe_dump({"schema_version": 1, "assets": entries}), encoding="utf-8")
        os.rename(root, target)
    return {"status": "complete", "schema_version": 1, "material_id": manifest["material_id"], "path": str(target), "offline_reuse": False}


def acquire_material(asset_id: str, output_dir: str | Path, manifest_path: str | Path, *, resolution: str = "1K-JPG", fetch=download_bytes) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", asset_id) or resolution not in {"1K-JPG", "2K-JPG"}:
        raise ValueError("Use a valid ambientCG asset ID and 1K-JPG or 2K-JPG")
    destination = Path(manifest_path)
    if destination.exists():
        raise ValueError("Selection manifest already exists; use materials fetch for pinned reuse")
    url = "https://ambientcg.com/api/v3/assets?" + urlencode({"id": asset_id, "include": "downloads,maps,url,dimensions", "limit": 1})
    metadata = json.loads(fetch(url))
    asset = next((a for a in metadata.get("assets", []) if a["id"] == asset_id), None)
    if asset is None:
        raise ValueError("Requested material is absent from the provider catalog")
    choice = next((d for d in asset["downloads"] if d["attributes"] == resolution), None)
    if not choice or choice["size"] > MAX_BYTES:
        raise ValueError("Requested material resolution is unavailable or exceeds the download budget")
    payload = fetch(choice["url"])
    maps = {}
    suffixes = {"color": "Color", "normal": "NormalGL", "roughness": "Roughness", "displacement": "Displacement", "ambient-occlusion": "AmbientOcclusion"}
    with _archive(payload) as archive:
        for role, suffix in suffixes.items():
            matches = sorted(name for name in archive.namelist() if name.endswith("_" + suffix + ".jpg"))
            if matches:
                data = archive.read(matches[0])
                maps[role] = {"member": matches[0], "sha256": _digest(data), "size_bytes": len(data)}
    manifest = {"schema_version": 1, "asset_id": asset_id, "material_id": "ambientcg/" + asset_id,
                "provider": "ambientCG", "source_page": asset.get("url", "https://ambientcg.com/a/" + asset_id),
                "license": "CC0-1.0", "license_url": "https://docs.ambientcg.com/license/", "resolution": resolution,
                "physical_dimensions": asset.get("dimensions"), "normal_convention": "OpenGL",
                "archive": {"url": choice["url"], "sha256": _digest(payload), "size_bytes": len(payload)}, "maps": maps}
    result = fetch_material(manifest, output_dir, payload=payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, indent=2) + "\n")
    return {**result, "manifest": str(destination)}
