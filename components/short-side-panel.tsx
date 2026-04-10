import { HandlingIcons } from "./handling-icons";
import { VaseWithHandles } from "./product-drawing";

interface ShortSidePanelProps {
  itemNo: string;
  caseQty: string;
  poNo: string;
  cartonWeight: string;
  cube: string;
  showDimensions?: boolean;
  panelWidth?: string;
  panelHeight?: string;
  isLast?: boolean;
}

export function ShortSidePanel({
  itemNo,
  caseQty,
  poNo,
  cartonWeight,
  cube,
  showDimensions = false,
  panelWidth,
  panelHeight,
  isLast = false,
}: ShortSidePanelProps) {
  return (
    <div
      className={`relative flex flex-col h-full bg-white ${!isLast ? "border-r-[1.5px] border-foreground" : ""}`}
    >
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
        <HandlingIcons size="small" />
      </div>

      {/* Brand block - slightly smaller */}
      <div className="text-center pt-14 pb-2">
        <h2 className="font-serif text-base tracking-[2px] uppercase text-foreground">
          Sagebrook Home<sup className="text-[8px] font-normal">TM</sup>
        </h2>
        <p className="font-crimson italic text-xs text-foreground/80 mt-0.5 tracking-wide">
          Style That Makes a Statement
        </p>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col items-center justify-center text-center px-3">
        <p className="text-[15px] font-black text-foreground mb-1">
          ITEM NO.: {itemNo}
        </p>
        <p className="text-[13px] font-extrabold text-foreground mb-3">
          CASE QTY : {caseQty}
        </p>

        {/* Logistics info */}
        <div className="text-left text-[11px] leading-relaxed text-foreground/80 w-full pl-[20%] mb-3">
          <p className="font-semibold">P.O NO.: {poNo}</p>
          <p className="font-semibold">CARTON NO.: _____ OF _____</p>
          <p className="font-semibold">CARTON WEIGHT : {cartonWeight} (LBS)</p>
          <p className="font-semibold">CUBE : {cube} (CU FT)</p>
        </div>

        {/* Product line drawing */}
        <div className="w-16 h-16 mx-auto">
          <VaseWithHandles className="w-full h-full text-foreground" />
        </div>
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
