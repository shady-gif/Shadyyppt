export const FONT_OPTIONS = [
  "Inter",
  "Poppins",
  "Montserrat",
  "Roboto",
  "Playfair Display",
] as const;

export type FontOption = (typeof FONT_OPTIONS)[number];

export const ANIMATION_OPTIONS = ["none", "fade", "zoom", "wipe", "fly"] as const;

export type AnimationOption = (typeof ANIMATION_OPTIONS)[number];

export type SlideObjectType = "text" | "image" | "shape";

export interface EditorDeck {
  templateId: string;
  templateName: string;
  sourceJsonPath?: string | null;
  sourceKind?: "template" | "generated";
  size: {
    widthInches: number;
    heightInches: number;
  };
  slides: EditorSlide[];
}

export interface EditorSlide {
  id: string;
  index: number;
  sourceSlideIndex: number;
  background: string;
  objects: SlideObject[];
}

export interface BaseSlideObject {
  id: string;
  sourceId: string;
  name: string;
  type: SlideObjectType;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  zIndex: number;
  enterAnimation: AnimationOption;
  exitAnimation: AnimationOption;
}

export interface TextSlideObject extends BaseSlideObject {
  type: "text";
  text: string;
  font: FontOption;
  color: string;
  fontSize: number;
}

export interface ImageSlideObject extends BaseSlideObject {
  type: "image";
  imageUrl?: string;
  assetPath?: string;
}

export interface ShapeSlideObject extends BaseSlideObject {
  type: "shape";
  geometryType?: string;
  fillColor: string;
  lineColor: string;
}

export type SlideObject = TextSlideObject | ImageSlideObject | ShapeSlideObject;

export interface AnimationMetadata {
  schemaVersion: 1;
  pptAnimationExport: boolean;
  objects: Array<{
    slideId: string;
    objectId: string;
    enterAnimation: AnimationOption;
    exitAnimation: AnimationOption;
  }>;
}

export type EditorOperation =
  | {
      type: "updateText";
      slideId: string;
      objectId: string;
      text: string;
    }
  | {
      type: "moveObject";
      slideId: string;
      objectId: string;
      x: number;
      y: number;
    }
  | {
      type: "resizeObject";
      slideId: string;
      objectId: string;
      width: number;
      height: number;
    }
  | {
      type: "changeFont";
      slideId: string;
      objectId: string;
      font: FontOption;
    }
  | {
      type: "changeTextColor";
      slideId: string;
      objectId: string;
      color: string;
    }
  | {
      type: "changeBackgroundColor";
      slideId: string;
      color: string;
    }
  | {
      type: "replaceImage";
      slideId: string;
      objectId: string;
      assetPath: string;
    }
  | {
      type: "setEnterAnimation";
      slideId: string;
      objectId: string;
      animation: AnimationOption;
    }
  | {
      type: "setExitAnimation";
      slideId: string;
      objectId: string;
      animation: AnimationOption;
    };

export interface TemplateOption {
  id: string;
  name: string;
  previewPath?: string;
}
