from __future__ import annotations

from pathlib import PurePosixPath, Path
import posixpath
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


class RelationshipsParser:
    def __init__(self, pptx_path: str | Path) -> None:
        self.pptx_path = Path(pptx_path).expanduser().resolve()

    def parse(self) -> dict:
        with ZipFile(self.pptx_path) as package:
            rel_files = sorted(
                [name for name in package.namelist() if name.endswith(".rels")]
            )
            return {
                rel_file: self._parse_relationship_file(package, rel_file)
                for rel_file in rel_files
            }

    def _parse_relationship_file(self, package: ZipFile, rel_file: str) -> list[dict]:
        root = ET.fromstring(package.read(rel_file))
        source_dir = self._source_dir_for_rel_file(rel_file)

        relationships = []
        for rel in root.findall("rel:Relationship", NS):
            target = rel.attrib.get("Target", "")
            relationships.append(
                {
                    "id": rel.attrib.get("Id"),
                    "type": rel.attrib.get("Type"),
                    "target": target,
                    "targetMode": rel.attrib.get("TargetMode"),
                    "resolvedTarget": self._resolve_target(source_dir, target),
                }
            )

        return relationships

    @staticmethod
    def _source_dir_for_rel_file(rel_file: str) -> str:
        if rel_file == "_rels/.rels":
            return ""

        path = PurePosixPath(rel_file)
        rels_dir = path.parent
        source_dir = rels_dir.parent
        return "" if str(source_dir) == "." else str(source_dir)

    @staticmethod
    def _resolve_target(source_dir: str, target: str) -> str:
        if not target or "://" in target:
            return target

        if target.startswith("/"):
            return target.lstrip("/")

        return posixpath.normpath(str(PurePosixPath(source_dir, target)))
