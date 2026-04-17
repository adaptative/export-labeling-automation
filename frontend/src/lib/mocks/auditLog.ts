export interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  actorType: 'user' | 'agent' | 'system';
  action: string;
  resourceType: string;
  resourceId: string;
  detail: string;
}

export const auditLog: AuditEntry[] = [
  { id: 'AL-001', timestamp: '2026-04-11T08:12:00Z', actor: 'Composer Agent', actorType: 'agent', action: 'GENERATE', resourceType: 'Die-cut SVG', resourceId: 'ITM-25364-6', detail: 'Rendered die-cut for 12X12" Paper Mache Knobby Footed Bowl' },
  { id: 'AL-002', timestamp: '2026-04-11T08:10:00Z', actor: 'Composer Agent', actorType: 'agent', action: 'GENERATE', resourceType: 'Die-cut SVG', resourceId: 'ITM-25364-7', detail: 'Rendered die-cut for 12X12" Paper Mache Knobby Footed Bowl, Taupe' },
  { id: 'AL-003', timestamp: '2026-04-11T08:08:00Z', actor: 'Line Drawing Agent', actorType: 'agent', action: 'GENERATE', resourceType: 'Line Drawing', resourceId: 'ITM-25364-4', detail: 'SD lineart fallback used — potrace failed on complex wood grain' },
  { id: 'AL-004', timestamp: '2026-04-11T07:58:00Z', actor: 'Fusion Agent', actorType: 'agent', action: 'RAISE_ISSUE', resourceType: 'HiTL Thread', resourceId: 'HITL-002', detail: 'FDA classification ambiguous for ceramic-coated paper mache bowl' },
  { id: 'AL-005', timestamp: '2026-04-11T07:41:36Z', actor: 'Priya Sharma', actorType: 'user', action: 'RESOLVE', resourceType: 'HiTL Thread', resourceId: 'HITL-001', detail: 'Confirmed UPC 677478674328 for item 22104-03' },
  { id: 'AL-006', timestamp: '2026-04-11T07:40:00Z', actor: 'Fusion Agent', actorType: 'agent', action: 'RAISE_ISSUE', resourceType: 'HiTL Thread', resourceId: 'HITL-001', detail: 'UPC only 11 digits for item 22104-03' },
  { id: 'AL-007', timestamp: '2026-04-11T06:05:00Z', actor: 'Intake Agent', actorType: 'agent', action: 'CLASSIFY', resourceType: 'Document', resourceId: 'PO-25330', detail: 'Classified 2 documents: PO (conf: 0.99), PI (conf: 0.97)' },
  { id: 'AL-008', timestamp: '2026-04-11T06:00:00Z', actor: 'Rajesh Kumar', actorType: 'user', action: 'CREATE', resourceType: 'Order', resourceId: 'PO-25330', detail: 'Uploaded PO_25330_TJX.pdf + PI_25330_Nakoda.xlsx' },
  { id: 'AL-009', timestamp: '2026-04-10T16:00:00Z', actor: 'Validator Agent', actorType: 'agent', action: 'VALIDATE', resourceType: 'Order', resourceId: 'PO-25320', detail: 'All 15 items passed validation — awaiting human review' },
  { id: 'AL-010', timestamp: '2026-04-10T14:00:00Z', actor: 'Fusion Agent', actorType: 'agent', action: 'RAISE_ISSUE', resourceType: 'HiTL Thread', resourceId: 'HITL-004', detail: 'Carton weight blank for item 23100-01 in PO#25351' },
  { id: 'AL-011', timestamp: '2026-04-09T12:00:00Z', actor: 'Delivery Agent', actorType: 'agent', action: 'DELIVER', resourceType: 'Order', resourceId: 'PO-25344', detail: 'Sent 11 die-cut SVGs + 11 approval PDFs to printer' },
  { id: 'AL-012', timestamp: '2026-04-09T10:00:00Z', actor: 'Priya Sharma', actorType: 'user', action: 'CREATE', resourceType: 'Order', resourceId: 'PO-25362', detail: 'Uploaded PO_25362_Sagebrook.pdf + PI_25362_Nakoda.xlsx' },
  { id: 'AL-013', timestamp: '2026-04-07T09:00:00Z', actor: 'Rajesh Kumar', actorType: 'user', action: 'CREATE', resourceType: 'Order', resourceId: 'PO-25358', detail: 'Uploaded PO_25358_Pier1.pdf + PI_25358_Nakoda.xlsx' },
  { id: 'AL-014', timestamp: '2026-04-07T07:15:00Z', actor: 'Rajesh Kumar', actorType: 'user', action: 'APPROVE', resourceType: 'Order', resourceId: 'PO-25358', detail: 'Approved all 6 items — sent to client for review' },
  { id: 'AL-015', timestamp: '2026-04-06T08:00:00Z', actor: 'Priya Sharma', actorType: 'user', action: 'CREATE', resourceType: 'Order', resourceId: 'PO-25357', detail: 'Uploaded PO_25357_Sagebrook.pdf + PI_25357_Nakoda.xlsx' },
  { id: 'AL-016', timestamp: '2026-04-01T08:00:00Z', actor: 'Priya Sharma', actorType: 'user', action: 'CREATE', resourceType: 'Order', resourceId: 'PO-25344', detail: 'Uploaded PO_25344_Sagebrook.pdf + PI_25344_Nakoda.xlsx' },
  { id: 'AL-017', timestamp: '2026-03-28T08:00:00Z', actor: 'Priya Sharma', actorType: 'user', action: 'CREATE', resourceType: 'Order', resourceId: 'PO-25320', detail: 'Uploaded PO_25320_Sagebrook.pdf + PI_25320_Nakoda.xlsx' },
  { id: 'AL-018', timestamp: '2026-04-11T07:43:25Z', actor: 'HiTL Agent', actorType: 'agent', action: 'PROPOSE_RULE', resourceType: 'Compliance Rule', resourceId: 'R-0009', detail: 'Proposed rule: ceramic-coated paper mache → non-ceramic for FDA' },
  { id: 'AL-019', timestamp: '2026-04-10T10:30:00Z', actor: 'Rajesh Kumar', actorType: 'user', action: 'UPDATE', resourceType: 'Importer Profile', resourceId: 'IMP-002', detail: 'Updated Pier 1 panel layout — added short panel barcode slot' },
  { id: 'AL-020', timestamp: '2026-04-08T14:00:00Z', actor: 'Protocol Analyzer', actorType: 'agent', action: 'EXTRACT', resourceType: 'Importer Profile', resourceId: 'IMP-001', detail: 'Re-extracted Sagebrook protocol v4 — 3 new warning label rules detected' },
];
