import { CartonDieCutLayout } from "@/components/carton-diecut-layout";

const cartonData = {
  itemNo: "18236-01",
  boxSize: "30.5 X 15.5 X 16 INCH",
  caseQty: "2 PCS",
  description: "PAPER MACHE, 14\" VASE WITH HANDLES, WHITE",
  dimensions: "30.5\"L x 15.5\"W x 16\"H",
  poNo: "24966",
  cartonWeight: "15",
  cube: "4.38",
};

export default function CartonPrintPage() {
  return (
    <main className="min-h-screen bg-background py-8 px-5">
      {/* Page Header */}
      <header className="max-w-6xl mx-auto text-center mb-6">
        <h1 className="text-xl font-black text-foreground">
          V3 — Carton Box Print Layout (Die-Cut)
        </h1>
        <p className="text-xs text-muted-foreground mt-1">
          Generated from PO24966 data for Item 18236-01 — Box Size: 30.5 x 15.5 x 16 Inch
        </p>
        <span className="inline-block mt-2 text-[10px] font-bold uppercase tracking-wide px-3 py-1 rounded-full bg-blue-50 text-blue-700">
          V3 — Matches Real Printer Sheet Format
        </span>
      </header>

      {/* Info Notes */}
      <section className="max-w-6xl mx-auto mb-6 space-y-3">
        <div className="text-xs text-foreground/70 leading-relaxed bg-red-50 border-l-4 border-red-500 px-4 py-3 rounded-r">
          <strong className="text-red-700">Key Insight:</strong> This is a{" "}
          <strong>flattened carton box die-cut</strong> — the entire surface of
          all 4 box sides is printed directly onto corrugated carton material.
          Each page represents one SKU&apos;s complete box with 4 panels (2 long
          sides + 2 short sides) plus top/bottom flaps.
        </div>
        <div className="text-xs text-foreground/70 leading-relaxed bg-amber-50 border-l-4 border-amber-500 px-4 py-3 rounded-r">
          <strong className="text-amber-700">Panel Structure:</strong>{" "}
          <strong>LONG SIDES</strong> (panels 1 & 3) = Brand + Item No + Case
          Qty + Description + Dimensions + Origin.{" "}
          <strong>SHORT SIDES</strong> (panels 2 & 4) = Brand + Item No + Case
          Qty + PO No + Carton No + Weight + Cube + Product Drawing + Origin.
          All panels have standardized handling symbols at top-right.
        </div>
      </section>

      {/* Die-Cut Layout */}
      <CartonDieCutLayout data={cartonData} showDimensions />

      {/* Legend / Comparison Section */}
      <section className="max-w-6xl mx-auto mt-10 bg-white border-2 border-border rounded-lg p-6 shadow-sm">
        <h3 className="text-sm font-extrabold text-foreground mb-4">
          Panel Type Reference
        </h3>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="border border-border rounded p-4">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Long Side Panels (1 & 3)
            </h4>
            <ul className="text-xs text-foreground/80 space-y-1 list-disc list-inside">
              <li>Brand name with trademark and tagline</li>
              <li>Item Number</li>
              <li>Case Quantity</li>
              <li>Product Description</li>
              <li>Box Dimensions</li>
              <li>Country of Origin</li>
              <li>Handling symbols (top-right corner)</li>
            </ul>
          </div>
          <div className="border border-border rounded p-4">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Short Side Panels (2 & 4)
            </h4>
            <ul className="text-xs text-foreground/80 space-y-1 list-disc list-inside">
              <li>Brand name with trademark and tagline</li>
              <li>Item Number</li>
              <li>Case Quantity</li>
              <li>PO Number</li>
              <li>Carton Number (fill-in blanks)</li>
              <li>Carton Weight</li>
              <li>Cubic Feet</li>
              <li>Product Line Drawing</li>
              <li>Country of Origin</li>
              <li>Handling symbols (top-right corner)</li>
            </ul>
          </div>
        </div>

        {/* No Barcodes Note */}
        <div className="mt-4 text-xs text-muted-foreground bg-neutral-50 p-3 rounded border border-border">
          <strong>Note:</strong> No barcodes on carton print — UPC and ITF-14 barcodes are applied as separate stickers after printing.
        </div>
      </section>
    </main>
  );
}
