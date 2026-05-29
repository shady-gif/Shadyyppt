import path from "node:path/posix";
import { ensureArray } from "../shared/xml.js";

const RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

export function parseRelationshipPart(xml, relsPath) {
  const relationships = ensureArray(xml?.Relationships?.Relationship).map((relationship) => {
    const id = relationship["@_Id"] || null;
    const type = relationship["@_Type"] || null;
    const target = relationship["@_Target"] || null;
    const targetMode = relationship["@_TargetMode"] || null;
    const sourcePath = sourcePartFromRelationshipsPath(relsPath);

    return {
      id,
      type,
      kind: relationshipKind(type),
      target,
      targetMode,
      sourcePath,
      targetPath: targetMode === "External" ? target : resolveTargetPath(sourcePath, target),
    };
  });

  return relationships;
}

export function sourcePartFromRelationshipsPath(relsPath) {
  if (relsPath === "_rels/.rels") {
    return "/";
  }

  const marker = "/_rels/";
  if (!relsPath.includes(marker) || !relsPath.endsWith(".rels")) {
    return null;
  }

  const [directory, filename] = relsPath.split(marker);
  return path.join(directory, filename.replace(/\.rels$/, ""));
}

export function resolveTargetPath(sourcePath, target) {
  if (!sourcePath || !target) {
    return target || null;
  }
  if (/^[a-z]+:/i.test(target)) {
    return target;
  }

  const baseDirectory = sourcePath === "/" ? "" : path.dirname(sourcePath);
  return path.normalize(path.join(baseDirectory, target));
}

export function relationshipKind(type) {
  if (!type) {
    return null;
  }
  return type.replace(`${RELATIONSHIP_NS}/`, "");
}

