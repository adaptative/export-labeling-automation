export interface HitlMessage {
  role: 'system' | 'agent' | 'human';
  content: string;
  attachments?: string[];
  options?: string[];
  timestamp: string;
}

export interface HitlThread {
  id: string;
  orderId: string;
  poNumber: string;
  importerName: string;
  itemNo: string;
  summary: string;
  status: 'resolved' | 'active' | 'waiting';
  blocking: string;
  priority: 'high' | 'medium' | 'low';
  createdAt: string;
  messages: HitlMessage[];
}

export const hitlThreads: HitlThread[] = [
  {
    id: 'HITL-001',
    orderId: 'PO-25362',
    poNumber: 'PO#25362',
    importerName: 'Sagebrook Home',
    itemNo: '22104-03',
    summary: 'UPC missing digit — only 11 digits in PO',
    status: 'resolved',
    blocking: 'Fusion Agent',
    priority: 'high',
    createdAt: '2026-04-11T07:40:00Z',
    messages: [
      { role: 'system', content: 'Session started — Agent: Nakoda-HiTL · Model: Claude Sonnet 4.6', timestamp: '2026-04-11T07:40:00Z' },
      {
        role: 'agent',
        content: 'Hi Priya — I need your help on **item 22104-03** (18" Ceramic Vase, White). The PO lists the UPC but it\'s only 11 digits: `67747867432`. UPC-A requires exactly 12 digits including the check digit.\n\nI can compute a valid check digit → `677478674328`. Can you confirm?',
        attachments: ['PO_25362_Sagebrook.pdf — page 4'],
        timestamp: '2026-04-11T07:40:05Z',
      },
      { role: 'human', content: 'Let me check... yes, 677478674328 is correct.', timestamp: '2026-04-11T07:41:30Z' },
      { role: 'agent', content: 'Thanks — that matches the standard check digit. ✅ **Resolved:** item 22104-03 UPC set to `677478674328`. Fusion Agent unblocked.', timestamp: '2026-04-11T07:41:35Z' },
      { role: 'system', content: 'Issue resolved. Pipeline resumed for item 22104-03.', timestamp: '2026-04-11T07:41:36Z' },
    ],
  },
  {
    id: 'HITL-002',
    orderId: 'PO-25362',
    poNumber: 'PO#25362',
    importerName: 'Sagebrook Home',
    itemNo: '22200-01',
    summary: 'FDA classification unclear — ceramic-coated paper mache bowl',
    status: 'active',
    blocking: 'Compliance Rules Engine',
    priority: 'high',
    createdAt: '2026-04-11T07:42:00Z',
    messages: [
      { role: 'system', content: 'Session started — Agent: Nakoda-HiTL · Model: Claude Sonnet 4.6', timestamp: '2026-04-11T07:42:00Z' },
      {
        role: 'agent',
        content: 'Next issue — **item 22200-01** (12" Coated Bowl, Taupe). The PO describes it as a "stoneware serving bowl" but the PI says the material is paper mache with a ceramic coating.\n\nSagebrook\'s warning rules require the **FDA Non-Food** label for bowls unless the protocol explicitly allows food contact. I couldn\'t find a glaze-safety note in the protocol.\n\nIs this item intended for food contact?',
        attachments: ['PO_25362_Sagebrook.pdf — page 6', 'Sagebrook_Protocol_v4.pdf — page 12'],
        timestamp: '2026-04-11T07:42:05Z',
      },
      { role: 'human', content: 'Not food-contact — it\'s purely decorative. They sell it with dried botanicals inside.', timestamp: '2026-04-11T07:43:20Z' },
      {
        role: 'agent',
        content: 'Got it. I\'ll apply the **FDA Non-Food (Non-ceramic)** label since the base material is paper mache, not solid ceramic:\n\n> "For Decoration Only. Not Intended for Food Use."\n\nThis is the 3rd decorative-use bowl this month for Sagebrook — would you like me to propose a **profile rule** so I auto-classify ceramic-coated paper mache items as non-food in the future?',
        options: ['Yes, propose rule', 'Just this once'],
        timestamp: '2026-04-11T07:43:25Z',
      },
    ],
  },
  {
    id: 'HITL-003',
    orderId: 'PO-25362',
    poNumber: 'PO#25362',
    importerName: 'Sagebrook Home',
    itemNo: '22300-02',
    summary: 'Carton gross weight not in PI — Team Lift determination blocked',
    status: 'waiting',
    blocking: 'Compliance Rules Engine',
    priority: 'medium',
    createdAt: '2026-04-11T07:45:00Z',
    messages: [
      { role: 'system', content: 'Session started — Agent: Nakoda-HiTL · Model: Claude Sonnet 4.6', timestamp: '2026-04-11T07:45:00Z' },
      {
        role: 'agent',
        content: 'Hi Priya — **item 22300-02** (S/3 Wood Riser, Brown) has a blank carton gross weight in the PI. I need it to determine if the **Team Lift** label applies (required if > 28 lbs).\n\nThe carton is 28×18×20" with 12 pcs. Similar reclaimed wood risers in past orders averaged ~32 lbs per carton. Do you have the actual weight, or should I use the 32 lb estimate?',
        options: ['Use 32 lb estimate', 'I\'ll check with the factory'],
        timestamp: '2026-04-11T07:45:05Z',
      },
    ],
  },
  {
    id: 'HITL-004',
    orderId: 'PO-25351',
    poNumber: 'PO#25351',
    importerName: 'Pier 1',
    itemNo: '23100-01',
    summary: 'Carton gross weight blank — cannot determine Team Lift',
    status: 'waiting',
    blocking: 'Compliance Rules Engine',
    priority: 'medium',
    createdAt: '2026-04-10T14:00:00Z',
    messages: [
      { role: 'system', content: 'Session started — Agent: Nakoda-HiTL · Model: Claude Sonnet 4.6', timestamp: '2026-04-10T14:00:00Z' },
      {
        role: 'agent',
        content: 'Hi Rajesh — reviewing PO#25351 from Pier 1. **Item 23100-01** (S/3 Wooden Trays) has a blank carton weight in the PI.\n\nBox size: 22×16×14" with 3 pcs per carton. Similar wood trays in your history average ~25 lbs per carton. Do you have the actual weight?',
        timestamp: '2026-04-10T14:00:05Z',
      },
    ],
  },
];
