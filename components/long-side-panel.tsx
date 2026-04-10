import { HandlingIcons } from "./handling-icons";

interface LongSidePanelProps {
  itemNo: string;
  caseQty: string;
  description: string;
  dimensions: string;
  showDimensions?: boolean;
  panelWidth?: string;
  panelHeight?: string;
}

export function LongSidePanel({
  itemNo,
  caseQty,
  description,
  dimensions,
  showDimensions = false,
  panelWidth,
  panelHeight,
}: LongSidePanelProps) {
  return (
    <div className="relative flex flex-col h-full bg-white border-r-[1.5px] border-foreground">
      {/* Dimension annotations */}
      {showDimensions && panelWidth && (
        <span className="absolute top-8 left-1/2 -translate-x-1/2 text-[10px] font-bold text-blue-600">
          {panelWidth}
        </span>
      )}
      {showDimensions && panelHeight && (
        <span className="absolute left-1 top-1/2 -translate-y-1/2 -rotate-90 whitespace-nowrap text-[10px] font-bold text-blue-600">
          {panelHeight}
        </span>
      )}

      {/* Handling icons - top right */}
      <div className="absolute top-3 right-3">
        <HandlingIcons />
      </div>

      {/* Brand block */}
      <div className="text-center pt-14 pb-2">
        <h2 className="font-serif text-xl tracking-[3px] uppercase text-foreground">
          Sagebrook Home<sup className="text-[9px] font-normal">TM</sup>
        </h2>
        <p className="font-crimson italic text-sm text-foreground/80 mt-0.5 tracking-wide">
          Style That Makes a Statement
        </p>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
        <p className="text-lg font-black text-foreground mb-1">
          ITEM NO.: {itemNo}
        </p>
        <p className="text-base font-extrabold text-foreground mb-3">
          CASE QTY : {caseQty}
        </p>
        <p className="text-xs font-semibold text-foreground/80 mb-2 leading-relaxed max-w-[90%]">
          DESCRIPTION : {description}
        </p>
        <p className="text-[11px] font-semibold text-foreground/80">
          DIMENSIONS: {dimensions}
        </p>
      </div>

      {/* Origin footer */}
      <div className="text-center pb-4">
        <p className="text-sm font-extrabold uppercase tracking-wider text-foreground">
          Made in India
        </p>
      </div>
    </div>
  );
}
