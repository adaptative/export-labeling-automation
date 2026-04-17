export type OrderState =
  | 'CREATED' | 'INTAKE' | 'EXTRACTING' | 'FUSING'
  | 'HUMAN_BLOCKED' | 'VALIDATING_COMPLIANCE'
  | 'GENERATING_DRAWINGS' | 'COMPOSING' | 'VALIDATING_OUTPUT'
  | 'REVIEW' | 'DELIVERED' | 'FAILED';

export interface Order {
  id: string;
  poNumber: string;
  importerId: string;
  importerName: string;
  itemsCount: number;
  state: OrderState;
  progress: number;
  issues: number;
  ownerId: string;
  ownerName: string;
  createdAt: string;
  updatedAt: string;
  dueDate: string;
  automationRate: number;
  totalCartons: number;
  documents: { name: string; type: string; sizeMb: number }[];
  activityLog: { time: string; text: string; agent?: string }[];
}

export const orders: Order[] = [
  {
    id: 'PO-25364',
    poNumber: 'PO#25364',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    itemsCount: 8,
    state: 'COMPOSING',
    progress: 72,
    issues: 0,
    ownerId: 'U-001',
    ownerName: 'Priya Sharma',
    createdAt: '2026-04-10T06:30:00Z',
    updatedAt: '2026-04-11T08:12:00Z',
    dueDate: '2026-04-18T00:00:00Z',
    automationRate: 88,
    totalCartons: 2217,
    documents: [
      { name: 'PO_25364_Sagebrook.pdf', type: 'PO', sizeMb: 2.1 },
      { name: 'PI_25364_Nakoda.xlsx', type: 'PI', sizeMb: 0.038 },
      { name: 'Sagebrook_Protocol_v4.pdf', type: 'PROTOCOL', sizeMb: 1.4 },
      { name: 'Sagebrook_Warnings_2026.pdf', type: 'WARNING_LABELS', sizeMb: 0.86 },
    ],
    activityLog: [
      { time: '2 min ago', text: 'Composer Agent rendered 6/8 die-cuts', agent: 'composer' },
      { time: '4 min ago', text: 'Line Drawing Agent finished 8/8', agent: 'line_drawing' },
      { time: '6 min ago', text: 'Fusion Agent completed — 0 issues', agent: 'fusion' },
      { time: '9 min ago', text: 'Priya resolved 0 HiTL issues' },
      { time: '11 min ago', text: 'PO Parser extracted 8 items (conf: 0.97)', agent: 'po_parser' },
      { time: '12 min ago', text: 'Intake classified 4 docs', agent: 'intake' },
    ],
  },
  {
    id: 'PO-25362',
    poNumber: 'PO#25362',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    itemsCount: 3,
    state: 'HUMAN_BLOCKED',
    progress: 42,
    issues: 3,
    ownerId: 'U-001',
    ownerName: 'Priya Sharma',
    createdAt: '2026-04-09T10:00:00Z',
    updatedAt: '2026-04-11T07:58:00Z',
    dueDate: '2026-04-16T00:00:00Z',
    automationRate: 70,
    totalCartons: 1840,
    documents: [
      { name: 'PO_25362_Sagebrook.pdf', type: 'PO', sizeMb: 3.4 },
      { name: 'PI_25362_Nakoda.xlsx', type: 'PI', sizeMb: 0.042 },
    ],
    activityLog: [
      { time: '14 min ago', text: 'HiTL session started — 3 blocking issues', agent: 'hitl' },
      { time: '16 min ago', text: 'Fusion Agent raised 3 issues', agent: 'fusion' },
      { time: '18 min ago', text: 'PO Parser extracted 13 items (conf: 0.91)', agent: 'po_parser' },
      { time: '20 min ago', text: 'Intake classified 2 docs', agent: 'intake' },
    ],
  },
  {
    id: 'PO-25358',
    poNumber: 'PO#25358',
    importerId: 'IMP-002',
    importerName: 'Pier 1',
    itemsCount: 6,
    state: 'DELIVERED',
    progress: 100,
    issues: 0,
    ownerId: 'U-002',
    ownerName: 'Rajesh Kumar',
    createdAt: '2026-04-07T09:00:00Z',
    updatedAt: '2026-04-11T07:15:00Z',
    dueDate: '2026-04-14T00:00:00Z',
    automationRate: 95,
    totalCartons: 780,
    documents: [
      { name: 'PO_25358_Pier1.pdf', type: 'PO', sizeMb: 1.8 },
      { name: 'PI_25358_Nakoda.xlsx', type: 'PI', sizeMb: 0.035 },
      { name: 'Pier1_Protocol_v2.pdf', type: 'PROTOCOL', sizeMb: 0.9 },
    ],
    activityLog: [
      { time: '1 h ago', text: 'Delivered to printer — 6 SVGs sent', agent: 'delivery' },
      { time: '2 h ago', text: 'Client approved all 6 items' },
      { time: '3 h ago', text: 'Validator passed — all checks green', agent: 'validator' },
    ],
  },
  {
    id: 'PO-25357',
    poNumber: 'PO#25357',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    itemsCount: 22,
    state: 'VALIDATING_OUTPUT',
    progress: 90,
    issues: 0,
    ownerId: 'U-001',
    ownerName: 'Priya Sharma',
    createdAt: '2026-04-06T08:00:00Z',
    updatedAt: '2026-04-11T05:30:00Z',
    dueDate: '2026-04-15T00:00:00Z',
    automationRate: 82,
    totalCartons: 3100,
    documents: [
      { name: 'PO_25357_Sagebrook.pdf', type: 'PO', sizeMb: 5.2 },
      { name: 'PI_25357_Nakoda.xlsx', type: 'PI', sizeMb: 0.06 },
      { name: 'Sagebrook_Protocol_v4.pdf', type: 'PROTOCOL', sizeMb: 1.4 },
      { name: 'Sagebrook_Warnings_2026.pdf', type: 'WARNING_LABELS', sizeMb: 0.86 },
      { name: 'Sagebrook_QA_Checklist.pdf', type: 'CHECKLIST', sizeMb: 0.22 },
    ],
    activityLog: [
      { time: '3 h ago', text: 'Validator running — 18/22 items checked', agent: 'validator' },
      { time: '4 h ago', text: 'Composer completed 22/22 die-cuts', agent: 'composer' },
    ],
  },
  {
    id: 'PO-25351',
    poNumber: 'PO#25351',
    importerId: 'IMP-002',
    importerName: 'Pier 1',
    itemsCount: 4,
    state: 'HUMAN_BLOCKED',
    progress: 35,
    issues: 1,
    ownerId: 'U-002',
    ownerName: 'Rajesh Kumar',
    createdAt: '2026-04-05T11:00:00Z',
    updatedAt: '2026-04-10T14:00:00Z',
    dueDate: '2026-04-12T00:00:00Z',
    automationRate: 65,
    totalCartons: 420,
    documents: [
      { name: 'PO_25351_Pier1.pdf', type: 'PO', sizeMb: 1.1 },
      { name: 'PI_25351_Nakoda.xlsx', type: 'PI', sizeMb: 0.032 },
    ],
    activityLog: [
      { time: 'yesterday', text: 'HiTL: carton gross weight missing for 1 item', agent: 'hitl' },
      { time: 'yesterday', text: 'Fusion Agent raised 1 issue', agent: 'fusion' },
    ],
  },
  {
    id: 'PO-25344',
    poNumber: 'PO#25344',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    itemsCount: 11,
    state: 'DELIVERED',
    progress: 100,
    issues: 0,
    ownerId: 'U-001',
    ownerName: 'Priya Sharma',
    createdAt: '2026-04-01T08:00:00Z',
    updatedAt: '2026-04-09T12:00:00Z',
    dueDate: '2026-04-10T00:00:00Z',
    automationRate: 92,
    totalCartons: 1560,
    documents: [
      { name: 'PO_25344_Sagebrook.pdf', type: 'PO', sizeMb: 4.0 },
      { name: 'PI_25344_Nakoda.xlsx', type: 'PI', sizeMb: 0.05 },
      { name: 'Sagebrook_Protocol_v4.pdf', type: 'PROTOCOL', sizeMb: 1.4 },
    ],
    activityLog: [
      { time: '2 d ago', text: 'Delivered — 11 SVGs + 11 PDFs sent to printer', agent: 'delivery' },
    ],
  },
  {
    id: 'PO-25330',
    poNumber: 'PO#25330',
    importerId: 'IMP-003',
    importerName: 'TJX Companies',
    itemsCount: 9,
    state: 'EXTRACTING',
    progress: 15,
    issues: 0,
    ownerId: 'U-002',
    ownerName: 'Rajesh Kumar',
    createdAt: '2026-04-11T06:00:00Z',
    updatedAt: '2026-04-11T06:05:00Z',
    dueDate: '2026-04-22T00:00:00Z',
    automationRate: 0,
    totalCartons: 1200,
    documents: [
      { name: 'PO_25330_TJX.pdf', type: 'PO', sizeMb: 6.8 },
      { name: 'PI_25330_Nakoda.xlsx', type: 'PI', sizeMb: 0.07 },
    ],
    activityLog: [
      { time: 'just now', text: 'PO Parser running — page 3/12', agent: 'po_parser' },
      { time: '5 min ago', text: 'Intake classified 2 docs', agent: 'intake' },
    ],
  },
  {
    id: 'PO-25320',
    poNumber: 'PO#25320',
    importerId: 'IMP-001',
    importerName: 'Sagebrook Home',
    itemsCount: 15,
    state: 'REVIEW',
    progress: 95,
    issues: 0,
    ownerId: 'U-001',
    ownerName: 'Priya Sharma',
    createdAt: '2026-03-28T08:00:00Z',
    updatedAt: '2026-04-10T16:00:00Z',
    dueDate: '2026-04-12T00:00:00Z',
    automationRate: 90,
    totalCartons: 2100,
    documents: [
      { name: 'PO_25320_Sagebrook.pdf', type: 'PO', sizeMb: 4.5 },
      { name: 'PI_25320_Nakoda.xlsx', type: 'PI', sizeMb: 0.055 },
      { name: 'Sagebrook_Protocol_v4.pdf', type: 'PROTOCOL', sizeMb: 1.4 },
      { name: 'Sagebrook_Warnings_2026.pdf', type: 'WARNING_LABELS', sizeMb: 0.86 },
    ],
    activityLog: [
      { time: 'yesterday', text: 'All 15 items validated — awaiting human review', agent: 'validator' },
    ],
  },
];
