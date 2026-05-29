import path from "node:path/posix";
import { readPptxPackage } from "../package/read-pptx-package.js";
import { ensureArray, firstOrderedRoot, findDeep } from "../shared/xml.js";
import { parseShapeTree } from "./element-parser.js";
import { detectLayoutSlots } from "../intelligence/slot-detector.js";
import { resolveDeckInheritance } from "../intelligence/inheritance-resolver.js";

export async function parseDeck(pptxPath) {
  const pkg = await readPptxPackage(pptxPath);
  const presentation = parsePresentation(pkg);
  const masters = parseReusableParts(pkg, "master", "ppt/slideMasters/");
  const layouts = parseReusableParts(pkg, "layout", "ppt/slideLayouts/").map((layout) => ({
    ...layout,
    slots: detectLayoutSlots(layout),
  }));
  const slides = presentation.slideRefs.map((slideRef, index) => parseSlide(pkg, slideRef, index));

  const deck = {
    meta: {
      sourcePath: pptxPath,
      width: presentation.width,
      height: presentation.height,
      units: "inches",
      slideCount: slides.length,
    },
    package: {
      entries: pkg.entries,
      contentTypes: pkg.contentTypes,
      relationships: pkg.relationships,
    },
    masters,
    layouts,
    slides,
    assets: pkg.entries
      .filter((entry) => entry.kind === "asset")
      .map((entry) => ({ id: entry.path, path: entry.path, type: mediaType(entry.path) })),
    semanticMap: {
      layoutSlots: Object.fromEntries(layouts.map((layout) => [layout.id, layout.slots])),
    },
  };

  const resolvedDeck = resolveDeckInheritance(deck);
  const resolvedLayouts = resolvedDeck.layouts.map((layout) => ({
    ...layout,
    slots: detectLayoutSlots(layout),
  }));

  return {
    ...resolvedDeck,
    layouts: resolvedLayouts,
    semanticMap: {
      ...resolvedDeck.semanticMap,
      layoutSlots: Object.fromEntries(resolvedLayouts.map((layout) => [layout.id, layout.slots])),
    },
  };
}

function parsePresentation(pkg) {
  const xml = pkg.xmlParts.get("ppt/presentation.xml")?.["p:presentation"] || {};
  const size = xml["p:sldSz"] || {};
  const rels = pkg.relationshipsBySource.get("ppt/presentation.xml") || [];
  const relById = Object.fromEntries(rels.map((rel) => [rel.id, rel]));
  const slideRefs = ensureArray(xml["p:sldIdLst"]?.["p:sldId"]).map((slide, index) => {
    const relationshipId = slide["@_r:id"];
    const rel = relById[relationshipId];
    return {
      id: slide["@_id"] || `slide-${index + 1}`,
      relationshipId,
      path: rel?.targetPath || null,
    };
  });

  return {
    width: emuToInchesNumber(size["@_cx"]),
    height: emuToInchesNumber(size["@_cy"]),
    slideRefs,
  };
}

function parseSlide(pkg, slideRef, zeroIndex) {
  const relationships = pkg.relationshipsBySource.get(slideRef.path) || [];
  const layoutRel = relationships.find((relationship) => relationship.kind === "slideLayout");
  const root = firstOrderedRoot(pkg.orderedXmlParts.get(slideRef.path), "p:sld");
  const shapeTree = findDeep(root, "p:spTree");
  const elements = parseShapeTree(shapeTree, relationships);

  return {
    id: String(slideRef.id),
    index: zeroIndex,
    relationshipId: slideRef.relationshipId,
    path: slideRef.path,
    layoutId: layoutRel?.targetPath || null,
    background: parseBackground(root),
    elements,
    notes: null,
  };
}

function parseReusableParts(pkg, kind, directory) {
  return pkg.entries
    .filter((entry) => entry.kind === kind && entry.path.startsWith(directory) && entry.path.endsWith(".xml"))
    .sort((a, b) => naturalSort(a.path, b.path))
    .map((entry, index) => {
      const relationships = pkg.relationshipsBySource.get(entry.path) || [];
      const rootTag = kind === "master" ? "p:sldMaster" : "p:sldLayout";
      const root = firstOrderedRoot(pkg.orderedXmlParts.get(entry.path), rootTag);
      const shapeTree = findDeep(root, "p:spTree");
      return {
        id: entry.path,
        index,
        path: entry.path,
        name: path.basename(entry.path, ".xml"),
        elements: parseShapeTree(shapeTree, relationships),
        relationships,
      };
    });
}

function parseBackground(root) {
  const background = findDeep(root, "p:bg");
  return background ? { present: true } : null;
}

function mediaType(mediaPath) {
  const extension = mediaPath.split(".").pop()?.toLowerCase();
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(extension)) {
    return "image";
  }
  if (["mp4", "mov", "m4v"].includes(extension)) {
    return "video";
  }
  return extension || "binary";
}

function emuToInchesNumber(value) {
  if (value === undefined || value === null) {
    return null;
  }
  return Number((Number(value) / 914400).toFixed(4));
}

function naturalSort(a, b) {
  return a.localeCompare(b, undefined, { numeric: true });
}
