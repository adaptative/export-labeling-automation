export type Role =
  | 'Merchandiser'
  | 'Designer'
  | 'QA Reviewer'
  | 'Compliance Lead'
  | 'Admin'
  | 'Importer QA'
  | 'Printer';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  avatar?: string;
  status: 'active' | 'inactive';
  lastActive: string;
  ssoProvider?: string;
  mfaEnabled: boolean;
}

export interface Tenant {
  id: string;
  name: string;
  location?: string;
}

export type OrderState = 
  | 'CREATED'
  | 'INTAKE'
  | 'EXTRACTING'
  | 'FUSING'
  | 'HUMAN_BLOCKED'
  | 'VALIDATING_COMPLIANCE'
  | 'GENERATING_DRAWINGS'
  | 'COMPOSING'
  | 'VALIDATING_OUTPUT'
  | 'REVIEW'
  | 'DELIVERED'
  | 'FAILED';

export interface Order {
  id: string;
  poNumber: string;
  importerId: string;
  itemsCount: number;
  state: OrderState;
  progress: number;
  ownerId: string;
  createdAt: string;
  dueDate: string;
  automationRate: number;
}
