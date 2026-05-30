import type { EditorDeck, EditorOperation, EditorSlide, SlideObject } from "./types";

export function applyEditorOperation(deck: EditorDeck, operation: EditorOperation): EditorDeck {
  const copy: EditorDeck = structuredClone(deck);
  const slide = requireSlide(copy, operation.slideId);

  switch (operation.type) {
    case "changeBackgroundColor":
      slide.background = operation.color;
      return copy;
    case "updateText": {
      const object = requireObject(slide, operation.objectId);
      if (object.type === "text") {
        object.text = operation.text;
      }
      return copy;
    }
    case "moveObject": {
      const object = requireObject(slide, operation.objectId);
      object.x = operation.x;
      object.y = operation.y;
      return copy;
    }
    case "resizeObject": {
      const object = requireObject(slide, operation.objectId);
      object.width = operation.width;
      object.height = operation.height;
      return copy;
    }
    case "changeFont": {
      const object = requireObject(slide, operation.objectId);
      if (object.type === "text") {
        object.font = operation.font;
      }
      return copy;
    }
    case "changeTextColor": {
      const object = requireObject(slide, operation.objectId);
      if (object.type === "text") {
        object.color = operation.color;
      }
      return copy;
    }
    case "replaceImage": {
      const object = requireObject(slide, operation.objectId);
      if (object.type === "image") {
        object.assetPath = operation.assetPath;
      }
      return copy;
    }
    case "setEnterAnimation": {
      const object = requireObject(slide, operation.objectId);
      object.enterAnimation = operation.animation;
      return copy;
    }
    case "setExitAnimation": {
      const object = requireObject(slide, operation.objectId);
      object.exitAnimation = operation.animation;
      return copy;
    }
    default:
      return exhaustive(operation);
  }
}

export function mergeOperation(operations: EditorOperation[], next: EditorOperation): EditorOperation[] {
  const nextKey = operationKey(next);
  return [...operations.filter((operation) => operationKey(operation) !== nextKey), next];
}

export function roundInches(value: number): number {
  return Number(value.toFixed(4));
}

function operationKey(operation: EditorOperation): string {
  if (operation.type === "changeBackgroundColor") {
    return `${operation.type}:${operation.slideId}`;
  }
  return `${operation.type}:${operation.slideId}:${operation.objectId}`;
}

function requireSlide(deck: EditorDeck, slideId: string): EditorSlide {
  const slide = deck.slides.find((candidate) => candidate.id === slideId);
  if (!slide) {
    throw new Error(`Unknown slide: ${slideId}`);
  }
  return slide;
}

function requireObject(slide: EditorSlide, objectId: string): SlideObject {
  const object = slide.objects.find((candidate) => candidate.id === objectId);
  if (!object) {
    throw new Error(`Unknown object: ${objectId}`);
  }
  return object;
}

function exhaustive(value: never): never {
  throw new Error(`Unhandled editor operation: ${JSON.stringify(value)}`);
}
