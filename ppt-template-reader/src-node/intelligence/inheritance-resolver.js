const GEOMETRY_FIELDS = ["x", "y", "w", "h", "rotation"];

export function resolveDeckInheritance(deck) {
  const mastersById = new Map(deck.masters.map((master) => [master.id, master]));
  const layoutsById = new Map(deck.layouts.map((layout) => [layout.id, layout]));

  const resolvedMasters = deck.masters.map((master) => ({
    ...master,
    elements: master.elements.map((element) => prepareElement(element)),
  }));

  const resolvedMastersById = new Map(resolvedMasters.map((master) => [master.id, master]));

  const resolvedLayouts = deck.layouts.map((layout) => {
    const masterId = findRelationshipTarget(layout.relationships, "slideMaster");
    const originalMaster = mastersById.get(masterId);
    const resolvedMaster = resolvedMastersById.get(masterId);
    const masterElements = resolvedMaster?.elements || originalMaster?.elements || [];

    return {
      ...layout,
      masterId: masterId || null,
      elements: layout.elements.map((element) => {
        const prepared = prepareElement(element);
        const parent = findPlaceholderParent(prepared, masterElements);
        return parent
          ? inheritElement(prepared, parent, {
              source: "master",
              sourcePartId: masterId,
              sourceElementId: parent.id,
            })
          : prepared;
      }),
    };
  });

  const resolvedLayoutsById = new Map(resolvedLayouts.map((layout) => [layout.id, layout]));

  const resolvedSlides = deck.slides.map((slide) => {
    const layout = resolvedLayoutsById.get(slide.layoutId) || layoutsById.get(slide.layoutId);
    const layoutElements = layout?.elements || [];

    return {
      ...slide,
      elements: slide.elements.map((element) => {
        const prepared = prepareElement(element);
        const parent = findPlaceholderParent(prepared, layoutElements);
        return parent
          ? inheritElement(prepared, parent, {
              source: "layout",
              sourcePartId: slide.layoutId,
              sourceElementId: parent.id,
            })
          : prepared;
      }),
    };
  });

  return {
    ...deck,
    masters: resolvedMasters,
    layouts: resolvedLayouts,
    slides: resolvedSlides,
    inheritance: summarizeInheritance(resolvedLayouts, resolvedSlides),
  };
}

function prepareElement(element) {
  return {
    ...element,
    raw: {
      geometry: pickGeometry(element),
      style: element.style || {},
    },
    inheritance: element.inheritance || [],
  };
}

function inheritElement(element, parent, source) {
  const geometryResult = inheritGeometry(element, parent, source);
  const styleResult = inheritStyle(geometryResult.element, parent, source);
  const inheritedFields = [...geometryResult.fields, ...styleResult.fields.map((field) => `style.${field}`)];

  if (inheritedFields.length === 0) {
    return styleResult.element;
  }

  return {
    ...styleResult.element,
    inheritance: [
      ...(styleResult.element.inheritance || []),
      {
        ...source,
        fields: inheritedFields,
      },
    ],
  };
}

function inheritGeometry(element, parent) {
  const fields = [];
  const next = { ...element };

  for (const field of GEOMETRY_FIELDS) {
    if (isMissing(next[field]) && !isMissing(parent[field])) {
      next[field] = parent[field];
      fields.push(field);
    }
  }

  return { element: next, fields };
}

function inheritStyle(element, parent) {
  const fields = [];
  const nextStyle = { ...(element.style || {}) };
  const parentStyle = parent.style || {};

  for (const [field, value] of Object.entries(parentStyle)) {
    if (isMissing(nextStyle[field]) && !isMissing(value)) {
      nextStyle[field] = value;
      fields.push(field);
    }
  }

  return {
    element: {
      ...element,
      style: nextStyle,
    },
    fields,
  };
}

function findPlaceholderParent(element, candidates) {
  if (!element.placeholder) {
    return null;
  }

  const exactIndex = candidates.find((candidate) => {
    return candidate.placeholder
      && candidate.placeholder.index
      && candidate.placeholder.index === element.placeholder.index
      && candidate.placeholder.type === element.placeholder.type;
  });
  if (exactIndex) {
    return exactIndex;
  }

  const typeMatch = candidates.find((candidate) => {
    return candidate.placeholder
      && candidate.placeholder.type
      && candidate.placeholder.type === element.placeholder.type;
  });
  if (typeMatch) {
    return typeMatch;
  }

  const indexMatch = candidates.find((candidate) => {
    return candidate.placeholder
      && candidate.placeholder.index
      && candidate.placeholder.index === element.placeholder.index;
  });
  if (indexMatch) {
    return indexMatch;
  }

  return null;
}

function findRelationshipTarget(relationships = [], kind) {
  return relationships.find((relationship) => relationship.kind === kind)?.targetPath || null;
}

function pickGeometry(element) {
  return Object.fromEntries(GEOMETRY_FIELDS.map((field) => [field, element[field] ?? null]));
}

function isMissing(value) {
  return value === undefined || value === null;
}

function summarizeInheritance(layouts, slides) {
  return {
    layoutElementsWithInheritedValues: countInheritedElements(layouts),
    slideElementsWithInheritedValues: countInheritedElements(slides),
  };
}

function countInheritedElements(parts) {
  return parts.reduce((count, part) => {
    return count + part.elements.filter((element) => element.inheritance?.length).length;
  }, 0);
}

