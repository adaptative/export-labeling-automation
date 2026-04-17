export interface ComplianceRule {
  id: string;
  version: string;
  name: string;
  importerId: string;
  importerName: string;
  labelId: string;
  effectiveFrom: string;
  effectiveTo: string | null;
  supersedes: string | null;
  ordersEvaluated: number;
  triggerDsl: string;
  triggerSummary: string;
  placement: string;
  status: 'active' | 'proposed' | 'deprecated';
}

export const rules: ComplianceRule[] = [
  {
    id: 'R-0001',
    version: 'v3',
    name: 'Prop 65 Product — California',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-001',
    effectiveFrom: '2024-01-01',
    effectiveTo: null,
    supersedes: 'v2',
    ordersEvaluated: 12450,
    triggerDsl: `if item.destination == "CA" and item.material in ["ceramic", "painted", "metal"]:
    return WarningLabel("PROP-65-PRODUCT")`,
    triggerSummary: 'destination = CA && material ∈ [ceramic, painted, metal]',
    placement: 'Carton — long panel',
    status: 'active',
  },
  {
    id: 'R-0002',
    version: 'v4',
    name: 'Prop 65 Furniture — California',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-002',
    effectiveFrom: '2024-01-01',
    effectiveTo: null,
    supersedes: 'v3',
    ordersEvaluated: 8200,
    triggerDsl: `if item.destination == "CA" and item.category == "furniture":
    return WarningLabel("PROP-65-FURNITURE")`,
    triggerSummary: 'destination = CA && category = furniture',
    placement: 'Carton — long panel',
    status: 'active',
  },
  {
    id: 'R-0003',
    version: 'v2',
    name: 'FDA Non-Food — Ceramic variant',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-003',
    effectiveFrom: '2024-03-15',
    effectiveTo: null,
    supersedes: 'v1',
    ordersEvaluated: 5100,
    triggerDsl: `if item.category in ["bowl", "plate", "mug"] and item.material == "ceramic" and not item.food_contact:
    return WarningLabel("FDA-NONFOOD-CERAMIC")`,
    triggerSummary: 'category ∈ [bowl, plate, mug] && material = ceramic && food_contact = false',
    placement: 'Carton + Product sticker',
    status: 'active',
  },
  {
    id: 'R-0004',
    version: 'v1',
    name: 'FDA Non-Food — Non-ceramic',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-004',
    effectiveFrom: '2024-06-01',
    effectiveTo: null,
    supersedes: null,
    ordersEvaluated: 3400,
    triggerDsl: `if item.category in ["bowl", "plate"] and item.material != "ceramic" and not item.food_contact:
    return WarningLabel("FDA-NONFOOD-NONCERAMIC")`,
    triggerSummary: 'category ∈ [bowl, plate] && material ≠ ceramic && food_contact = false',
    placement: 'Product sticker',
    status: 'active',
  },
  {
    id: 'R-0005',
    version: 'v2',
    name: 'TSCA Title VI — Wood products',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-005',
    effectiveFrom: '2023-06-01',
    effectiveTo: null,
    supersedes: 'v1',
    ordersEvaluated: 15000,
    triggerDsl: `if item.material in ["MDF", "plywood", "particle_board", "reclaimed_wood"] and item.destination == "USA":
    return WarningLabel("TSCA-TITLE-VI")`,
    triggerSummary: 'material ∈ [MDF, plywood, reclaimed_wood] && destination = USA',
    placement: 'Carton — short panel',
    status: 'active',
  },
  {
    id: 'R-0006',
    version: 'v1',
    name: 'Team Lift — Heavy cartons',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-006',
    effectiveFrom: '2023-06-01',
    effectiveTo: null,
    supersedes: null,
    ordersEvaluated: 45000,
    triggerDsl: `if item.gross_weight_lbs > 28:
    return WarningLabel("TEAM-LIFT")`,
    triggerSummary: 'gross_weight_lbs > 28',
    placement: 'Carton — all 4 sides',
    status: 'active',
  },
  {
    id: 'R-0007',
    version: 'v1',
    name: 'Heavy Object — Very heavy cartons',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-007',
    effectiveFrom: '2023-06-01',
    effectiveTo: null,
    supersedes: null,
    ordersEvaluated: 45000,
    triggerDsl: `if item.gross_weight_lbs > 50:
    return WarningLabel("HEAVY-OBJECT")`,
    triggerSummary: 'gross_weight_lbs > 50',
    placement: 'Carton — all 4 sides',
    status: 'active',
  },
  {
    id: 'R-0008',
    version: 'v1',
    name: 'Fragile — Breakable materials',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-012',
    effectiveFrom: '2023-06-01',
    effectiveTo: null,
    supersedes: null,
    ordersEvaluated: 32000,
    triggerDsl: `if item.material in ["ceramic", "glass", "porcelain", "stone"]:
    return WarningLabel("FRAGILE")`,
    triggerSummary: 'material ∈ [ceramic, glass, porcelain, stone]',
    placement: 'Carton — all 4 sides',
    status: 'active',
  },
  {
    id: 'R-0009',
    version: 'v1',
    name: 'Ceramic-coated = Non-ceramic for FDA',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    labelId: 'WL-004',
    effectiveFrom: '2026-04-11',
    effectiveTo: null,
    supersedes: null,
    ordersEvaluated: 0,
    triggerDsl: `if item.material == "paper_mache" and "ceramic" in item.finish.lower():
    classify_as("non-ceramic for FDA")
    return WarningLabel("FDA-NONFOOD-NONCERAMIC")`,
    triggerSummary: 'material = paper_mache && finish contains "ceramic"',
    placement: 'Product sticker',
    status: 'proposed',
  },
];
