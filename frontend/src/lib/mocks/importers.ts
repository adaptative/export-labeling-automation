export type ImporterStatus = 'active' | 'onboarding' | 'invited' | 'paused';

export interface Importer {
  id: string;
  name: string;
  countries: string[];
  onboardingProgress: number;
  ordersMTD: number;
  openHitl: number;
  status: ImporterStatus;
  buyerContact: string;
  buyerEmail: string;
  portalToken: string;
  since: string;
  labelLang: string[];
  units: 'metric' | 'imperial' | 'both';
  barcodePlacement: string;
  panelLayout: string;
  handlingSymbols: string[];
  requiredFields: string[];
  docRequirements: string[];
  notes: string;
}

export const importers: Importer[] = [
  {
    id: 'IMP-001',
    name: 'Sagebrook Home',
    countries: ['US', 'CA'],
    onboardingProgress: 100,
    ordersMTD: 45,
    openHitl: 2,
    status: 'active',
    buyerContact: 'Jennifer Walsh',
    buyerEmail: 'j.walsh@sagebrookhome.com',
    portalToken: 'tok_SBH001',
    since: '2023-04-15',
    labelLang: ['en'],
    units: 'imperial',
    barcodePlacement: 'Bottom Right',
    panelLayout: 'Standard 4-panel',
    handlingSymbols: ['Fragile', 'This Way Up', 'Keep Dry'],
    requiredFields: ['SKU', 'UPC', 'Country of Origin', 'Material Content', 'Care Instructions', 'Weight', 'Dimensions'],
    docRequirements: ['po', 'pi', 'label_protocol', 'logo', 'care_icons', 'warning_guidelines', 'warning_labels', 'brand_guide', 'msds', 'prop65', 'factory_cert', 'customs_code'],
    notes: 'Requires Prop 65 warning on all California-destined shipments. Font size min 8pt.',
  },
  {
    id: 'IMP-002',
    name: 'Pier 1',
    countries: ['US'],
    onboardingProgress: 80,
    ordersMTD: 12,
    openHitl: 5,
    status: 'onboarding',
    buyerContact: 'David Park',
    buyerEmail: 'd.park@pier1.com',
    portalToken: 'tok_P1002',
    since: '2024-01-22',
    labelLang: ['en'],
    units: 'imperial',
    barcodePlacement: 'Bottom Left',
    panelLayout: 'Standard 4-panel',
    handlingSymbols: ['Fragile', 'This Way Up'],
    requiredFields: ['SKU', 'UPC', 'Country of Origin', 'Care Instructions', 'Weight'],
    docRequirements: ['po', 'pi', 'label_protocol', 'logo', 'care_icons', 'warning_guidelines', 'warning_labels', 'factory_cert'],
    notes: 'Pending: buyer needs to approve warning label artwork and care icons in portal.',
  },
  {
    id: 'IMP-003',
    name: 'TJX Companies',
    countries: ['US', 'UK', 'AU'],
    onboardingProgress: 50,
    ordersMTD: 8,
    openHitl: 1,
    status: 'onboarding',
    buyerContact: 'Priya Mehta',
    buyerEmail: 'p.mehta@tjx.com',
    portalToken: 'tok_TJX003',
    since: '2024-09-10',
    labelLang: ['en', 'fr'],
    units: 'both',
    barcodePlacement: 'Top Right',
    panelLayout: 'Bilingual 6-panel',
    handlingSymbols: ['Fragile'],
    requiredFields: ['SKU', 'UPC', 'GTIN-14', 'Country of Origin', 'Material Content', 'Care Instructions', 'Weight', 'Dimensions', 'Retail Price'],
    docRequirements: ['po', 'pi', 'label_protocol', 'logo', 'care_icons', 'warning_guidelines', 'warning_labels', 'msds', 'factory_cert', 'customs_code'],
    notes: 'UK shipments require UKCA mark. AU requires bilingual (EN/FR is for CA stores). In progress — label spec sheet not yet confirmed.',
  },
  {
    id: 'IMP-004',
    name: 'Artisan Living',
    countries: ['US'],
    onboardingProgress: 10,
    ordersMTD: 0,
    openHitl: 0,
    status: 'invited',
    buyerContact: 'Marcus Green',
    buyerEmail: 'm.green@artisanliving.com',
    portalToken: 'tok_ART004',
    since: '2025-03-01',
    labelLang: ['en'],
    units: 'imperial',
    barcodePlacement: 'TBD',
    panelLayout: 'TBD',
    handlingSymbols: [],
    requiredFields: [],
    docRequirements: ['po', 'pi', 'label_protocol'],
    notes: 'New importer — invite sent. Awaiting buyer portal completion.',
  },
];
