import { XMLBuilder, XMLParser } from "fast-xml-parser";

export const ATTRS = ":@";
export const ATTR_PREFIX = "@_";
export const EMU_PER_INCH = 914400;

const xmlParser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: ATTR_PREFIX,
  trimValues: false,
  parseAttributeValue: false,
  parseTagValue: false,
});

const orderedXmlParser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: ATTR_PREFIX,
  preserveOrder: true,
  trimValues: false,
  parseAttributeValue: false,
  parseTagValue: false,
});

const orderedXmlBuilder = new XMLBuilder({
  ignoreAttributes: false,
  attributeNamePrefix: ATTR_PREFIX,
  preserveOrder: true,
  suppressEmptyNode: true,
});

export function parseXml(xml) {
  return xmlParser.parse(xml);
}

export function parseXmlOrdered(xml) {
  return orderedXmlParser.parse(xml);
}

export function buildXmlOrdered(xml) {
  return orderedXmlBuilder.build(xml);
}

export function ensureArray(value) {
  if (value === undefined || value === null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

export function emuToInches(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return null;
  }
  return Number((Number(value) / EMU_PER_INCH).toFixed(4));
}

export function nodeName(node) {
  return Object.keys(node || {}).find((key) => key !== ATTRS);
}

export function nodeChildren(node) {
  const name = nodeName(node);
  if (!name) {
    return [];
  }
  return ensureArray(node[name]).filter((child) => typeof child === "object");
}

export function attrs(node) {
  const raw = node?.[ATTRS] || {};
  return Object.fromEntries(
    Object.entries(raw).map(([key, value]) => [key.replace(ATTR_PREFIX, ""), value]),
  );
}

export function attr(node, name) {
  return node?.[ATTRS]?.[`${ATTR_PREFIX}${name}`] ?? null;
}

export function findDirect(node, tagName) {
  return nodeChildren(node).find((child) => nodeName(child) === tagName) || null;
}

export function findAllDirect(node, tagName) {
  return nodeChildren(node).filter((child) => nodeName(child) === tagName);
}

export function findDeep(node, tagName) {
  if (!node) {
    return null;
  }
  if (nodeName(node) === tagName) {
    return node;
  }
  for (const child of nodeChildren(node)) {
    const found = findDeep(child, tagName);
    if (found) {
      return found;
    }
  }
  return null;
}

export function findAllDeep(node, tagName, results = []) {
  if (!node) {
    return results;
  }
  if (nodeName(node) === tagName) {
    results.push(node);
  }
  for (const child of nodeChildren(node)) {
    findAllDeep(child, tagName, results);
  }
  return results;
}

export function textContent(node) {
  if (!node) {
    return "";
  }

  let text = "";
  for (const child of nodeChildren(node)) {
    const name = nodeName(child);
    if (name === "#text") {
      text += ensureArray(child[name]).join("");
    } else {
      text += textContent(child);
    }
  }
  return text;
}

export function firstOrderedRoot(orderedXml, tagName) {
  return ensureArray(orderedXml).find((node) => nodeName(node) === tagName) || null;
}

export function setTextNode(node, text) {
  if (!node) {
    return;
  }

  const name = nodeName(node);
  if (!name) {
    return;
  }

  node[name] = [{ "#text": text }];
}
