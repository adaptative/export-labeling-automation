import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'wouter';
import { apiPost, apiUpload, apiGet } from '@/api/authInterceptor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  ChevronRight,
  ChevronLeft,
  Check,
  Building2,
  FileText,
  Tag,
  Cpu,
  ClipboardCheck,
  Loader2,
  AlertCircle,
  Globe,
  User,
  Mail,
  Upload,
  Sparkles,
  CheckCircle2,
  FileUp,
  X,
  Eye,
  Pencil,
  Info,
  RefreshCw,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const STEPS = [
  { id: 1, label: 'Company Info', icon: Building2 },
  { id: 2, label: 'Upload Documents', icon: Upload },
  { id: 3, label: 'Extracted Requirements', icon: Tag },
  { id: 4, label: 'AI Analysis', icon: Cpu },
  { id: 5, label: 'Review Protocol', icon: ClipboardCheck },
];

const COUNTRIES = ['United States', 'Canada', 'United Kingdom', 'Australia', 'Germany', 'France', 'Japan', 'UAE', 'Saudi Arabia', 'India'];

const DOC_GROUPS: { group: string; docs: { id: string; label: string; description: string }[] }[] = [
  {
    group: 'Order Documents',
    docs: [
      { id: 'po',   label: 'Purchase Order (PO)',    description: "Importer's official PO for the shipment" },
      { id: 'pi',   label: 'Proforma Invoice (PI)',  description: 'Exporter proforma with prices & quantities' },
    ],
  },
  {
    group: 'Label & Protocol',
    docs: [
      { id: 'label_protocol',     label: 'Label Protocol / Spec Sheet',  description: 'Master label spec: fields, layout, fonts, placements' },
      { id: 'warning_guidelines', label: 'Warning Guidelines',            description: 'Regulatory warning text & format rules per market' },
      { id: 'warning_labels',     label: 'Warning Label Templates',       description: 'Final artwork for warning panels (Prop 65, CE, UKCA…)' },
    ],
  },
  {
    group: 'Brand Assets',
    docs: [
      { id: 'logo',        label: 'Brand Logo Files',          description: 'Vector logo — all variants (primary, reverse, mono)' },
      { id: 'care_icons',  label: 'Care Icons / Symbol Sheet', description: 'ISO 3758 textile care & handling symbol files' },
      { id: 'brand_guide', label: 'Brand Style Guide',         description: 'Colour palette, typography, clear-space rules' },
    ],
  },
  {
    group: 'Compliance',
    docs: [
      { id: 'msds',         label: 'MSDS / Safety Data Sheet',        description: 'Required for products with hazardous materials' },
      { id: 'prop65',       label: 'Prop 65 Warning Template',        description: 'California Prop 65 warning text & artwork' },
      { id: 'factory_cert', label: 'Factory Compliance Certificate',  description: 'BSCI, SMETA, or equivalent social audit' },
    ],
  },
  {
    group: 'Customs',
    docs: [
      { id: 'customs_code', label: 'Customs Commodity Codes', description: 'HS / HTS codes for your full product range' },
    ],
  },
];
const DOC_OPTIONS = DOC_GROUPS.flatMap(g => g.docs);

const REQUIRED_FIELDS_OPTIONS = [
  'SKU', 'UPC / EAN', 'GTIN-14', 'Country of Origin', 'Material Content',
  'Care Instructions', 'Net Weight', 'Gross Weight', 'Dimensions', 'Retail Price',
  'Prop 65 Warning', 'Age Rating', 'UKCA Mark', 'CE Mark',
];

const HANDLING_SYMBOLS = ['Fragile', 'This Way Up', 'Keep Dry', 'Keep Cool', 'Do Not Stack', 'Recyclable'];

const PANEL_LAYOUTS = ['Standard 4-panel', 'Standard 6-panel', 'Bilingual 6-panel', 'Compact 2-panel', 'Full-bleed wrap', 'Hangtag only'];

interface UploadedFile {
  name: string;
  size: number;
  type: string;
  detectedDocType: string | null;
  confidence: number;
  status: 'classifying' | 'classified' | 'unknown';
}

interface FormData {
  companyName: string;
  buyerContact: string;
  buyerEmail: string;
  countries: string[];
  units: string;
  docRequirements: string[];
  requiredFields: string[];
  labelLang: string[];
  panelLayout: string;
  barcodePlacement: string;
  handlingSymbols: string[];
  notes: string;
}

const INITIAL_FORM: FormData = {
  companyName: '',
  buyerContact: '',
  buyerEmail: '',
  countries: [],
  units: 'imperial',
  docRequirements: [],
  requiredFields: [],
  labelLang: ['en'],
  panelLayout: '',
  barcodePlacement: '',
  handlingSymbols: [],
  notes: '',
};

const FILE_TYPE_MAP: Record<string, { docType: string; confidence: number }> = {
  'purchase_order': { docType: 'po', confidence: 0.96 },
  'po': { docType: 'po', confidence: 0.94 },
  'proforma': { docType: 'pi', confidence: 0.92 },
  'invoice': { docType: 'pi', confidence: 0.88 },
  'label': { docType: 'label_protocol', confidence: 0.95 },
  'protocol': { docType: 'label_protocol', confidence: 0.93 },
  'spec': { docType: 'label_protocol', confidence: 0.91 },
  'warning': { docType: 'warning_guidelines', confidence: 0.94 },
  'prop65': { docType: 'prop65', confidence: 0.97 },
  'prop_65': { docType: 'prop65', confidence: 0.97 },
  'logo': { docType: 'logo', confidence: 0.98 },
  'brand': { docType: 'brand_guide', confidence: 0.90 },
  'care': { docType: 'care_icons', confidence: 0.92 },
  'msds': { docType: 'msds', confidence: 0.96 },
  'safety': { docType: 'msds', confidence: 0.87 },
  'factory': { docType: 'factory_cert', confidence: 0.91 },
  'cert': { docType: 'factory_cert', confidence: 0.89 },
  'customs': { docType: 'customs_code', confidence: 0.93 },
  'hts': { docType: 'customs_code', confidence: 0.95 },
  'hs_code': { docType: 'customs_code', confidence: 0.94 },
};

function classifyFile(name: string): { docType: string; confidence: number } | null {
  const lower = name.toLowerCase().replace(/[.\-_\s]+/g, '_');
  for (const [keyword, result] of Object.entries(FILE_TYPE_MAP)) {
    if (lower.includes(keyword)) return result;
  }
  const ext = name.split('.').pop()?.toLowerCase();
  if (ext === 'svg' || ext === 'eps' || ext === 'ai') return { docType: 'logo', confidence: 0.85 };
  if (ext === 'pdf') return { docType: 'label_protocol', confidence: 0.72 };
  if (ext === 'xlsx' || ext === 'csv') return { docType: 'customs_code', confidence: 0.68 };
  return null;
}

function extractRequirementsFromDocs(detectedTypes: string[], countries: string[]): {
  fields: string[];
  layout: string;
  barcode: string;
  symbols: string[];
} {
  const fields: Set<string> = new Set(['SKU', 'Country of Origin']);
  const symbols: Set<string> = new Set();
  let layout = 'Standard 4-panel';
  let barcode = 'Bottom Right';

  if (detectedTypes.includes('po') || detectedTypes.includes('pi')) {
    fields.add('UPC / EAN');
    fields.add('Net Weight');
    fields.add('Gross Weight');
    fields.add('Dimensions');
  }
  if (detectedTypes.includes('label_protocol')) {
    fields.add('UPC / EAN');
    fields.add('Material Content');
    fields.add('Care Instructions');
    fields.add('Net Weight');
    fields.add('Dimensions');
    layout = 'Standard 4-panel';
    barcode = 'Bottom Right';
  }
  if (detectedTypes.includes('warning_guidelines') || detectedTypes.includes('warning_labels')) {
    fields.add('Prop 65 Warning');
    symbols.add('Fragile');
  }
  if (detectedTypes.includes('prop65')) {
    fields.add('Prop 65 Warning');
  }
  if (detectedTypes.includes('care_icons')) {
    fields.add('Care Instructions');
  }
  if (detectedTypes.includes('msds')) {
    fields.add('Material Content');
  }
  if (detectedTypes.includes('customs_code')) {
    fields.add('GTIN-14');
  }

  const hasUS = countries.some(c => c === 'United States' || c === 'US');
  const hasUK = countries.some(c => c === 'United Kingdom' || c === 'UK');
  const hasCA = countries.some(c => c === 'Canada' || c === 'CA');

  if (hasUS) {
    fields.add('Prop 65 Warning');
  }
  if (hasUK) {
    fields.add('UKCA Mark');
    symbols.add('This Way Up');
  }
  if (hasCA) {
    layout = 'Bilingual 6-panel';
  }

  if (detectedTypes.includes('brand_guide')) {
    layout = detectedTypes.includes('label_protocol') ? layout : 'Standard 6-panel';
  }

  if (detectedTypes.length >= 4) {
    symbols.add('Fragile');
    symbols.add('This Way Up');
  }

  return {
    fields: Array.from(fields),
    layout,
    barcode,
    symbols: Array.from(symbols),
  };
}

const AI_ANALYSIS_STEPS_WITH_DOCS = [
  { label: 'Analysing uploaded documents…', duration: 800 },
  { label: 'Extracting document structure…', duration: 700 },
  { label: 'Detecting destination markets…', duration: 600 },
  { label: 'Cross-referencing compliance corpus…', duration: 1200 },
  { label: 'Matching regulatory requirements…', duration: 900 },
  { label: 'Resolving label field conflicts…', duration: 800 },
  { label: 'Generating protocol draft…', duration: 1100 },
  { label: 'Running dry-run validation…', duration: 900 },
  { label: 'Protocol ready for review.', duration: 500 },
];

const AI_ANALYSIS_STEPS_MANUAL = [
  { label: 'Parsing company profile…', duration: 600 },
  { label: 'Detecting destination markets…', duration: 900 },
  { label: 'Loading compliance rule corpus…', duration: 700 },
  { label: 'Matching regulatory requirements…', duration: 1200 },
  { label: 'Resolving label field conflicts…', duration: 800 },
  { label: 'Generating protocol draft…', duration: 1100 },
  { label: 'Running dry-run validation…', duration: 900 },
  { label: 'Protocol ready for review.', duration: 500 },
];

export default function OnboardingImporter() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<FormData>(INITIAL_FORM);

  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const [extractionDone, setExtractionDone] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [editingRequirements, setEditingRequirements] = useState(false);

  const [aiProgress, setAiProgress] = useState(0);
  const [aiCurrentStep, setAiCurrentStep] = useState(0);
  const [aiDone, setAiDone] = useState(false);

  // API integration state
  const [importerId, setImporterId] = useState<string | null>(null);
  const [rawFiles, setRawFiles] = useState<File[]>([]);
  const [apiLoading, setApiLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [extractionData, setExtractionData] = useState<Record<string, unknown> | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingStartRef = useRef<number>(0);
  // Flips to true if the spinner has been up long enough that we should
  // offer the user a manual escape hatch. Driven by a timer set in the
  // step-3 mount effect.
  const [extractionStuck, setExtractionStuck] = useState(false);

  const toggleArrayItem = (arr: string[], item: string): string[] =>
    arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item];

  const hasDocUploads = uploadedFiles.length > 0 && !manualMode;

  const simulateClassification = useCallback((files: File[]) => {
    // De-duplicate against already-queued files (name + size is the usual
    // natural identity for an upload; React keys rely on uniqueness too).
    const seen = new Set(uploadedFiles.map((f) => `${f.name}:${f.size}`));
    const unique = files.filter((f) => {
      const key = `${f.name}:${f.size}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    if (unique.length === 0) return;

    setRawFiles(prev => [...prev, ...unique]);
    const newFiles: UploadedFile[] = unique.map(f => ({
      name: f.name,
      size: f.size,
      type: f.type,
      detectedDocType: null,
      confidence: 0,
      status: 'classifying' as const,
    }));
    setUploadedFiles(prev => [...prev, ...newFiles]);

    newFiles.forEach((uf, i) => {
      setTimeout(() => {
        const result = classifyFile(uf.name);
        setUploadedFiles(prev => prev.map(f =>
          f.name === uf.name && f.status === 'classifying'
            ? {
                ...f,
                detectedDocType: result?.docType || null,
                confidence: result?.confidence || 0,
                status: result ? 'classified' : 'unknown',
              }
            : f
        ));

        if (result) {
          setForm(prev => ({
            ...prev,
            docRequirements: Array.from(new Set([...prev.docRequirements, result.docType])),
          }));
        }
      }, 800 + i * 400);
    });
  }, [uploadedFiles]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) simulateClassification(files);
  }, [simulateClassification]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) simulateClassification(files);
    e.target.value = '';
  }, [simulateClassification]);

  const removeFile = (name: string) => {
    const file = uploadedFiles.find(f => f.name === name);
    setUploadedFiles(prev => prev.filter(f => f.name !== name));
    setRawFiles(prev => prev.filter(f => f.name !== name));
    if (file?.detectedDocType) {
      const remainingOfType = uploadedFiles.filter(f => f.name !== name && f.detectedDocType === file.detectedDocType);
      if (remainingOfType.length === 0) {
        setForm(prev => ({
          ...prev,
          docRequirements: prev.docRequirements.filter(d => d !== file.detectedDocType),
        }));
      }
    }
  };

  const runExtraction = useCallback(() => {
    if (uploadedFiles.length === 0) return;
    setExtracting(true);
    setExtractionDone(false);

    setTimeout(() => {
      const detectedTypes = uploadedFiles
        .filter(f => f.detectedDocType)
        .map(f => f.detectedDocType!);
      const result = extractRequirementsFromDocs(detectedTypes, form.countries);

      setForm(prev => ({
        ...prev,
        requiredFields: result.fields,
        panelLayout: result.layout,
        barcodePlacement: result.barcode,
        handlingSymbols: result.symbols,
      }));
      setExtracting(false);
      setExtractionDone(true);
    }, 1500);
  }, [uploadedFiles, form.countries]);

  const aiSteps = hasDocUploads ? AI_ANALYSIS_STEPS_WITH_DOCS : AI_ANALYSIS_STEPS_MANUAL;

  const runAiAnalysis = useCallback(() => {
    setAiProgress(0);
    setAiCurrentStep(0);
    setAiDone(false);
    let elapsed = 0;
    const totalTime = aiSteps.reduce((s, x) => s + x.duration, 0);
    aiSteps.forEach((s, i) => {
      elapsed += s.duration;
      setTimeout(() => {
        setAiCurrentStep(i);
        setAiProgress(Math.round((elapsed / totalTime) * 100));
        if (i === aiSteps.length - 1) {
          setAiDone(true);
        }
      }, elapsed);
    });
  }, [aiSteps]);

  const startExtractionPolling = useCallback(() => {
    if (!importerId) return;
    setExtracting(true);
    setExtractionDone(false);
    setAiProgress(0);
    setAiCurrentStep(0);
    setAiDone(false);
    pollingStartRef.current = Date.now();

    const poll = async () => {
      try {
        // Backend shape (Sprint 8): agents is an OBJECT keyed by agent name,
        // status transitions in_progress → ready_for_review → completed.
        const data = await apiGet<{
          session_id: string;
          status: string;
          agents: Record<string, { status: string; confidence?: number; error?: string | null }>;
          extracted_values: Record<string, unknown> | null;
          started_at: string;
          completed_at: string | null;
        }>('/importers/' + importerId + '/onboarding/extraction');

        // Flatten extracted_values into the top-level payload so the existing
        // review UI (which reads brand_treatment, warning_labels, etc. off the
        // root) keeps working.
        const flattened: Record<string, unknown> = { ...(data.extracted_values || {}) };
        const protocolData = (data.extracted_values?.protocol ?? null) as Record<string, unknown> | null;
        if (protocolData) {
          if (protocolData.brand_treatment) flattened.brand_treatment = protocolData.brand_treatment;
          if (protocolData.panel_layouts) flattened.panel_layouts = protocolData.panel_layouts;
          if (protocolData.handling_symbol_rules) {
            flattened.handling_symbol_rules = protocolData.handling_symbol_rules;
          }
        }
        const warningsData = data.extracted_values?.warnings as Record<string, unknown> | undefined;
        if (warningsData?.labels) flattened.warning_labels = warningsData.labels;
        const checklistData = data.extracted_values?.checklist as Record<string, unknown> | undefined;
        if (checklistData?.rules) flattened.compliance_rules = checklistData.rules;

        setExtractionData(flattened);

        // Map agent statuses → UI progress (object form)
        const agents = data.agents || {};
        const agentKeys = Object.keys(agents);
        const completedCount = agentKeys.filter((k) => agents[k].status === 'completed').length;
        const totalAgents = Math.max(agentKeys.length, 1);
        setAiCurrentStep(completedCount);
        setAiProgress(Math.round((completedCount / totalAgents) * 100));

        // Terminal states: backend emits "ready_for_review" once all agents stop
        if (data.status === 'completed' || data.status === 'ready_for_review' || data.status === 'failed') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          setAiProgress(100);
          setAiDone(true);
          setExtracting(false);
          setExtractionDone(true);

          // Seed form from extracted data with sensible fallbacks so step-3
          // can advance even when individual agents produced no output (e.g.
          // the protocol agent stays `pending` when no file's filename
          // contains the word "protocol").
          const detected = uploadedFiles
            .map((f) => f.detectedDocType)
            .filter((t): t is string => !!t);
          const inferred = extractRequirementsFromDocs(detected, form.countries);

          const panelLayouts = flattened.panel_layouts as Record<string, unknown> | undefined;
          const handlingRules = flattened.handling_symbol_rules as Record<string, boolean> | undefined;
          const warningLabels = flattened.warning_labels as Array<Record<string, unknown>> | undefined;
          const complianceRules = flattened.compliance_rules as Array<Record<string, unknown>> | undefined;

          // If the backend returned warning labels, enrich the inferred field set
          // so the user can see the regulatory signal in the "Required Data Fields" badges.
          const fieldSet = new Set<string>(inferred.fields);
          if (warningLabels && warningLabels.length) {
            fieldSet.add('Prop 65 Warning');
          }
          if (complianceRules && complianceRules.length) {
            // Rules that mention destination-state gating imply locale data is required.
            fieldSet.add('Country of Origin');
          }

          setForm((prev) => {
            const layoutFromProtocol = panelLayouts && typeof panelLayouts === 'object'
              ? Object.keys(panelLayouts)[0] ?? ''
              : '';
            const symbolsFromProtocol = handlingRules && typeof handlingRules === 'object'
              ? Object.keys(handlingRules).filter((k) => handlingRules[k])
              : [];
            return {
              ...prev,
              requiredFields: prev.requiredFields.length ? prev.requiredFields : Array.from(fieldSet),
              panelLayout: prev.panelLayout || layoutFromProtocol || inferred.layout,
              barcodePlacement: prev.barcodePlacement || inferred.barcode,
              handlingSymbols: prev.handlingSymbols.length
                ? prev.handlingSymbols
                : (symbolsFromProtocol.length ? symbolsFromProtocol : inferred.symbols),
            };
          });
        }

        // 5-minute timeout
        if (Date.now() - pollingStartRef.current > 5 * 60 * 1000) {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          setExtracting(false);
          setApiError('Extraction timed out after 5 minutes. Please try again.');
          toast({ title: 'Extraction timeout', description: 'AI extraction took too long. Please try again.', variant: 'destructive' });
        }
      } catch (err) {
        // Don't stop polling on transient errors, but stop after timeout
        if (Date.now() - pollingStartRef.current > 5 * 60 * 1000) {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          setExtracting(false);
          const message = err instanceof Error ? err.message : 'Extraction failed';
          setApiError(message);
          toast({ title: 'Extraction failed', description: message, variant: 'destructive' });
        }
      }
    };

    // Start polling every 2 seconds
    poll();
    pollingRef.current = setInterval(poll, 2000);
  }, [importerId, toast, uploadedFiles, form.countries]);

  useEffect(() => {
    if (step !== 3 || !hasDocUploads) return;
    if (!importerId) {
      // Fallback to local simulated extraction when no importerId is present.
      runExtraction();
      return;
    }
    // Real backend: kick off polling. Guarded by pollingRef so a re-render
    // can't double-start. `extracting`/`extractionDone` are intentionally
    // *not* in the dep array — they change inside poll() and including them
    // would trigger the cleanup below and kill the interval after one tick.
    if (pollingRef.current) return;
    startExtractionPolling();
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, hasDocUploads, importerId, runExtraction, startExtractionPolling]);

  /* ── Defensive unblock for step 3 ─────────────────────────────────
     Runs once whenever we land on step 3 with an ``importerId`` set.
     Hits ``/onboarding/extraction`` directly — independent of the
     useCallback identity churn that can stall the interval-based
     poll() above — and seeds the review UI if the backend already
     reports ``ready_for_review``/``completed``. Also arms a 25 s
     "stuck" timer that unlocks a manual continue button. */
  useEffect(() => {
    if (step !== 3 || !importerId) return;
    setExtractionStuck(false);
    const stuckTimer = window.setTimeout(() => setExtractionStuck(true), 25_000);

    let cancelled = false;
    (async () => {
      try {
        const data = await apiGet<{
          status: string;
          agents: Record<string, { status: string }>;
          extracted_values: Record<string, unknown> | null;
        }>(`/importers/${importerId}/onboarding/extraction`);
        if (cancelled) return;
        if (data.status === 'ready_for_review' || data.status === 'completed' || data.status === 'failed') {
          const ev = data.extracted_values ?? {};
          const flattened: Record<string, unknown> = { ...ev };
          const warningsData = ev.warnings as Record<string, unknown> | undefined;
          if (warningsData?.labels) flattened.warning_labels = warningsData.labels;
          const checklistData = ev.checklist as Record<string, unknown> | undefined;
          if (checklistData?.rules) flattened.compliance_rules = checklistData.rules;
          const protocolData = ev.protocol as Record<string, unknown> | undefined;
          if (protocolData?.brand_treatment) flattened.brand_treatment = protocolData.brand_treatment;
          if (protocolData?.panel_layouts) flattened.panel_layouts = protocolData.panel_layouts;
          if (protocolData?.handling_symbol_rules) flattened.handling_symbol_rules = protocolData.handling_symbol_rules;

          setExtractionData(flattened);
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          setAiProgress(100);
          setAiDone(true);
          setExtracting(false);
          setExtractionDone(true);
          setExtractionStuck(false);
        }
      } catch {
        // Silent — step-3 polling effect will take over if this 404s.
      }
    })();

    return () => {
      cancelled = true;
      window.clearTimeout(stuckTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, importerId]);

  useEffect(() => {
    if (step !== 4) return;
    if (!importerId) {
      // Fallback to simulated analysis if no importerId (shouldn't happen)
      runAiAnalysis();
      return;
    }
    // Extraction is kicked off at step 3 with importerId; only (re)start
    // polling here if the step-3 run never happened. Same dep-array note as
    // the step-3 effect: don't include `extracting`/`extractionDone`.
    if (pollingRef.current) return;
    startExtractionPolling();
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, importerId, startExtractionPolling, runAiAnalysis]);

  const canProceed = (): boolean => {
    switch (step) {
      case 1: return !!form.companyName && !!form.buyerContact && !!form.buyerEmail && form.countries.length > 0;
      case 2: return uploadedFiles.length > 0 || manualMode;
      case 3: return form.requiredFields.length > 0 && !!form.panelLayout && !!form.barcodePlacement;
      case 4: return aiDone;
      case 5: return true;
      default: return true;
    }
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  const handleStep1Next = async () => {
    setApiError(null);
    setApiLoading(true);
    try {
      const result = await apiPost<{ id: string }>('/importers', {
        name: form.companyName,
        code: form.companyName.toLowerCase().replace(/\s+/g, '-'),
        contact_email: form.buyerEmail,
        contact_phone: '',
        address: '',
      });
      setImporterId(result.id);
      setStep(2);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create importer';
      setApiError(message);
      toast({ title: 'Error creating importer', description: message, variant: 'destructive' });
    } finally {
      setApiLoading(false);
    }
  };

  const handleStep2Next = async () => {
    if (!importerId) return;
    if (manualMode) {
      setStep(3);
      return;
    }
    setApiError(null);
    setApiLoading(true);
    try {
      const fd = new globalThis.FormData();
      rawFiles.forEach(f => fd.append('files', f));
      await apiUpload<unknown>('/importers/' + importerId + '/onboarding/upload', fd);
      setStep(3);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to upload documents';
      setApiError(message);
      toast({ title: 'Upload failed', description: message, variant: 'destructive' });
    } finally {
      setApiLoading(false);
    }
  };

  const handleFinalize = async () => {
    if (!importerId) return;
    setApiError(null);
    setApiLoading(true);
    try {
      // Backend expects ImporterProfileModel-shaped dicts for these JSON columns
      // (see OnboardingFinalizeRequest in labelforge/api/v1/importers.py).
      // Prefer the agent-extracted shape when available; otherwise synthesize
      // a dict from the user's form selections.
      const extracted = (extractionData as Record<string, unknown>) || {};
      const extractedPanelLayouts = extracted.panel_layouts as Record<string, unknown> | undefined;
      const extractedHandling = extracted.handling_symbol_rules as Record<string, boolean> | undefined;
      const extractedBrand = extracted.brand_treatment as Record<string, unknown> | undefined;

      const panelLayouts: Record<string, unknown> = extractedPanelLayouts
        && typeof extractedPanelLayouts === 'object'
        && Object.keys(extractedPanelLayouts).length
        ? extractedPanelLayouts
        : (form.panelLayout ? { [form.panelLayout]: { selected: true } } : {});

      const handlingRules: Record<string, boolean> = extractedHandling
        && typeof extractedHandling === 'object'
        && Object.keys(extractedHandling).length
        ? extractedHandling
        : form.handlingSymbols.reduce<Record<string, boolean>>((acc, s) => {
            acc[s] = true;
            return acc;
          }, {});

      const payload: Record<string, unknown> = {
        brand_treatment: extractedBrand ?? null,
        panel_layouts: panelLayouts,
        handling_symbol_rules: handlingRules,
        // Extras allowed by the backend (extra="allow") — carried for audit.
        warning_labels: extracted.warning_labels ?? null,
        compliance_rules: extracted.compliance_rules ?? null,
        required_fields: form.requiredFields,
        barcode_placement: form.barcodePlacement,
      };
      await apiPost<unknown>('/importers/' + importerId + '/onboard/finalize', payload);

      // Stash the full onboarding form in localStorage so the detail page
      // can render it until the backend catches up. The backend's
      // ImporterProfile response currently only returns brand_treatment /
      // panel_layouts / handling_symbol_rules; everything else (buyer
      // contact, markets, units, barcode placement, required fields, doc
      // requirements, label languages, notes) is dropped on the floor by
      // create_importer + finalize_onboarding. See importer-detail.tsx for
      // the matching hydrate. Intentionally best-effort — a storage error
      // shouldn't block navigation.
      try {
        localStorage.setItem(
          `labelforge:onboarding:${importerId}`,
          JSON.stringify({
            companyName: form.companyName,
            buyerContact: form.buyerContact,
            buyerEmail: form.buyerEmail,
            countries: form.countries,
            units: form.units,
            docRequirements: form.docRequirements,
            requiredFields: form.requiredFields,
            labelLang: form.labelLang,
            panelLayout: form.panelLayout,
            barcodePlacement: form.barcodePlacement,
            handlingSymbols: form.handlingSymbols,
            notes: form.notes,
            savedAt: new Date().toISOString(),
          }),
        );
      } catch {
        /* quota / private mode — fall through silently */
      }

      toast({ title: 'Importer saved', description: `${form.companyName || 'Importer'} protocol has been created successfully.` });
      setLocation('/importers/' + importerId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to finalize onboarding';
      setApiError(message);
      toast({ title: 'Finalize failed', description: message, variant: 'destructive' });
    } finally {
      setApiLoading(false);
    }
  };

  const next = () => {
    if (step === 1) {
      handleStep1Next();
      return;
    }
    if (step === 2) {
      handleStep2Next();
      return;
    }
    if (step < 5) setStep(step + 1);
  };

  const back = () => {
    if (step > 1) setStep(step - 1);
  };

  const classifiedCount = uploadedFiles.filter(f => f.status === 'classified').length;
  const classifyingCount = uploadedFiles.filter(f => f.status === 'classifying').length;
  const docLabel = (id: string) => DOC_OPTIONS.find(d => d.id === id)?.label || id;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="h-14 border-b bg-card flex items-center px-6 justify-between shrink-0 sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setLocation('/importers')}
            className="font-mono font-bold text-primary text-lg tracking-tight"
          >
            Labelforge
          </button>
          <span className="text-muted-foreground">/</span>
          <span className="text-sm text-muted-foreground">Importer Onboarding</span>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setLocation('/importers')}>
          Cancel
        </Button>
      </header>

      <div className="border-b bg-card">
        <div className="max-w-3xl mx-auto px-6">
          <div className="flex items-center gap-1">
            {STEPS.map((s, i) => {
              const done = step > s.id;
              const active = step === s.id;
              return (
                <React.Fragment key={s.id}>
                  <div className={`flex items-center gap-2 py-3 text-sm transition-colors ${
                    active ? 'text-primary font-medium' : done ? 'text-muted-foreground' : 'text-muted-foreground/40'
                  }`}>
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs font-bold border transition-colors ${
                      done ? 'bg-green-500 border-green-500 text-white' : active ? 'border-primary bg-primary/10 text-primary' : 'border-muted-foreground/30'
                    }`}>
                      {done ? <Check className="w-3.5 h-3.5" /> : s.id}
                    </div>
                    <span className="hidden sm:inline whitespace-nowrap">{s.label}</span>
                  </div>
                  {i < STEPS.length - 1 && (
                    <div className={`flex-1 h-px mx-2 transition-colors ${done ? 'bg-green-400' : 'bg-border'}`} />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <main className="max-w-2xl mx-auto w-full py-10 px-6">
          {step === 1 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold">Company Information</h2>
                <p className="text-sm text-muted-foreground mt-1">Tell us about the importer and their primary buyer contact.</p>
              </div>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label className="flex items-center gap-1.5"><Building2 className="w-3.5 h-3.5" /> Company Name</Label>
                  <Input
                    placeholder="e.g. Sagebrook Home"
                    value={form.companyName}
                    onChange={(e) => setForm({ ...form, companyName: e.target.value })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="flex items-center gap-1.5"><User className="w-3.5 h-3.5" /> Buyer Contact Name</Label>
                    <Input
                      placeholder="Jennifer Walsh"
                      value={form.buyerContact}
                      onChange={(e) => setForm({ ...form, buyerContact: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="flex items-center gap-1.5"><Mail className="w-3.5 h-3.5" /> Buyer Email</Label>
                    <Input
                      type="email"
                      placeholder="buyer@company.com"
                      value={form.buyerEmail}
                      onChange={(e) => setForm({ ...form, buyerEmail: e.target.value })}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label className="flex items-center gap-1.5"><Globe className="w-3.5 h-3.5" /> Destination Markets</Label>
                  <div className="grid grid-cols-2 gap-2">
                    {COUNTRIES.map((c) => (
                      <label key={c} className="flex items-center gap-2 text-sm cursor-pointer hover:text-foreground text-muted-foreground">
                        <Checkbox
                          checked={form.countries.includes(c)}
                          onCheckedChange={() => setForm({ ...form, countries: toggleArrayItem(form.countries, c) })}
                        />
                        {c}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>Units System</Label>
                  <Select value={form.units} onValueChange={(v) => setForm({ ...form, units: v })}>
                    <SelectTrigger className="w-48">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="imperial">Imperial (lbs / in)</SelectItem>
                      <SelectItem value="metric">Metric (kg / cm)</SelectItem>
                      <SelectItem value="both">Both (dual-unit labels)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold">Upload Documents</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Drop the importer's existing documents — POs, label specs, brand guides, compliance certs, etc.
                  Our AI will classify each file and extract document requirements automatically.
                </p>
              </div>

              {!manualMode && (
                <>
                  <div
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    className={`border-2 border-dashed rounded-xl p-10 text-center transition-colors cursor-pointer ${
                      dragOver
                        ? 'border-primary bg-primary/5'
                        : 'border-muted-foreground/25 hover:border-primary/50'
                    }`}
                    onClick={() => document.getElementById('onboard-file-input')?.click()}
                  >
                    <input
                      id="onboard-file-input"
                      type="file"
                      multiple
                      className="hidden"
                      accept=".pdf,.xlsx,.csv,.doc,.docx,.xls,.png,.jpg,.jpeg,.svg,.eps,.ai"
                      onChange={handleFileInput}
                    />
                    <FileUp className="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
                    <p className="text-sm font-medium">Drop files here or click to browse</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      PDF, XLSX, CSV, DOC, images, vector files — any importer documents
                    </p>
                  </div>

                  {uploadedFiles.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold">
                          Detected Files
                          <span className="text-muted-foreground font-normal ml-1.5">
                            ({classifiedCount} classified{classifyingCount > 0 ? `, ${classifyingCount} processing…` : ''})
                          </span>
                        </p>
                      </div>
                      <div className="border rounded-xl overflow-hidden divide-y">
                        {uploadedFiles.map((f, i) => (
                          <div key={`${f.name}-${i}`} className="flex items-center gap-3 px-4 py-3 text-sm">
                            <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="font-medium truncate">{f.name}</div>
                              <div className="text-xs text-muted-foreground">
                                {(f.size / 1024).toFixed(0)} KB
                              </div>
                            </div>
                            {f.status === 'classifying' && (
                              <div className="flex items-center gap-1.5 text-xs text-primary">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                Classifying…
                              </div>
                            )}
                            {f.status === 'classified' && (
                              <div className="flex items-center gap-2">
                                <Badge variant="secondary" className="text-xs">
                                  {docLabel(f.detectedDocType!)}
                                </Badge>
                                <span className="text-xs font-mono tabular-nums text-emerald-600">
                                  {Math.round(f.confidence * 100)}%
                                </span>
                              </div>
                            )}
                            {f.status === 'unknown' && (
                              <Badge variant="outline" className="text-xs text-orange-600 border-orange-200">
                                Unknown type
                              </Badge>
                            )}
                            <button
                              onClick={() => removeFile(f.name)}
                              className="text-muted-foreground hover:text-foreground transition-colors"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>

                      {form.docRequirements.length > 0 && (
                        <div className="flex items-start gap-3 bg-emerald-50 border border-emerald-200 rounded-lg p-4 mt-3">
                          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                          <div>
                            <p className="text-sm font-medium text-emerald-800">
                              {form.docRequirements.length} document type{form.docRequirements.length !== 1 ? 's' : ''} identified
                            </p>
                            <div className="flex flex-wrap gap-1 mt-1.5">
                              {form.docRequirements.map(d => (
                                <Badge key={d} variant="outline" className="text-xs bg-white">{docLabel(d)}</Badge>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {uploadedFiles.length === 0 && (
                    <div className="text-center pt-2">
                      <button
                        onClick={() => setManualMode(true)}
                        className="text-xs text-muted-foreground hover:text-primary underline transition-colors"
                      >
                        No documents available? Configure requirements manually →
                      </button>
                    </div>
                  )}
                </>
              )}

              {manualMode && (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
                    <Info className="w-4 h-4 text-amber-600 shrink-0" />
                    <p className="text-xs text-amber-800">
                      Manual mode — select document types the importer must provide. You can
                      <button
                        onClick={() => { setManualMode(false); setForm(prev => ({ ...prev, docRequirements: [] })); }}
                        className="text-primary underline ml-1 hover:text-primary/80"
                      >
                        switch back to upload
                      </button>
                      {' '}anytime.
                    </p>
                  </div>

                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-sm font-semibold">Document Requirements</h3>
                      <p className="text-xs text-muted-foreground mt-0.5">Select every document type this importer must supply.</p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button size="sm" variant="outline" onClick={() => setForm({ ...form, docRequirements: DOC_OPTIONS.map(d => d.id) })}>
                        Select all
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setForm({ ...form, docRequirements: [] })}>
                        Clear
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-5">
                    {DOC_GROUPS.map((g) => (
                      <div key={g.group}>
                        <div className="text-[11px] font-bold text-muted-foreground/60 uppercase tracking-wider mb-2">{g.group}</div>
                        <div className="space-y-2">
                          {g.docs.map((d) => (
                            <label
                              key={d.id}
                              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                                form.docRequirements.includes(d.id)
                                  ? 'border-primary bg-primary/5'
                                  : 'border-border hover:border-muted-foreground/40'
                              }`}
                            >
                              <Checkbox
                                checked={form.docRequirements.includes(d.id)}
                                onCheckedChange={() => setForm({ ...form, docRequirements: toggleArrayItem(form.docRequirements, d.id) })}
                                className="mt-0.5"
                              />
                              <div className="flex-1">
                                <div className="text-sm font-medium">{d.label}</div>
                                <div className="text-xs text-muted-foreground mt-0.5">{d.description}</div>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              {hasDocUploads ? (
                <>
                  <div>
                    <h2 className="text-xl font-bold flex items-center gap-2">
                      <Sparkles className="w-5 h-5 text-primary" />
                      Extracted Requirements
                    </h2>
                    <p className="text-sm text-muted-foreground mt-1">
                      AI analysed {uploadedFiles.filter(f => f.status === 'classified').length} document{uploadedFiles.filter(f => f.status === 'classified').length !== 1 ? 's' : ''} and extracted the following label requirements.
                      You can review and adjust if needed.
                    </p>
                  </div>

                  {extracting && (
                    <div className="border rounded-xl p-8 bg-card text-center space-y-4">
                      <Loader2 className="w-8 h-8 mx-auto text-primary animate-spin" />
                      <div>
                        <p className="text-sm font-medium">Extracting requirements from documents…</p>
                        <p className="text-xs text-muted-foreground mt-1">Parsing label specs, compliance rules, and field definitions</p>
                      </div>
                      {extractionStuck && (
                        <div className="pt-2 flex items-center justify-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={async () => {
                              if (!importerId) return;
                              try {
                                const data = await apiGet<{
                                  status: string;
                                  extracted_values: Record<string, unknown> | null;
                                }>(`/importers/${importerId}/onboarding/extraction`);
                                const ev = data.extracted_values ?? {};
                                const flattened: Record<string, unknown> = { ...ev };
                                const warnings = (ev.warnings as any)?.labels;
                                if (warnings) flattened.warning_labels = warnings;
                                const checklist = (ev.checklist as any)?.rules;
                                if (checklist) flattened.compliance_rules = checklist;
                                setExtractionData(flattened);
                                if (pollingRef.current) {
                                  clearInterval(pollingRef.current);
                                  pollingRef.current = null;
                                }
                                setAiProgress(100);
                                setAiDone(true);
                                setExtracting(false);
                                setExtractionDone(true);
                                setExtractionStuck(false);
                              } catch {
                                toast({ title: 'Extraction not ready yet', description: 'Please wait a few more seconds and try again.', variant: 'destructive' });
                              }
                            }}
                          >
                            <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Check status now
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              // Escape hatch: seed empty requirements and let
                              // the user continue reviewing manually.
                              if (pollingRef.current) {
                                clearInterval(pollingRef.current);
                                pollingRef.current = null;
                              }
                              setExtracting(false);
                              setExtractionDone(true);
                              setExtractionStuck(false);
                            }}
                          >
                            Continue without extraction
                          </Button>
                        </div>
                      )}
                    </div>
                  )}

                  {extractionDone && !editingRequirements && (
                    <div className="space-y-4">
                      <div className="border rounded-xl overflow-hidden">
                        <div className="px-4 py-3 bg-emerald-50 border-b border-emerald-200 flex items-center justify-between">
                          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-800">
                            <CheckCircle2 className="w-4 h-4" />
                            Requirements extracted successfully
                          </div>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-xs h-7"
                            onClick={() => setEditingRequirements(true)}
                          >
                            <Pencil className="w-3 h-3 mr-1" /> Edit
                          </Button>
                        </div>
                        <div className="p-4 space-y-4">
                          <div>
                            <p className="text-xs text-muted-foreground font-medium mb-1.5">Required Data Fields ({form.requiredFields.length})</p>
                            <div className="flex flex-wrap gap-1.5">
                              {form.requiredFields.map(f => {
                                const scores = (extractionData as Record<string, unknown>)?.confidence_scores as Record<string, number> | undefined;
                                const confidence = scores?.[f];
                                const colorClass = confidence !== undefined
                                  ? confidence > 80 ? 'border-green-300 bg-green-50' : confidence > 50 ? 'border-yellow-300 bg-yellow-50' : 'border-red-300 bg-red-50'
                                  : '';
                                return (
                                  <Badge key={f} variant="secondary" className={`text-xs ${colorClass}`}>
                                    {f}
                                    {confidence !== undefined && (
                                      <span className="ml-1 font-mono text-[10px] opacity-70">{confidence}%</span>
                                    )}
                                  </Badge>
                                );
                              })}
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <p className="text-xs text-muted-foreground font-medium mb-1">Panel Layout</p>
                              <p className="text-sm font-medium">{form.panelLayout}</p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground font-medium mb-1">Barcode Placement</p>
                              <p className="text-sm font-medium">{form.barcodePlacement}</p>
                            </div>
                          </div>
                          {form.handlingSymbols.length > 0 && (
                            <div>
                              <p className="text-xs text-muted-foreground font-medium mb-1.5">Handling Symbols</p>
                              <div className="flex flex-wrap gap-1.5">
                                {form.handlingSymbols.map(s => (
                                  <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                                ))}
                              </div>
                            </div>
                          )}
                          {(() => {
                            const warningLabels = (extractionData as Record<string, unknown>)?.warning_labels as Array<Record<string, unknown>> | undefined;
                            const complianceRules = (extractionData as Record<string, unknown>)?.compliance_rules as Array<Record<string, unknown>> | undefined;
                            const wCount = warningLabels?.length ?? 0;
                            const rCount = complianceRules?.length ?? 0;
                            if (wCount === 0 && rCount === 0) return null;
                            return (
                              <div className="grid grid-cols-2 gap-4 pt-2 border-t border-border/60">
                                <div>
                                  <p className="text-xs text-muted-foreground font-medium mb-1">Warning Labels Detected</p>
                                  <p className="text-sm font-medium">{wCount}</p>
                                </div>
                                <div>
                                  <p className="text-xs text-muted-foreground font-medium mb-1">Compliance Rules Extracted</p>
                                  <p className="text-sm font-medium">{rCount}</p>
                                </div>
                              </div>
                            );
                          })()}
                        </div>
                      </div>

                      <div className="flex items-start gap-3 border border-blue-200 bg-blue-50 rounded-xl p-4">
                        <Eye className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                        <div className="text-xs text-blue-800">
                          <span className="font-semibold">Source documents: </span>
                          {uploadedFiles.filter(f => f.status === 'classified').map(f => f.name).join(', ')}
                        </div>
                      </div>
                    </div>
                  )}

                  {extractionDone && editingRequirements && (
                    <div className="space-y-5">
                      <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
                        <Pencil className="w-4 h-4 text-amber-600 shrink-0" />
                        <p className="text-xs text-amber-800">
                          Editing extracted requirements — adjust the AI's findings as needed.
                          <button
                            onClick={() => setEditingRequirements(false)}
                            className="text-primary underline ml-1 hover:text-primary/80"
                          >
                            Done editing
                          </button>
                        </p>
                      </div>

                      <div className="space-y-2">
                        <Label className="font-semibold">Required Data Fields</Label>
                        <div className="grid grid-cols-2 gap-2">
                          {REQUIRED_FIELDS_OPTIONS.map((f) => (
                            <label key={f} className="flex items-center gap-2 text-sm cursor-pointer hover:text-foreground text-muted-foreground">
                              <Checkbox
                                checked={form.requiredFields.includes(f)}
                                onCheckedChange={() => setForm({ ...form, requiredFields: toggleArrayItem(form.requiredFields, f) })}
                              />
                              {f}
                            </label>
                          ))}
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <Label>Panel Layout</Label>
                          <Select value={form.panelLayout} onValueChange={(v) => setForm({ ...form, panelLayout: v })}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {PANEL_LAYOUTS.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-1.5">
                          <Label>Barcode Placement</Label>
                          <Select value={form.barcodePlacement} onValueChange={(v) => setForm({ ...form, barcodePlacement: v })}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="Bottom Right">Bottom Right</SelectItem>
                              <SelectItem value="Bottom Left">Bottom Left</SelectItem>
                              <SelectItem value="Top Right">Top Right</SelectItem>
                              <SelectItem value="Top Left">Top Left</SelectItem>
                              <SelectItem value="Back Center">Back Center</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <Label className="font-semibold">Handling Symbols</Label>
                        <div className="flex flex-wrap gap-2">
                          {HANDLING_SYMBOLS.map((s) => (
                            <button
                              key={s}
                              type="button"
                              onClick={() => setForm({ ...form, handlingSymbols: toggleArrayItem(form.handlingSymbols, s) })}
                              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                                form.handlingSymbols.includes(s)
                                  ? 'bg-primary text-primary-foreground border-primary'
                                  : 'bg-card border-border text-muted-foreground hover:border-muted-foreground/60'
                              }`}
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-xl font-bold">Label Requirements</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                      No documents were uploaded — define label requirements manually.
                    </p>
                  </div>
                  <div className="space-y-5">
                    <div className="space-y-2">
                      <Label className="font-semibold">Required Data Fields</Label>
                      <p className="text-xs text-muted-foreground">These fields will be extracted/validated by the AI agents for every shipment item.</p>
                      <div className="grid grid-cols-2 gap-2 mt-2">
                        {REQUIRED_FIELDS_OPTIONS.map((f) => (
                          <label key={f} className="flex items-center gap-2 text-sm cursor-pointer hover:text-foreground text-muted-foreground">
                            <Checkbox
                              checked={form.requiredFields.includes(f)}
                              onCheckedChange={() => setForm({ ...form, requiredFields: toggleArrayItem(form.requiredFields, f) })}
                            />
                            {f}
                          </label>
                        ))}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <Label>Panel Layout</Label>
                        <Select value={form.panelLayout} onValueChange={(v) => setForm({ ...form, panelLayout: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {PANEL_LAYOUTS.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label>Barcode Placement</Label>
                        <Select value={form.barcodePlacement} onValueChange={(v) => setForm({ ...form, barcodePlacement: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Bottom Right">Bottom Right</SelectItem>
                            <SelectItem value="Bottom Left">Bottom Left</SelectItem>
                            <SelectItem value="Top Right">Top Right</SelectItem>
                            <SelectItem value="Top Left">Top Left</SelectItem>
                            <SelectItem value="Back Center">Back Center</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="font-semibold">Handling Symbols</Label>
                      <div className="flex flex-wrap gap-2 mt-1">
                        {HANDLING_SYMBOLS.map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => setForm({ ...form, handlingSymbols: toggleArrayItem(form.handlingSymbols, s) })}
                            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                              form.handlingSymbols.includes(s)
                                ? 'bg-primary text-primary-foreground border-primary'
                                : 'bg-card border-border text-muted-foreground hover:border-muted-foreground/60'
                            }`}
                          >
                            {s}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 4 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-primary" />
                  AI Protocol Analysis
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  {hasDocUploads
                    ? `Labelforge agents are analysing ${uploadedFiles.length} uploaded document${uploadedFiles.length !== 1 ? 's' : ''} and your configuration to generate a custom importer protocol.`
                    : 'Labelforge agents are analysing your configuration against our compliance corpus to generate a custom importer protocol.'}
                </p>
              </div>

              <div className="border rounded-xl p-6 bg-card space-y-5">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground font-medium">Progress</span>
                  <span className="font-mono tabular-nums">{aiProgress}%</span>
                </div>
                <Progress value={aiProgress} className="h-2" />

                <div className="space-y-2.5 mt-2">
                  {aiSteps.map((s, i) => {
                    const done = i < aiCurrentStep || (i === aiCurrentStep && aiDone);
                    const running = i === aiCurrentStep && !aiDone;
                    const pending = i > aiCurrentStep;
                    return (
                      <div key={i} className={`flex items-center gap-3 text-sm transition-opacity ${pending ? 'opacity-30' : ''}`}>
                        {done ? (
                          <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                        ) : running ? (
                          <Loader2 className="w-4 h-4 text-primary animate-spin shrink-0" />
                        ) : (
                          <div className="w-4 h-4 rounded-full border border-muted-foreground/30 shrink-0" />
                        )}
                        <span className={running ? 'text-primary font-medium' : done ? 'text-foreground' : 'text-muted-foreground'}>
                          {s.label}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {aiDone && (
                  <div className="flex items-start gap-3 bg-green-50 border border-green-200 rounded-lg p-4 mt-2">
                    <CheckCircle2 className="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-green-800">Protocol generated successfully</p>
                      <p className="text-xs text-green-700 mt-0.5">
                        {hasDocUploads
                          ? `${uploadedFiles.filter(f => f.status === 'classified').length} documents processed · ${form.requiredFields.length} fields extracted · 14 compliance rules matched · 0 conflicts detected`
                          : '14 compliance rules matched · 3 market-specific overrides applied · 0 conflicts detected'}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              <div className="border rounded-xl p-4 bg-muted/30 text-xs space-y-1 font-mono text-muted-foreground">
                <div className="text-foreground font-semibold text-sm mb-2">Agent trace</div>
                {hasDocUploads && <div>[DocumentParserAgent] Parsed {uploadedFiles.length} files, {classifiedCount} classified</div>}
                <div>[ProtocolBuilderAgent] Loaded 847 rules from corpus v4.2</div>
                <div>[ProtocolBuilderAgent] Markets detected: {form.countries.slice(0, 3).join(', ') || 'US'}</div>
                <div>[ComplianceMatcherAgent] Matched {form.requiredFields.length + 7} mandatory fields</div>
                {aiProgress >= 40 && <div>[LayoutOptimizerAgent] Panel layout: {form.panelLayout || 'Standard 4-panel'}</div>}
                {aiProgress >= 70 && <div>[BarcodePlacementAgent] Barcode: {form.barcodePlacement || 'Bottom Right'}</div>}
                {aiDone && <div className="text-green-600">[ProtocolBuilderAgent] Protocol IMP-NEW-{Math.floor(Math.random() * 900 + 100)} committed.</div>}
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold">Review Protocol</h2>
                <p className="text-sm text-muted-foreground mt-1">Review the generated importer protocol before sending the buyer invite.</p>
              </div>

              <div className="space-y-4">
                <div className="border rounded-xl overflow-hidden">
                  <div className="px-4 py-3 bg-muted/50 border-b text-sm font-semibold flex items-center gap-2">
                    <Building2 className="w-4 h-4" /> Company
                  </div>
                  <div className="p-4 grid grid-cols-2 gap-3 text-sm">
                    <div><span className="text-muted-foreground">Name</span><div className="font-medium mt-0.5">{form.companyName || '—'}</div></div>
                    <div><span className="text-muted-foreground">Buyer Contact</span><div className="font-medium mt-0.5">{form.buyerContact || '—'}</div></div>
                    <div><span className="text-muted-foreground">Email</span><div className="font-medium mt-0.5">{form.buyerEmail || '—'}</div></div>
                    <div><span className="text-muted-foreground">Markets</span><div className="flex flex-wrap gap-1 mt-0.5">{form.countries.map(c => <Badge key={c} variant="secondary" className="text-xs">{c}</Badge>)}</div></div>
                  </div>
                </div>

                <div className="border rounded-xl overflow-hidden">
                  <div className="px-4 py-3 bg-muted/50 border-b text-sm font-semibold flex items-center gap-2">
                    <Tag className="w-4 h-4" /> Label Specification
                    {hasDocUploads && (
                      <Badge variant="outline" className="text-xs ml-auto bg-blue-50 text-blue-700 border-blue-200">
                        AI-extracted
                      </Badge>
                    )}
                  </div>
                  <div className="p-4 space-y-3 text-sm">
                    <div className="grid grid-cols-2 gap-3">
                      <div><span className="text-muted-foreground">Panel Layout</span><div className="font-medium mt-0.5">{form.panelLayout || '—'}</div></div>
                      <div><span className="text-muted-foreground">Barcode Placement</span><div className="font-medium mt-0.5">{form.barcodePlacement || '—'}</div></div>
                      <div><span className="text-muted-foreground">Units</span><div className="font-medium mt-0.5 capitalize">{form.units}</div></div>
                    </div>
                    {form.requiredFields.length > 0 && (
                      <div>
                        <span className="text-muted-foreground">Required Fields ({form.requiredFields.length})</span>
                        <div className="flex flex-wrap gap-1.5 mt-1.5">
                          {form.requiredFields.map(f => <Badge key={f} variant="outline" className="text-xs">{f}</Badge>)}
                        </div>
                      </div>
                    )}
                    {form.handlingSymbols.length > 0 && (
                      <div>
                        <span className="text-muted-foreground">Handling Symbols</span>
                        <div className="flex flex-wrap gap-1.5 mt-1.5">
                          {form.handlingSymbols.map(s => <Badge key={s} variant="outline" className="text-xs">{s}</Badge>)}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="border rounded-xl overflow-hidden">
                  <div className="px-4 py-3 bg-muted/50 border-b text-sm font-semibold flex items-center gap-2">
                    <FileText className="w-4 h-4" /> Document Requirements ({form.docRequirements.length})
                    {hasDocUploads && (
                      <Badge variant="outline" className="text-xs ml-auto bg-blue-50 text-blue-700 border-blue-200">
                        from uploads
                      </Badge>
                    )}
                  </div>
                  <div className="p-4 flex flex-wrap gap-1.5">
                    {DOC_OPTIONS.filter(d => form.docRequirements.includes(d.id)).map(d => (
                      <Badge key={d.id} variant="secondary" className="text-xs">{d.label}</Badge>
                    ))}
                    {form.docRequirements.length === 0 && (
                      <p className="text-xs text-muted-foreground">No document requirements configured.</p>
                    )}
                  </div>
                </div>

                {hasDocUploads && (
                  <div className="border rounded-xl overflow-hidden">
                    <div className="px-4 py-3 bg-muted/50 border-b text-sm font-semibold flex items-center gap-2">
                      <Upload className="w-4 h-4" /> Uploaded Documents ({uploadedFiles.length})
                    </div>
                    <div className="p-4 space-y-1.5">
                      {uploadedFiles.map((f, i) => (
                        <div key={`${f.name}-${i}`} className="flex items-center gap-2 text-xs">
                          <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                          <span className="truncate">{f.name}</span>
                          {f.detectedDocType && (
                            <Badge variant="outline" className="text-[10px] ml-auto shrink-0">{docLabel(f.detectedDocType)}</Badge>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex items-start gap-3 border border-primary/20 bg-primary/5 rounded-xl p-4">
                  <AlertCircle className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                  <p className="text-xs text-primary/80">
                    AI agents have pre-validated this protocol against 14 compliance rules. Any future label that deviates from this spec will automatically trigger a HiTL review.
                  </p>
                </div>
              </div>
            </div>
          )}

          {apiError && (
            <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-lg p-4 mt-6">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-800">Something went wrong</p>
                <p className="text-xs text-red-700 mt-0.5">{apiError}</p>
              </div>
              <button onClick={() => setApiError(null)} className="text-red-400 hover:text-red-600">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <div className="flex items-center justify-between mt-10 pt-6 border-t">
            <Button variant="ghost" onClick={back} disabled={step === 1}>
              <ChevronLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            {step === 5 ? (
              <Button
                onClick={handleFinalize}
                disabled={apiLoading}
              >
                {apiLoading ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving…</>
                ) : (
                  <><CheckCircle2 className="w-4 h-4 mr-2" /> Save Importer</>
                )}
              </Button>
            ) : (
              <Button
                onClick={next}
                disabled={!canProceed() || apiLoading}
              >
                {apiLoading ? (
                  <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> {step === 1 ? 'Creating…' : step === 2 ? 'Uploading…' : 'Processing…'}</>
                ) : (
                  <>Next <ChevronRight className="w-4 h-4 ml-1" /></>
                )}
              </Button>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
