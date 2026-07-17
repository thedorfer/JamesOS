from __future__ import annotations

import json
from pathlib import Path

from .manifest import AgencyManifest, AgencyManifestError


class CatalogProvider:
    def list_manifests(self) -> list[AgencyManifest]:
        raise NotImplementedError


class DirectoryCatalogProvider(CatalogProvider):
    """Checked-in provider boundary; remote catalogs can implement the same contract."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def list_manifests(self) -> list[AgencyManifest]:
        manifests: list[AgencyManifest] = []
        ids: set[str] = set()
        for path in sorted(self.directory.glob("*.json")):
            try:
                manifest = AgencyManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, AgencyManifestError) as exc:
                raise AgencyManifestError(f"{path.name}: {exc}") from exc
            if manifest.package.agent_id in ids:
                raise AgencyManifestError(f"duplicate catalog agent ID: {manifest.package.agent_id}")
            ids.add(manifest.package.agent_id)
            manifests.append(manifest)
        return manifests
