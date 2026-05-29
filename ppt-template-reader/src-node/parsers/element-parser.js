import {
  attr,
  attrs,
  emuToInches,
  findAllDeep,
  findDeep,
  findDirect,
  findAllDirect,
  nodeChildren,
  nodeName,
  textContent,
} from "../shared/xml.js";

export function parseShapeTree(shapeTree, relationships = [], options = {}) {
  if (!shapeTree) {
    return [];
  }

  const elements = [];
  for (const child of nodeChildren(shapeTree)) {
    const tag = nodeName(child);
    if (!["p:sp", "p:pic", "p:graphicFrame", "p:grpSp", "p:cxnSp", "p:contentPart"].includes(tag)) {
      continue;
    }
    elements.push(parseElement(child, elements.length, relationships, options));
  }
  return elements;
}

export function parseElement(node, zIndex = 0, relationships = [], options = {}) {
  const tag = nodeName(node);
  const common = parseCommon(node, zIndex);
  const relationshipLookup = Object.fromEntries(relationships.map((relationship) => [relationship.id, relationship]));

  if (tag === "p:grpSp") {
    const groupShapeTree = node;
    return {
      ...common,
      type: "group",
      elements: parseShapeTree(groupShapeTree, relationships, options),
    };
  }

  if (tag === "p:pic") {
    const embedId = attr(findDeep(node, "a:blip"), "r:embed");
    return {
      ...common,
      type: "image",
      assetRef: relationshipLookup[embedId]?.targetPath || null,
      relationshipId: embedId,
      style: parseShapeStyle(node),
    };
  }

  if (tag === "p:graphicFrame") {
    return {
      ...common,
      type: graphicFrameType(node),
      relationshipId: attr(findDeep(node, "c:chart"), "r:id"),
      style: {},
    };
  }

  const text = parseText(node);
  return {
    ...common,
    type: text.raw ? "text" : "shape",
    geometryType: attr(findDeep(node, "a:prstGeom"), "prst") || (findDeep(node, "a:custGeom") ? "custom" : null),
    style: parseShapeStyle(node),
    text: text.raw ? text : undefined,
  };
}

function parseCommon(node, zIndex) {
  const nonVisualProps = findDeep(node, "p:cNvPr");
  const placeholder = findDeep(node, "p:ph");
  return {
    id: attr(nonVisualProps, "id"),
    name: attr(nonVisualProps, "name"),
    x: parseGeometry(node).x,
    y: parseGeometry(node).y,
    w: parseGeometry(node).w,
    h: parseGeometry(node).h,
    rotation: parseGeometry(node).rotation,
    zIndex,
    placeholder: parsePlaceholder(placeholder),
  };
}

function parseGeometry(node) {
  const transform = findDeep(node, "a:xfrm");
  const offset = findDirect(transform, "a:off");
  const extent = findDirect(transform, "a:ext");
  const rotation = attr(transform, "rot");
  return {
    x: emuToInches(attr(offset, "x")),
    y: emuToInches(attr(offset, "y")),
    w: emuToInches(attr(extent, "cx")),
    h: emuToInches(attr(extent, "cy")),
    rotation: rotation === null ? 0 : Number((Number(rotation) / 60000).toFixed(4)),
  };
}

function parsePlaceholder(placeholder) {
  if (!placeholder) {
    return undefined;
  }
  return {
    type: normalizePlaceholderRole(attr(placeholder, "type")),
    rawType: attr(placeholder, "type"),
    index: attr(placeholder, "idx"),
    size: attr(placeholder, "sz"),
  };
}

function parseShapeStyle(node) {
  const shapeProps = findDirect(node, "p:spPr") || findDirect(node, "p:picPr") || findDeep(node, "p:spPr");
  const textBody = findDeep(node, "p:txBody");
  const paragraph = findDirect(textBody, "a:p");
  const paragraphProps = findDirect(paragraph, "a:pPr");
  const runProps = findDeep(node, "a:rPr") || findDeep(node, "a:defRPr");

  return {
    fill: parseFill(shapeProps),
    line: parseLine(findDirect(shapeProps, "a:ln")),
    fontFamily: parseFontFamily(runProps),
    fontSize: parseFontSize(runProps),
    bold: parseBoolean(attr(runProps, "b")),
    italic: parseBoolean(attr(runProps, "i")),
    color: parseColor(runProps),
    align: attr(paragraphProps, "algn"),
  };
}

function parseText(node) {
  const textBody = findDeep(node, "p:txBody");
  if (!textBody) {
    return { raw: "", paragraphs: [], runs: [] };
  }

  const paragraphs = findAllDirect(textBody, "a:p").map(parseParagraph);
  const raw = paragraphs.map((paragraph) => paragraph.raw).join("\n").trim();
  return {
    raw,
    paragraphs,
    runs: paragraphs.flatMap((paragraph) => paragraph.runs),
    autoFit: Boolean(findDeep(textBody, "a:spAutoFit") || findDeep(textBody, "a:normAutofit")),
  };
}

function parseParagraph(paragraph) {
  const paragraphProps = findDirect(paragraph, "a:pPr");
  const runs = nodeChildren(paragraph)
    .filter((child) => ["a:r", "a:fld", "a:br"].includes(nodeName(child)))
    .map(parseRun);
  return {
    raw: runs.map((run) => run.text).join(""),
    align: attr(paragraphProps, "algn"),
    level: attr(paragraphProps, "lvl") === null ? null : Number(attr(paragraphProps, "lvl")),
    bullet: parseBullet(paragraphProps),
    runs,
  };
}

function parseRun(run) {
  if (nodeName(run) === "a:br") {
    return { text: "\n", style: {} };
  }

  const runProps = findDirect(run, "a:rPr");
  const textNode = findDirect(run, "a:t");
  return {
    text: textContent(textNode),
    style: {
      fontFamily: parseFontFamily(runProps),
      fontSize: parseFontSize(runProps),
      bold: parseBoolean(attr(runProps, "b")),
      italic: parseBoolean(attr(runProps, "i")),
      underline: attr(runProps, "u"),
      color: parseColor(runProps),
    },
  };
}

function parseFill(parent) {
  if (!parent) {
    return undefined;
  }
  if (findDirect(parent, "a:noFill")) {
    return { type: "none" };
  }
  const solid = findDirect(parent, "a:solidFill");
  if (solid) {
    return { type: "solid", color: parseColor(solid) };
  }
  if (findDirect(parent, "a:gradFill")) {
    return { type: "gradient" };
  }
  if (findDirect(parent, "a:blipFill")) {
    return { type: "image" };
  }
  return undefined;
}

function parseLine(line) {
  if (!line) {
    return undefined;
  }
  return {
    width: attr(line, "w") === null ? null : Number(attr(line, "w")),
    fill: parseFill(line),
    color: parseColor(line),
  };
}

function parseColor(parent) {
  if (!parent) {
    return undefined;
  }

  const srgb = findDeep(parent, "a:srgbClr");
  if (srgb) {
    return `#${attr(srgb, "val")}`;
  }

  const scheme = findDeep(parent, "a:schemeClr");
  if (scheme) {
    return { scheme: attr(scheme, "val"), transforms: colorTransforms(scheme) };
  }

  const preset = findDeep(parent, "a:prstClr");
  if (preset) {
    return { preset: attr(preset, "val") };
  }

  return undefined;
}

function colorTransforms(colorNode) {
  return nodeChildren(colorNode)
    .filter((child) => nodeName(child).startsWith("a:"))
    .map((child) => ({ type: nodeName(child).replace("a:", ""), ...attrs(child) }));
}

function parseFontFamily(runProps) {
  const latin = findDirect(runProps, "a:latin");
  const ea = findDirect(runProps, "a:ea");
  const cs = findDirect(runProps, "a:cs");
  return attr(latin, "typeface") || attr(ea, "typeface") || attr(cs, "typeface") || undefined;
}

function parseFontSize(runProps) {
  const size = attr(runProps, "sz");
  return size === null ? undefined : Number(size) / 100;
}

function parseBoolean(value) {
  if (value === null || value === undefined) {
    return undefined;
  }
  return value === "1" || value === "true";
}

function parseBullet(paragraphProps) {
  if (!paragraphProps) {
    return undefined;
  }
  if (findDirect(paragraphProps, "a:buNone")) {
    return { type: "none" };
  }
  const character = findDirect(paragraphProps, "a:buChar");
  if (character) {
    return { type: "character", character: attr(character, "char") };
  }
  const autoNumber = findDirect(paragraphProps, "a:buAutoNum");
  if (autoNumber) {
    return { type: "autoNumber", scheme: attr(autoNumber, "type") };
  }
  return undefined;
}

function graphicFrameType(node) {
  if (findDeep(node, "a:tbl")) {
    return "table";
  }
  if (findDeep(node, "c:chart")) {
    return "chart";
  }
  return "graphic";
}

function normalizePlaceholderRole(rawType) {
  const roleMap = {
    null: "body",
    undefined: "body",
    title: "title",
    ctrTitle: "title",
    subTitle: "subtitle",
    obj: "body",
    body: "body",
    pic: "image",
    chart: "chart",
    tbl: "table",
    ftr: "footer",
    dt: "date",
    sldNum: "slideNumber",
  };
  return roleMap[rawType] || rawType || null;
}
