import fs from "node:fs/promises";
import path from "node:path";
import JSZip from "jszip";
import { applyOperation, applyOperations } from "../operations/deck-operations.js";
import {
  attr,
  buildXmlOrdered,
  findAllDeep,
  findDeep,
  findDirect,
  firstOrderedRoot,
  nodeChildren,
  nodeName,
  parseXmlOrdered,
  setTextNode,
} from "../shared/xml.js";

const SUPPORTED_PACKAGE_OPERATIONS = new Set(["CLONE_SLIDE", "DELETE_SLIDE", "MOVE_SLIDE", "REPLACE_TEXT"]);
const SLIDE_RELATIONSHIP_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide";
const SLIDE_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml";

export async function patchPptxWithOperations({ sourcePptxPath, deck, operations, outputPptxPath }) {
  assertSupportedOperations(operations);
  const sourceBuffer = await fs.readFile(sourcePptxPath);
  const zip = await JSZip.loadAsync(sourceBuffer);
  const { materializedOperations, clonePlans } = materializePackageOperations(deck, operations, zip);
  const finalDeck = applyOperations(deck, materializedOperations);

  await patchCloneOperations(zip, clonePlans);
  await patchTextOperations(zip, finalDeck, materializedOperations);
  await patchPresentationOrder(zip, finalDeck);
  await patchPresentationRelationships(zip, finalDeck);
  await patchContentTypes(zip, finalDeck);
  await patchAppProperties(zip, finalDeck);

  const outputBuffer = await zip.generateAsync({
    type: "nodebuffer",
    compression: "DEFLATE",
  });
  await fs.mkdir(path.dirname(outputPptxPath), { recursive: true });
  await fs.writeFile(outputPptxPath, outputBuffer);

  return finalDeck;
}

export function patchSlideTextXml(slideXml, replacements) {
  if (!replacements.length) {
    return slideXml;
  }

  const parsed = parseXmlOrdered(slideXml);
  const root = firstOrderedRoot(parsed, "p:sld");
  const shapes = findAllDeep(root, "p:sp");
  const replacementByElementId = new Map(replacements.map((replacement) => [String(replacement.elementId), replacement]));
  const applied = new Set();

  for (const shape of shapes) {
    const elementId = attr(findDeep(shape, "p:cNvPr"), "id");
    const replacement = replacementByElementId.get(String(elementId));
    if (!replacement) {
      continue;
    }

    replaceShapeText(shape, replacement.text);
    applied.add(String(elementId));
  }

  for (const replacement of replacements) {
    if (!applied.has(String(replacement.elementId))) {
      throw new Error(`Could not find text element ${replacement.elementId} in ${replacement.slidePath}.`);
    }
  }

  return buildXmlOrdered(parsed);
}

export function patchPresentationXml(presentationXml, finalDeck) {
  const parsed = parseXmlOrdered(presentationXml);
  const root = firstOrderedRoot(parsed, "p:presentation");
  const slideList = findDirect(root, "p:sldIdLst");
  if (!slideList) {
    throw new Error("presentation.xml does not contain p:sldIdLst.");
  }

  const children = slideList["p:sldIdLst"] || [];
  const slideNodes = children.filter((child) => nodeName(child) === "p:sldId");
  const otherNodes = children.filter((child) => nodeName(child) !== "p:sldId");
  const slideNodeById = new Map(slideNodes.map((node) => [String(attr(node, "id")), node]));
  const reorderedSlideNodes = finalDeck.slides.map((slide) => {
    return slideNodeById.get(String(slide.id)) || createSlideIdNode(slide);
  });

  slideList["p:sldIdLst"] = [...reorderedSlideNodes, ...otherNodes];
  return buildXmlOrdered(parsed);
}

export function patchPresentationRelationshipsXml(relsXml, finalDeck) {
  const parsed = parseXmlOrdered(relsXml);
  const root = firstOrderedRoot(parsed, "Relationships");
  if (!root) {
    throw new Error("presentation.xml.rels does not contain Relationships root.");
  }

  const children = root.Relationships || [];
  const nonSlideRelationships = children.filter((child) => {
    return nodeName(child) !== "Relationship" || attr(child, "Type") !== SLIDE_RELATIONSHIP_TYPE;
  });
  const slideRelationshipById = new Map(
    children
      .filter((child) => nodeName(child) === "Relationship" && attr(child, "Type") === SLIDE_RELATIONSHIP_TYPE)
      .map((child) => [String(attr(child, "Id")), child]),
  );
  const slideRelationships = finalDeck.slides.map((slide) => {
    return slideRelationshipById.get(String(slide.relationshipId)) || createSlideRelationshipNode(slide);
  });

  root.Relationships = [...nonSlideRelationships, ...slideRelationships];

  return buildXmlOrdered(parsed);
}

export function patchContentTypesXml(contentTypesXml, finalDeck) {
  const parsed = parseXmlOrdered(contentTypesXml);
  const root = firstOrderedRoot(parsed, "Types");
  if (!root) {
    throw new Error("[Content_Types].xml does not contain Types root.");
  }

  const children = root.Types || [];
  const existingPartNames = new Set(
    children
      .filter((child) => nodeName(child) === "Override")
      .map((child) => attr(child, "PartName")),
  );

  const missingSlideOverrides = finalDeck.slides
    .map((slide) => `/${slide.path}`)
    .filter((partName) => !existingPartNames.has(partName))
    .map((partName) => createContentTypeOverrideNode(partName, SLIDE_CONTENT_TYPE));

  root.Types = [...children, ...missingSlideOverrides];
  return buildXmlOrdered(parsed);
}

export function patchAppPropertiesXml(appXml, finalDeck) {
  const parsed = parseXmlOrdered(appXml);
  const root = firstOrderedRoot(parsed, "Properties");
  const slidesNode = findDirect(root, "Slides");
  if (slidesNode) {
    setTextNode(slidesNode, String(finalDeck.slides.length));
  }
  return buildXmlOrdered(parsed);
}

async function patchTextOperations(zip, deck, operations) {
  const replacementsBySlidePath = groupTextReplacements(deck, operations);
  for (const [slidePath, replacements] of replacementsBySlidePath.entries()) {
    const slideFile = zip.file(slidePath);
    if (!slideFile) {
      throw new Error(`PPTX package is missing ${slidePath}.`);
    }

    const patchedXml = patchSlideTextXml(await slideFile.async("string"), replacements);
    zip.file(slidePath, patchedXml);
  }
}

async function patchCloneOperations(zip, clonePlans) {
  for (const clonePlan of clonePlans) {
    const sourceSlide = zip.file(clonePlan.sourcePath);
    if (!sourceSlide) {
      throw new Error(`CLONE_SLIDE source is missing from package: ${clonePlan.sourcePath}`);
    }

    zip.file(clonePlan.targetPath, await sourceSlide.async("nodebuffer"));

    const sourceRelsPath = slideRelationshipPath(clonePlan.sourcePath);
    const targetRelsPath = slideRelationshipPath(clonePlan.targetPath);
    const sourceRels = zip.file(sourceRelsPath);
    if (sourceRels) {
      zip.file(targetRelsPath, await sourceRels.async("nodebuffer"));
    }
  }
}

async function patchPresentationOrder(zip, finalDeck) {
  const path = "ppt/presentation.xml";
  const file = zip.file(path);
  if (!file) {
    throw new Error("PPTX package is missing ppt/presentation.xml.");
  }

  zip.file(path, patchPresentationXml(await file.async("string"), finalDeck));
}

async function patchPresentationRelationships(zip, finalDeck) {
  const path = "ppt/_rels/presentation.xml.rels";
  const file = zip.file(path);
  if (!file) {
    throw new Error("PPTX package is missing ppt/_rels/presentation.xml.rels.");
  }

  zip.file(path, patchPresentationRelationshipsXml(await file.async("string"), finalDeck));
}

async function patchContentTypes(zip, finalDeck) {
  const path = "[Content_Types].xml";
  const file = zip.file(path);
  if (!file) {
    throw new Error("PPTX package is missing [Content_Types].xml.");
  }

  zip.file(path, patchContentTypesXml(await file.async("string"), finalDeck));
}

async function patchAppProperties(zip, finalDeck) {
  const path = "docProps/app.xml";
  const file = zip.file(path);
  if (!file) {
    return;
  }

  zip.file(path, patchAppPropertiesXml(await file.async("string"), finalDeck));
}

function groupTextReplacements(deck, operations) {
  const replacementsBySlidePath = new Map();
  for (const operation of operations.filter((op) => op.type === "REPLACE_TEXT")) {
    const slide = deck.slides.find((candidate) => String(candidate.id) === String(operation.slideId));
    if (!slide) {
      throw new Error(`REPLACE_TEXT could not find slide ${operation.slideId}.`);
    }
    if (!slide.path) {
      throw new Error(`REPLACE_TEXT slide ${operation.slideId} does not have a source path.`);
    }

    const replacements = replacementsBySlidePath.get(slide.path) || [];
    replacements.push({
      slidePath: slide.path,
      elementId: operation.elementId,
      text: operation.text,
    });
    replacementsBySlidePath.set(slide.path, replacements);
  }
  return replacementsBySlidePath;
}

function replaceShapeText(shape, text) {
  const textBody = findDeep(shape, "p:txBody");
  if (!textBody) {
    throw new Error(`Shape ${attr(findDeep(shape, "p:cNvPr"), "id")} does not have a text body.`);
  }

  const children = textBody["p:txBody"] || [];
  const paragraphs = children.filter((child) => nodeName(child) === "a:p");
  if (!paragraphs.length) {
    throw new Error(`Shape ${attr(findDeep(shape, "p:cNvPr"), "id")} does not contain text paragraphs.`);
  }

  const lines = text.split(/\r?\n/);
  const firstParagraphIndex = children.findIndex((child) => nodeName(child) === "a:p");
  const paragraphTemplate = structuredClone(paragraphs[0]);
  const newParagraphs = lines.map((line) => {
    const paragraph = structuredClone(paragraphTemplate);
    setParagraphText(paragraph, line);
    return paragraph;
  });

  textBody["p:txBody"] = [
    ...children.slice(0, firstParagraphIndex),
    ...newParagraphs,
    ...children.slice(firstParagraphIndex).filter((child) => nodeName(child) !== "a:p"),
  ];
}

function setParagraphText(paragraph, text) {
  const textNodes = findAllDeep(paragraph, "a:t");
  if (!textNodes.length) {
    throw new Error("Text paragraph does not contain an a:t node.");
  }

  setTextNode(textNodes[0], text);
  for (const extraTextNode of textNodes.slice(1)) {
    setTextNode(extraTextNode, "");
  }
}

function materializePackageOperations(deck, operations, zip) {
  const materializedOperations = [];
  const clonePlans = [];
  let workingDeck = structuredClone(deck);
  const ids = collectPackageIds(deck, zip);

  for (const operation of operations) {
    let materialized = operation;
    if (operation.type === "CLONE_SLIDE") {
      const sourceSlide = workingDeck.slides.find((slide) => String(slide.id) === String(operation.sourceSlideId));
      if (!sourceSlide) {
        throw new Error(`CLONE_SLIDE could not find source slide: ${operation.sourceSlideId}`);
      }
      if (!sourceSlide.path) {
        throw new Error(`CLONE_SLIDE source slide ${operation.sourceSlideId} does not have a source path.`);
      }

      materialized = {
        ...operation,
        newSlideId: operation.newSlideId || nextSlideId(ids),
        newRelationshipId: operation.newRelationshipId || nextRelationshipId(ids),
        newPath: operation.newPath || nextSlidePath(ids),
      };

      rememberMaterializedClone(ids, materialized);
      clonePlans.push({
        sourcePath: sourceSlide.path,
        targetPath: materialized.newPath,
      });
    }

    materializedOperations.push(materialized);
    workingDeck = applyOperation(workingDeck, materialized);
  }

  return { materializedOperations, clonePlans };
}

function collectPackageIds(deck, zip) {
  const numericSlideIds = deck.slides.map((slide) => Number(slide.id)).filter(Number.isFinite);
  const slidePaths = new Set([
    ...Object.keys(zip.files).filter((entryPath) => /^ppt\/slides\/slide\d+\.xml$/.test(entryPath)),
    ...deck.slides.map((slide) => slide.path).filter(Boolean),
  ]);
  const relationshipIds = new Set(
    (deck.package?.relationships || [])
      .filter((relationship) => relationship.sourcePath === "ppt/presentation.xml")
      .map((relationship) => relationship.id)
      .filter(Boolean),
  );

  return {
    nextSlideIdNumber: Math.max(255, ...numericSlideIds) + 1,
    relationshipIds,
    slidePaths,
  };
}

function nextSlideId(ids) {
  const value = String(ids.nextSlideIdNumber);
  ids.nextSlideIdNumber += 1;
  return value;
}

function nextRelationshipId(ids) {
  let index = 1;
  for (const relationshipId of ids.relationshipIds) {
    const match = /^rId(\d+)$/.exec(String(relationshipId));
    if (match) {
      index = Math.max(index, Number(match[1]) + 1);
    }
  }

  let candidate = `rId${index}`;
  while (ids.relationshipIds.has(candidate)) {
    index += 1;
    candidate = `rId${index}`;
  }
  ids.relationshipIds.add(candidate);
  return candidate;
}

function nextSlidePath(ids) {
  let index = 1;
  for (const slidePath of ids.slidePaths) {
    const match = /^ppt\/slides\/slide(\d+)\.xml$/.exec(slidePath);
    if (match) {
      index = Math.max(index, Number(match[1]) + 1);
    }
  }

  let candidate = `ppt/slides/slide${index}.xml`;
  while (ids.slidePaths.has(candidate)) {
    index += 1;
    candidate = `ppt/slides/slide${index}.xml`;
  }
  ids.slidePaths.add(candidate);
  return candidate;
}

function rememberMaterializedClone(ids, operation) {
  ids.slidePaths.add(operation.newPath);
  ids.relationshipIds.add(operation.newRelationshipId);
  const numericSlideId = Number(operation.newSlideId);
  if (Number.isFinite(numericSlideId)) {
    ids.nextSlideIdNumber = Math.max(ids.nextSlideIdNumber, numericSlideId + 1);
  }
}

function createSlideIdNode(slide) {
  if (!slide.relationshipId) {
    throw new Error(`Slide ${slide.id} is missing relationshipId.`);
  }

  return {
    "p:sldId": [],
    ":@": {
      "@_id": String(slide.id),
      "@_r:id": String(slide.relationshipId),
    },
  };
}

function createSlideRelationshipNode(slide) {
  if (!slide.relationshipId || !slide.path) {
    throw new Error(`Slide ${slide.id} is missing relationshipId or path.`);
  }

  return {
    Relationship: [],
    ":@": {
      "@_Id": String(slide.relationshipId),
      "@_Target": slide.path.replace(/^ppt\//, ""),
      "@_Type": SLIDE_RELATIONSHIP_TYPE,
    },
  };
}

function createContentTypeOverrideNode(partName, contentType) {
  return {
    Override: [],
    ":@": {
      "@_PartName": partName,
      "@_ContentType": contentType,
    },
  };
}

function slideRelationshipPath(slidePath) {
  const filename = path.posix.basename(slidePath);
  return `${path.posix.dirname(slidePath)}/_rels/${filename}.rels`;
}

function assertSupportedOperations(operations) {
  if (!Array.isArray(operations)) {
    throw new Error("Operations payload must be an array.");
  }

  const unsupported = operations.find((operation) => !SUPPORTED_PACKAGE_OPERATIONS.has(operation.type));
  if (unsupported) {
    throw new Error(`OOXML patcher does not support ${unsupported.type} yet.`);
  }
}
