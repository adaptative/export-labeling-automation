import { LongSidePanel } from "./long-side-panel";
import { ShortSidePanel } from "./short-side-panel";

interface CartonData {
  itemNo: string;
  boxSize: string;
  caseQty: string;
  description: string;
  dimensions: string;
  poNo: string;
  cartonWeight: string;
  cube: string;
}

interface CartonDieCutLayoutProps {
  data: CartonData;
  showDimensions?: boolean;
}

export function CartonDieCutLayout({ data, showDimensions = true }: CartonDieCutLayoutProps) {
  return (
    <div className="w-full max-w-6xl mx-auto">
      {/* Box title header */}
      <h2 className="text-2xl font-black text-red-600 text-center tracking-wider mb-3">
        {data.itemNo} : {data.boxSize}
      </h2>

      {/* Die-cut container */}
      <div className="bg-white border-2 border-foreground shadow-xl overflow-hidden">
        {/* Top flaps */}
        <div className="flex border-b-[1.5px] border-foreground h-16">
          <div className="w-[28.5%] bg-neutral-50 border-r-[1.5px] border-foreground" />
          <div className="w-[21.5%] bg-neutral-50 border-r-[1.5px] border-foreground" />
          <div className="w-[28.5%] bg-neutral-50 border-r-[1.5px] border-foreground" />
          <div className="w-[21.5%] bg-neutral-50" />
        </div>

        {/* Main 4 panels */}
        <div className="flex min-h-[380px]">
          {/* Panel 1: Long Side */}
          <div className="w-[28.5%]">
            <LongSidePanel
              itemNo={data.itemNo}
              caseQty={data.caseQty}
              description={data.description}
              dimensions={data.dimensions}
              showDimensions={showDimensions}
              panelWidth="12.1 inch"
              panelHeight="9 inch"
            />
          </div>

          {/* Panel 2: Short Side */}
          <div className="w-[21.5%]">
            <ShortSidePanel
              itemNo={data.itemNo}
              caseQty={data.caseQty}
              poNo={data.poNo}
              cartonWeight={data.cartonWeight}
              cube={data.cube}
              showDimensions={showDimensions}
              panelWidth="10.9 inch"
              panelHeight="9 inch"
            />
          </div>

          {/* Panel 3: Long Side (repeat) */}
          <div className="w-[28.5%]">
            <LongSidePanel
              itemNo={data.itemNo}
              caseQty={data.caseQty}
              description={data.description}
              dimensions={data.dimensions}
            />
          </div>

          {/* Panel 4: Short Side (repeat) */}
          <div className="w-[21.5%]">
            <ShortSidePanel
              itemNo={data.itemNo}
              caseQty={data.caseQty}
              poNo={data.poNo}
              cartonWeight={data.cartonWeight}
              cube={data.cube}
              isLast
            />
          </div>
        </div>

        {/* Bottom flaps */}
        <div className="flex border-t-[1.5px] border-foreground h-16">
          <div className="w-[28.5%] bg-neutral-50 border-r-[1.5px] border-foreground" />
          <div className="w-[21.5%] bg-neutral-50 border-r-[1.5px] border-foreground" />
          <div className="w-[28.5%] bg-neutral-50 border-r-[1.5px] border-foreground" />
          <div className="w-[21.5%] bg-neutral-50" />
        </div>
      </div>
    </div>
  );
}
