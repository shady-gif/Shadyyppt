import fs from "node:fs/promises";
import JSZip from "jszip";
import { parseXml, parseXmlOrdered } from "../shared/xml.js";
import { parseRelationshipPart } from "./relationships.js";

export async function readPptxPackage(pptxPath) {
  const buffer = await fs.readFile(pptxPath);
  const zip = await JSZip.loadAsync(buffer);
  const entries = [];
  const xmlParts = new Map();
  const orderedXmlParts = new Map();
  const xmlStrings = new Map();

  const files = Object.values(zip.files).sort((a, b) => a.name.localeCompare(b.name));
  for (const file of files) {
    if (file.dir) {
      continue;
    }

    const entry = {
      path: file.name,
      kind: partKind(file.name),
      isXml: isXmlPart(file.name),
      isRelationshipPart: file.name.endsWith(".rels"),
    };
    entries.push(entry);

    if (entry.isXml || entry.isRelationshipPart) {
      const xml = await file.async("string");
      xmlStrings.set(file.name, xml);
      xmlParts.set(file.name, parseXml(xml));
      orderedXmlParts.set(file.name, parseXmlOrdered(xml));
    }
  }

  const relationships = [];
  const relationshipsBySource = new Map();
  for (const entry of entries.filter((item) => item.isRelationshipPart)) {
    const rels = parseRelationshipPart(xmlParts.get(entry.path), entry.path);
    relationships.push(...rels);
    if (rels[0]?.sourcePath) {
      relationshipsBySource.set(rels[0].sourcePath, rels);
    }
  }

  return {
    sourcePath: pptxPath,
    entries,
    xmlParts,
    orderedXmlParts,
    xmlStrings,
    relationships,
    relationshipsBySource,
    contentTypes: parseContentTypes(xmlParts.get("[Content_Types].xml")),
  };
}

function parseContentTypes(xml) {
  const types = xml?.Types || {};
  return {
    defaults: asArray(types.Default).map((item) => ({
      extension: item["@_Extension"],
      contentType: item["@_ContentType"],
    })),
    overrides: asArray(types.Override).map((item) => ({
      partName: item["@_PartName"],
      contentType: item["@_ContentType"],
    })),
  };
}

function asArray(value) {
  if (value === undefined || value === null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function isXmlPart(name) {
  return name.endsWith(".xml") || name === "[Content_Types].xml";
}

function partKind(name) {
  if (name.endsWith(".rels")) return "relationships";
  if (name === "[Content_Types].xml") return "contentTypes";
  if (name === "ppt/presentation.xml") return "presentation";
  if (name.startsWith("ppt/slides/")) return "slide";
  if (name.startsWith("ppt/slideLayouts/")) return "layout";
  if (name.startsWith("ppt/slideMasters/")) return "master";
  if (name.startsWith("ppt/theme/")) return "theme";
  if (name.startsWith("ppt/media/")) return "asset";
  if (name.startsWith("ppt/notesSlides/")) return "notes";
  return name.endsWith(".xml") ? "xml" : "binary";
}

