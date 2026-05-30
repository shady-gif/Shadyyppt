import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Konva from "konva";
import { Ellipse, Group, Image as KonvaImage, Layer, Rect, Stage, Text, Transformer } from "react-konva";
import { assetUrl } from "./api";
import { roundInches } from "./operations";
import type { EditorDeck, EditorSlide, ImageSlideObject, ShapeSlideObject, SlideObject } from "./types";

interface SlideCanvasProps {
  deck: EditorDeck;
  slide: EditorSlide;
  selectedObjectId: string | null;
  onSelectObject: (objectId: string | null) => void;
  onMoveObject: (object: SlideObject, x: number, y: number) => void;
  onResizeObject: (object: SlideObject, geometry: { x: number; y: number; width: number; height: number }) => void;
}

const MAX_STAGE_WIDTH = 980;
const MIN_OBJECT_SIZE_INCHES = 0.15;
const MIN_OBJECT_SIZE_PX = 18;
const POINTS_PER_INCH = 72;

export function SlideCanvas({
  deck,
  slide,
  selectedObjectId,
  onSelectObject,
  onMoveObject,
  onResizeObject,
}: SlideCanvasProps) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const transformerRef = useRef<Konva.Transformer | null>(null);
  const objectNodeRefs = useRef(new Map<string, Konva.Node>());
  const [wrapWidth, setWrapWidth] = useState(MAX_STAGE_WIDTH);

  useLayoutEffect(() => {
    const element = wrapRef.current;
    if (!element) {
      return;
    }

    const observer = new ResizeObserver(([entry]) => {
      setWrapWidth(Math.max(320, Math.min(MAX_STAGE_WIDTH, entry.contentRect.width)));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const stageWidth = Math.min(MAX_STAGE_WIDTH, wrapWidth);
  const stageHeight = stageWidth * (deck.size.heightInches / deck.size.widthInches);
  const scale = stageWidth / deck.size.widthInches;

  const attachTransformer = useCallback(() => {
    const transformer = transformerRef.current;
    if (!transformer) {
      return;
    }

    const selectedNode = selectedObjectId ? objectNodeRefs.current.get(selectedObjectId) : null;
    transformer.nodes(selectedNode ? [selectedNode] : []);
    transformer.moveToTop();
    transformer.getLayer()?.batchDraw();
  }, [selectedObjectId]);

  const registerObjectNode = useCallback(
    (objectId: string, node: Konva.Node | null) => {
      if (node) {
        objectNodeRefs.current.set(objectId, node);
      } else {
        objectNodeRefs.current.delete(objectId);
      }

      if (objectId === selectedObjectId) {
        window.requestAnimationFrame(attachTransformer);
      }
    },
    [attachTransformer, selectedObjectId],
  );

  const sortedObjects = useMemo(
    () => [...slide.objects].sort((left, right) => left.zIndex - right.zIndex),
    [slide.objects],
  );

  useLayoutEffect(() => {
    attachTransformer();
  }, [attachTransformer, selectedObjectId, slide.id, sortedObjects]);

  return (
    <div className="canvasWrap" ref={wrapRef}>
      <Stage
        width={stageWidth}
        height={stageHeight}
        className="slideStage"
        onMouseDown={(event) => {
          if (event.target === event.target.getStage()) {
            onSelectObject(null);
          }
        }}
      >
        <Layer>
          <Rect width={stageWidth} height={stageHeight} fill={slide.background} listening={false} />
          {sortedObjects.map((object) => (
            <CanvasObject
              key={object.id}
              object={object}
              scale={scale}
              isSelected={object.id === selectedObjectId}
              registerNode={registerObjectNode}
              onSelect={() => onSelectObject(object.id)}
              onMove={(x, y) => onMoveObject(object, x, y)}
              onResize={(geometry) => onResizeObject(object, geometry)}
            />
          ))}
          <Transformer
            ref={transformerRef}
            rotateEnabled
            flipEnabled={false}
            keepRatio={false}
            enabledAnchors={[
              "top-left",
              "top-center",
              "top-right",
              "middle-left",
              "middle-right",
              "bottom-left",
              "bottom-center",
              "bottom-right",
            ]}
            borderStroke="#2563eb"
            borderStrokeWidth={2}
            borderDash={[6, 4]}
            anchorFill="#ffffff"
            anchorStroke="#2563eb"
            anchorStrokeWidth={2}
            anchorSize={12}
            anchorCornerRadius={3}
            padding={5}
            rotateAnchorOffset={28}
            boundBoxFunc={(oldBox, newBox) => {
              if (newBox.width < MIN_OBJECT_SIZE_PX || newBox.height < MIN_OBJECT_SIZE_PX) {
                return oldBox;
              }
              return newBox;
            }}
          />
        </Layer>
      </Stage>
    </div>
  );
}

interface CanvasObjectProps {
  object: SlideObject;
  scale: number;
  isSelected: boolean;
  registerNode: (objectId: string, node: Konva.Node | null) => void;
  onSelect: () => void;
  onMove: (x: number, y: number) => void;
  onResize: (geometry: { x: number; y: number; width: number; height: number }) => void;
}

function CanvasObject({ object, scale, isSelected, registerNode, onSelect, onMove, onResize }: CanvasObjectProps) {
  const width = Math.max(1, object.width * scale);
  const height = Math.max(1, object.height * scale);
  const common = {
    id: object.id,
    ref: (node: Konva.Node | null) => registerNode(object.id, node),
    x: object.x * scale,
    y: object.y * scale,
    width,
    height,
    rotation: object.rotation,
    draggable: true,
    onMouseDown: (event: Konva.KonvaEventObject<MouseEvent>) => {
      event.cancelBubble = true;
      onSelect();
    },
    onTap: (event: Konva.KonvaEventObject<Event>) => {
      event.cancelBubble = true;
      onSelect();
    },
    onDragStart: () => onSelect(),
    onDragEnd: (event: Konva.KonvaEventObject<DragEvent>) => {
      onMove(roundInches(event.target.x() / scale), roundInches(event.target.y() / scale));
    },
    onTransformEnd: (event: Konva.KonvaEventObject<Event>) => {
      const node = event.target;
      const nextWidth = Math.max(MIN_OBJECT_SIZE_INCHES, (node.width() * node.scaleX()) / scale);
      const nextHeight = Math.max(MIN_OBJECT_SIZE_INCHES, (node.height() * node.scaleY()) / scale);
      const nextX = roundInches(node.x() / scale);
      const nextY = roundInches(node.y() / scale);

      node.width(nextWidth * scale);
      node.height(nextHeight * scale);
      node.scaleX(1);
      node.scaleY(1);
      onResize({
        x: nextX,
        y: nextY,
        width: roundInches(nextWidth),
        height: roundInches(nextHeight),
      });
    },
    onMouseEnter: (event: Konva.KonvaEventObject<MouseEvent>) => {
      const stage = event.target.getStage();
      if (stage) {
        stage.container().style.cursor = isSelected ? "move" : "pointer";
      }
    },
    onMouseLeave: (event: Konva.KonvaEventObject<MouseEvent>) => {
      const stage = event.target.getStage();
      if (stage) {
        stage.container().style.cursor = "default";
      }
    },
  };

  if (object.type === "text") {
    return (
      <Text
        {...common}
        text={object.text}
        fill={object.color}
        fontFamily={object.font}
        fontSize={Math.max(7, (object.fontSize / POINTS_PER_INCH) * scale)}
        lineHeight={1.12}
        padding={2}
        perfectDrawEnabled={false}
        listening
      />
    );
  }

  if (object.type === "image") {
    return <ImageObject object={object} common={common} />;
  }

  return <ShapeObject object={object} common={common} width={width} height={height} />;
}

function ImageObject({
  object,
  common,
}: {
  object: ImageSlideObject;
  common: Record<string, unknown>;
}) {
  const image = useLoadedImage(object.imageUrl);
  if (image) {
    return <KonvaImage {...common} image={image} perfectDrawEnabled={false} />;
  }

  return (
    <Group {...common}>
      <Rect
        x={0}
        y={0}
        width={Number(common.width)}
        height={Number(common.height)}
        fill="#e6e8ee"
        stroke="#9aa3b2"
        dash={[8, 6]}
        listening={false}
      />
      <Text
        x={12}
        y={12}
        width={Math.max(1, Number(common.width) - 24)}
        height={Math.max(1, Number(common.height) - 24)}
        text="Image"
        fill="#4b5563"
        fontSize={14}
        fontFamily="Inter"
        listening={false}
      />
    </Group>
  );
}

function ShapeObject({
  object,
  common,
  width,
  height,
}: {
  object: ShapeSlideObject;
  common: Record<string, unknown>;
  width: number;
  height: number;
}) {
  const stroke = object.lineColor || "rgba(35, 42, 58, 0.34)";
  const fill = object.fillColor || "#eef0f4";

  return (
    <Group {...common}>
      {object.geometryType === "ellipse" || object.geometryType === "arc" ? (
        <Ellipse
          x={width / 2}
          y={height / 2}
          radiusX={width / 2}
          radiusY={height / 2}
          fill={fill}
          stroke={stroke}
          strokeWidth={1}
          listening={false}
        />
      ) : (
        <Rect x={0} y={0} width={width} height={height} fill={fill} stroke={stroke} strokeWidth={1} listening={false} />
      )}
    </Group>
  );
}

function useLoadedImage(src?: string) {
  const [image, setImage] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!src) {
      setImage(null);
      return;
    }

    const nextImage = new window.Image();
    nextImage.crossOrigin = "anonymous";
    nextImage.onload = () => setImage(nextImage);
    nextImage.onerror = () => setImage(null);
    nextImage.src = assetUrl(src);

    return () => {
      nextImage.onload = null;
      nextImage.onerror = null;
    };
  }, [src]);

  return image;
}
