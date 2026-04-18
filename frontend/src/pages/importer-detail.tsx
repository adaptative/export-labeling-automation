import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useRoute, useLocation } from 'wouter';
import { apiGet, apiPut, apiUpload, apiDelete } from '../api/authInterceptor';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { useToast } from '@/hooks/use-toast';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Building2, Globe, Mail, User, Tag, FileText, CheckCircle2, AlertCircle,
  Clock, ExternalLink, Package, ChevronRight, Settings, Layers,
  Upload, Download, Trash2, RefreshCw, Send, Plus, FilePlus, Eye,
  FileType2, File, MoreHorizontal, Save, X, Loader2, AlertTriangle,
} from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

/* ─── Types matching backend response ────────────────────────────── */

interface ImporterProfile {
  id: string;
  name: string;
  code: string;
  status: string;
  countries: string[];
  profile_version: number;
  onboarding_progress: number;
  orders_mtd: number;
  open_hitl: number;
  buyer_contact: string;
  buyer_email: string;
  portal_token: string;
  since: string;
  label_languages: string[];
  units: string;
  barcode_placement: string;
  // Raw backend response uses `importer_id` — kept here so the adapter in
  // `fetchProfile` doesn't lose it when mapping back to `id`.
  importer_id?: string;
  // Backend (ImporterProfile in labelforge/contracts/models.py) returns these
  // as free-form JSON dicts — not strings. The onboarding agents write shapes
  // like `brand_treatment: {primary_color, font_family, logo_position}` and
  // `panel_layouts: {carton_top: [...], carton_side: [...]}`. Rendering those
  // straight into JSX crashes React ("Objects are not valid as a React child"),
  // so accept the dict shape here and format it for display below.
  panel_layout?: string | null;
  panel_layouts?: Record<string, unknown> | null;
  brand_treatment?: Record<string, unknown> | string | null;
  handling_symbol_rules?: Record<string, boolean> | string[] | null;
  required_fields: string[];
  doc_requirements: string[];
  notes: string;
}

/** Flatten an extraction dict into a short, human-readable summary.
 *  Used so the importer-detail page doesn't attempt to render an
 *  object as a React child (which throws at runtime). */
function formatProfileDict(value: unknown, { max = 3 }: { max?: number } = {}): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(String).join(', ');
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    const pairs = entries.slice(0, max).map(([k, v]) => {
      const key = k.replace(/_/g, ' ');
      if (v === true) return key;
      if (v === false || v == null) return '';
      if (typeof v === 'string' || typeof v === 'number') return `${key}: ${v}`;
      return key;
    }).filter(Boolean);
    const suffix = entries.length > max ? `, +${entries.length - max} more` : '';
    return pairs.join(' · ') + suffix;
  }
  return String(value);
}

/** Extract an enabled-symbol list from either a dict (`{fragile: true}`)
 *  or a legacy string array. */
function handlingSymbolList(value: ImporterProfile['handling_symbol_rules']): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  return Object.entries(value).filter(([, v]) => !!v).map(([k]) => k.replace(/_/g, ' '));
}

/** Extract a panel-layout display string from either the new `panel_layouts`
 *  dict or the legacy `panel_layout` string. */
function panelLayoutDisplay(p: ImporterProfile): string {
  if (p.panel_layout) return p.panel_layout;
  if (p.panel_layouts && typeof p.panel_layouts === 'object') {
    const keys = Object.keys(p.panel_layouts);
    if (keys.length) return keys.join(', ').replace(/_/g, ' ');
  }
  return '';
}

/** Flatten the content arrays of a `panel_layouts` dict
 *  (`{carton_top: ["logo", "upc"], carton_side: ["warnings"]}`) into a
 *  de-duplicated list of field names. Used to populate the Label
 *  Requirements tab for importers whose backend response doesn't carry an
 *  explicit `required_fields` list (i.e. anything onboarded before the
 *  localStorage cache was added). */
function deriveFieldsFromPanelLayouts(layouts: Record<string, unknown> | null | undefined): string[] {
  if (!layouts || typeof layouts !== 'object') return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of Object.values(layouts)) {
    if (!Array.isArray(value)) continue;
    for (const item of value) {
      if (typeof item !== 'string') continue;
      const pretty = item.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      if (!seen.has(pretty)) {
        seen.add(pretty);
        out.push(pretty);
      }
    }
  }
  return out;
}

interface ImporterOrder {
  id: string;
  po_number: string;
  state: string;
  item_count: number;
  progress: number;
  created_at: string;
}

interface ImporterOrdersResponse {
  orders: ImporterOrder[];
  total: number;
}

interface ImporterDocument {
  id: string;
  doc_type: string;
  filename: string;
  size_bytes: number;
  version: number;
  uploaded_at: string;
}

interface ImporterDocumentsResponse {
  documents: ImporterDocument[];
}

/* ─── Types for local doc UI state ──────────────────────────────── */

interface DocFile {
  name: string;
  sizeMb: number;
  uploadedAt: string;
  version: number;
  uploading: boolean;
  progress: number;
}
type DocStore = Record<string, DocFile | null>;

/* ─── Static metadata ───────────────────────────────────────────── */

const DOC_META: Record<string, { label: string; desc: string; accept: string; formats: string; category: string }> = {
  po:                 { label: 'Purchase Order (PO)',           desc: "Importer's official purchase order for the shipment",          accept: '.pdf,.xlsx,.xls,.doc,.docx', formats: 'PDF, XLS, DOC',     category: 'Order Documents' },
  pi:                 { label: 'Proforma Invoice (PI)',         desc: 'Exporter proforma invoice with item prices & quantities',       accept: '.pdf,.xlsx,.xls',            formats: 'PDF, XLS',          category: 'Order Documents' },
  label_protocol:     { label: 'Label Protocol / Spec Sheet',  desc: 'Master specification: fields, layout, fonts, placements',       accept: '.pdf,.docx',                 formats: 'PDF, DOCX',         category: 'Label & Protocol' },
  warning_guidelines: { label: 'Warning Guidelines',           desc: 'Market-specific regulatory warning text & format rules',        accept: '.pdf,.docx,.xlsx',           formats: 'PDF, DOCX, XLS',    category: 'Label & Protocol' },
  warning_labels:     { label: 'Warning Label Templates',      desc: 'Final artwork for warning panels (Prop 65, CE, UKCA, etc.)',    accept: '.pdf,.ai,.eps,.zip',         formats: 'PDF, AI, EPS, ZIP', category: 'Label & Protocol' },
  logo:               { label: 'Brand Logo Files',             desc: 'Vector logo in all approved variants (primary, reverse, mono)', accept: '.ai,.eps,.svg,.zip',         formats: 'AI, EPS, SVG, ZIP', category: 'Brand Assets' },
  care_icons:         { label: 'Care Icons / Symbol Sheet',    desc: 'ISO 3758 textile care & handling symbol files',                 accept: '.ai,.eps,.svg,.pdf,.zip',    formats: 'AI, EPS, SVG, ZIP', category: 'Brand Assets' },
  brand_guide:        { label: 'Brand Style Guide',            desc: 'Colour palette, typography, clear-space, and usage rules',      accept: '.pdf,.ai,.zip',              formats: 'PDF, AI, ZIP',      category: 'Brand Assets' },
  msds:               { label: 'MSDS / Safety Data Sheet',     desc: 'Required for any products with hazardous materials',            accept: '.pdf,.doc,.docx',            formats: 'PDF, DOC',          category: 'Compliance' },
  prop65:             { label: 'Prop 65 Warning Template',     desc: 'California Prop 65 compliant warning text & artwork',           accept: '.pdf,.ai,.eps',              formats: 'PDF, AI, EPS',      category: 'Compliance' },
  factory_cert:       { label: 'Factory Compliance Certificate', desc: 'BSCI, SMETA, or equivalent social compliance audit',          accept: '.pdf',                       formats: 'PDF',               category: 'Compliance' },
  customs_code:       { label: 'Customs Commodity Codes',      desc: 'HS / HTS codes for every product line in this shipment',        accept: '.pdf,.xlsx,.csv',            formats: 'PDF, XLS, CSV',     category: 'Customs' },
};

const FALLBACK_DOC = (id: string): { label: string; desc: string; accept: string; formats: string; category: string } =>
  ({ label: id, desc: '', accept: '*', formats: 'Any', category: 'Other' });

const STATUS_COLORS: Record<string, string> = {
  active:     'bg-green-100 text-green-700 border-green-200',
  onboarding: 'bg-blue-100 text-blue-700 border-blue-200',
  invited:    'bg-yellow-100 text-yellow-700 border-yellow-200',
  inactive:   'bg-gray-100 text-gray-600 border-gray-200',
  paused:     'bg-gray-100 text-gray-600 border-gray-200',
};

/* ─── Helpers ───────────────────────────────────────────────────── */

const fmtSize = (mb: number) => mb < 1 ? `${Math.round(mb * 1000)} KB` : `${mb.toFixed(1)} MB`;
const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

/* ─── DocCard ───────────────────────────────────────────────────── */

function DocCard({
  docId,
  importerId,
  file,
  onUploadComplete,
  onDelete,
  onRequest,
}: {
  docId: string;
  importerId: string;
  file: DocFile | null;
  onUploadComplete: (docId: string, filename: string, sizeMb: number) => void;
  onDelete: (docId: string) => void;
  onRequest: (docId: string) => void;
}) {
  const meta = DOC_META[docId] ?? FALLBACK_DOC(docId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const { toast } = useToast();

  const trigger = () => inputRef.current?.click();

  const handleFiles = useCallback(async (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;

    setUploading(true);
    setUploadProgress(0);

    // Simulate progress while actual upload happens
    const iv = setInterval(() => {
      setUploadProgress(prev => Math.min(prev + Math.random() * 15 + 5, 90));
    }, 200);

    try {
      const formData = new FormData();
      formData.append('file', f);
      formData.append('doc_type', docId);
      await apiUpload(`/importers/${importerId}/onboarding/upload`, formData);
      clearInterval(iv);
      setUploadProgress(100);
      onUploadComplete(docId, f.name, f.size / (1024 * 1024));
      toast({ title: 'Upload complete', description: f.name });
    } catch (e: any) {
      clearInterval(iv);
      toast({ title: 'Upload failed', description: e.message || 'Could not upload file', variant: 'destructive' });
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  }, [docId, importerId, onUploadComplete, toast]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  if (uploading) {
    return (
      <div className="border rounded-xl p-5 bg-card space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <FileText className="w-5 h-5 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm truncate">{meta.label}</p>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">Uploading...</p>
          </div>
          <Badge variant="outline" className="text-xs text-blue-600 border-blue-300 shrink-0">Uploading...</Badge>
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Uploading</span>
            <span className="font-mono">{Math.round(uploadProgress)}%</span>
          </div>
          <Progress value={uploadProgress} className="h-1.5" />
        </div>
      </div>
    );
  }

  if (file) {
    return (
      <div className="border rounded-xl bg-card overflow-hidden">
        <div className="p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center shrink-0">
            <FileType2 className="w-5 h-5 text-green-600" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-medium text-sm truncate">{meta.label}</p>
              <Badge variant="secondary" className="text-xs shrink-0">v{file.version}</Badge>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
              <span className="truncate">{file.name}</span>
              <span>·</span>
              <span className="shrink-0">{fmtSize(file.sizeMb)}</span>
              <span>·</span>
              <span className="shrink-0">{fmtDate(file.uploadedAt)}</span>
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => toast({ title: 'Downloading', description: file.name })}
            >
              <Download className="w-3.5 h-3.5" />
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="ghost"><MoreHorizontal className="w-3.5 h-3.5" /></Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => toast({ title: 'Previewing', description: file.name })}>
                  <Eye className="w-3.5 h-3.5 mr-2" /> Preview
                </DropdownMenuItem>
                <DropdownMenuItem onClick={trigger}>
                  <RefreshCw className="w-3.5 h-3.5 mr-2" /> Replace file
                </DropdownMenuItem>
                <DropdownMenuItem className="text-destructive" onClick={() => onDelete(docId)}>
                  <Trash2 className="w-3.5 h-3.5 mr-2" /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <div className="px-4 pb-3 flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
          <span className="text-xs text-green-700">Received and verified</span>
        </div>
        <input ref={inputRef} type="file" accept={meta.accept} className="hidden" onChange={e => handleFiles(e.target.files)} />
      </div>
    );
  }

  /* Empty / pending state */
  return (
    <div className="border rounded-xl bg-card overflow-hidden">
      <div className="p-4 pb-3 flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center shrink-0">
          <File className="w-5 h-5 text-muted-foreground" />
        </div>
        <div className="flex-1">
          <p className="font-medium text-sm">{meta.label}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{meta.desc}</p>
        </div>
        <Badge variant="outline" className="text-xs text-yellow-600 border-yellow-300 shrink-0">
          <Clock className="w-3 h-3 mr-1" />Pending
        </Badge>
      </div>

      <div
        className={`mx-4 mb-4 border-2 border-dashed rounded-lg p-5 transition-colors cursor-pointer ${
          dragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/20 hover:border-primary/50 hover:bg-muted/40'
        }`}
        onClick={trigger}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <div className="flex flex-col items-center gap-2 text-center">
          <Upload className={`w-6 h-6 ${dragOver ? 'text-primary' : 'text-muted-foreground/50'}`} />
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              Drag & drop or <span className="text-primary underline underline-offset-2">browse</span>
            </p>
            <p className="text-[11px] text-muted-foreground/60 mt-0.5">{meta.formats} · Max 25 MB</p>
          </div>
        </div>
      </div>

      <div className="px-4 pb-4 flex gap-2">
        <Button size="sm" variant="outline" className="flex-1" onClick={trigger}>
          <Upload className="w-3.5 h-3.5 mr-1.5" /> Upload File
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onRequest(docId)}>
          <Send className="w-3.5 h-3.5 mr-1.5" /> Request from Buyer
        </Button>
      </div>

      <input ref={inputRef} type="file" accept={meta.accept} className="hidden" onChange={e => handleFiles(e.target.files)} />
    </div>
  );
}

/* ─── Profile loading skeleton ──────────────────────────────────── */

function ProfileSkeleton() {
  return (
    <div className="flex flex-col h-[calc(100vh-56px)]">
      <div className="border-b px-6 py-5 bg-background shrink-0">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <Skeleton className="w-12 h-12 rounded-xl" />
            <div className="space-y-2">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-3 w-64" />
            </div>
          </div>
        </div>
        <div className="grid grid-cols-5 gap-4 mt-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      </div>
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    </div>
  );
}

/* ─── Main component ────────────────────────────────────────────── */

export default function ImporterDetail() {
  const [, params] = useRoute('/importers/:id');
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const importerId = params?.id || '';

  /* ── Profile state ── */
  const [importer, setImporter] = useState<ImporterProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);

  /* ── Orders state ── */
  const [importerOrders, setImporterOrders] = useState<ImporterOrder[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState<string | null>(null);

  /* ── Documents state ── */
  const [docs, setDocs] = useState<DocStore>({});
  const [docsLoaded, setDocsLoaded] = useState(false);

  /* ── Onboarding-session state (for importers that were uploaded-to
     but never ran `finalize`) ── */
  const [onboardingSession, setOnboardingSession] = useState<{
    status: string;
    extracted_values: Record<string, unknown>;
    agents: Record<string, { status: string; [k: string]: unknown }>;
  } | null>(null);

  /* ── Edit mode state ── */
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    name: '',
    panel_layout: '',
    barcode_placement: '',
    brand_treatment: '',
    handling_symbol_rules: '',
    notes: '',
    // Onboarding-form fields the backend doesn't persist yet. Captured here
    // so Save can seed them into the localStorage cache that `fetchProfile`
    // reads back on reload.
    buyer_contact: '',
    buyer_email: '',
    units: '',
    countries: '',
    required_fields: '',
  });
  const [saving, setSaving] = useState(false);

  /* ── Delete state ── */
  const [deleting, setDeleting] = useState(false);

  /* ── Fetch profile ──
   *
   * Adapter layer: the backend's ImporterProfile response (see
   * labelforge/contracts/models.py) returns `importer_id` not `id`, and
   * currently omits most of the onboarding form data (buyer contact,
   * countries, units, barcode placement, required fields, doc requirements,
   * label languages, notes). Until the schema catches up, we hydrate those
   * fields from localStorage written by the onboarding finalize step. See
   * `onboarding-importer.tsx` → `handleFinalize`.
   */
  const fetchProfile = useCallback(async () => {
    if (!importerId) return;
    setProfileLoading(true);
    setProfileError(null);
    try {
      const raw = await apiGet<Record<string, unknown>>(`/importers/${importerId}`);

      let cached: Record<string, unknown> = {};
      try {
        const s = localStorage.getItem(`labelforge:onboarding:${importerId}`);
        if (s) cached = JSON.parse(s) ?? {};
      } catch {
        /* ignore */
      }

      const data: ImporterProfile = {
        id: (raw.id as string) ?? (raw.importer_id as string) ?? importerId,
        importer_id: raw.importer_id as string | undefined,
        name: (raw.name as string) ?? (cached.companyName as string) ?? '',
        code: (raw.code as string) ?? '',
        status: (raw.status as string) ?? 'active',
        countries: (raw.countries as string[]) ?? (cached.countries as string[]) ?? [],
        profile_version: (raw.version as number) ?? (raw.profile_version as number) ?? 0,
        onboarding_progress: (raw.onboarding_progress as number) ?? 100,
        orders_mtd: (raw.orders_mtd as number) ?? 0,
        open_hitl: (raw.open_hitl as number) ?? 0,
        buyer_contact: (raw.buyer_contact as string) ?? (cached.buyerContact as string) ?? '',
        buyer_email: (raw.buyer_email as string) ?? (cached.buyerEmail as string) ?? '',
        portal_token: (raw.portal_token as string) ?? '',
        since: (raw.since as string) ?? (cached.savedAt as string) ?? '',
        label_languages: (raw.label_languages as string[]) ?? (cached.labelLang as string[]) ?? [],
        units: (raw.units as string) ?? (cached.units as string) ?? '',
        barcode_placement: (raw.barcode_placement as string) ?? (cached.barcodePlacement as string) ?? '',
        panel_layout: (raw.panel_layout as string) ?? (cached.panelLayout as string) ?? null,
        panel_layouts: (raw.panel_layouts as Record<string, unknown>) ?? null,
        brand_treatment: (raw.brand_treatment as Record<string, unknown>) ?? null,
        handling_symbol_rules:
          (raw.handling_symbol_rules as Record<string, boolean>) ??
          (cached.handlingSymbols as string[]) ??
          null,
        required_fields:
          (raw.required_fields as string[]) ??
          (cached.requiredFields as string[]) ??
          // Last resort: pull field names out of the agent-extracted panel
          // layout content so importers onboarded before the localStorage
          // cache existed still have something to show.
          deriveFieldsFromPanelLayouts(raw.panel_layouts as Record<string, unknown> | null) ??
          [],
        doc_requirements: (raw.doc_requirements as string[]) ?? (cached.docRequirements as string[]) ?? [],
        notes: (raw.notes as string) ?? (cached.notes as string) ?? '',
      };
      setImporter(data);
    } catch (e: any) {
      setProfileError(e.message || 'Failed to load importer');
    } finally {
      setProfileLoading(false);
    }
  }, [importerId]);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  /* ── Fetch orders (on tab switch or mount) ── */
  const fetchOrders = useCallback(async () => {
    if (!importerId) return;
    setOrdersLoading(true);
    setOrdersError(null);
    try {
      const data = await apiGet<ImporterOrdersResponse>(`/importers/${importerId}/orders`);
      setImporterOrders(data.orders);
    } catch (e: any) {
      setOrdersError(e.message || 'Failed to load orders');
    } finally {
      setOrdersLoading(false);
    }
  }, [importerId]);

  /* ── Fetch documents from API and seed DocStore ── */
  const fetchDocuments = useCallback(async () => {
    if (!importerId) return;
    try {
      const data = await apiGet<ImporterDocumentsResponse>(`/importers/${importerId}/documents`);
      const store: DocStore = {};
      // Initialize all doc requirements as null
      if (importer?.doc_requirements) {
        importer.doc_requirements.forEach(d => { store[d] = null; });
      }
      // Fill in received documents
      data.documents.forEach(doc => {
        store[doc.doc_type] = {
          name: doc.filename,
          sizeMb: doc.size_bytes / (1024 * 1024),
          uploadedAt: doc.uploaded_at,
          version: doc.version,
          uploading: false,
          progress: 100,
        };
      });
      setDocs(store);
      setDocsLoaded(true);
    } catch {
      // If documents endpoint fails, seed empty store from profile
      if (importer?.doc_requirements) {
        const store: DocStore = {};
        importer.doc_requirements.forEach(d => { store[d] = null; });
        setDocs(store);
      }
      setDocsLoaded(true);
    }
  }, [importerId, importer]);

  /* Load documents once profile is available */
  useEffect(() => {
    if (importer && !docsLoaded) {
      fetchDocuments();
    }
  }, [importer, docsLoaded, fetchDocuments]);

  /* ── Fetch onboarding session (if any) ─────────────────────────────
     For importers whose operators uploaded files and ran the extraction
     agents but never clicked "Finalize", the ImporterProfile row is null
     and the Overview would otherwise look empty. We render a banner +
     the extracted warnings/checklist summary instead. */
  const fetchOnboardingSession = useCallback(async () => {
    if (!importerId) return;
    try {
      const data = await apiGet<{
        status: string;
        extracted_values: Record<string, unknown>;
        agents: Record<string, { status: string }>;
      }>(`/importers/${importerId}/onboarding/extraction`);
      setOnboardingSession({
        status: data.status,
        extracted_values: data.extracted_values ?? {},
        agents: data.agents ?? {},
      });
    } catch {
      // 404 → no session yet; silent, the banner simply won't render.
      setOnboardingSession(null);
    }
  }, [importerId]);

  useEffect(() => {
    if (importer) fetchOnboardingSession();
  }, [importer, fetchOnboardingSession]);

  /* ── Upload complete handler ── */
  const handleUploadComplete = useCallback((docId: string, filename: string, sizeMb: number) => {
    setDocs(prev => ({
      ...prev,
      [docId]: {
        name: filename,
        sizeMb,
        uploadedAt: new Date().toISOString(),
        version: (prev[docId]?.version ?? 0) + 1,
        uploading: false,
        progress: 100,
      },
    }));
  }, []);

  const handleDeleteDoc = useCallback((docId: string) => {
    setDocs(prev => ({ ...prev, [docId]: null }));
    toast({ title: 'Document removed', variant: 'destructive' });
  }, [toast]);

  const handleRequest = useCallback((docId: string) => {
    const meta = DOC_META[docId] ?? FALLBACK_DOC(docId);
    toast({ title: 'Request sent', description: `${meta.label} request emailed to ${importer?.buyer_email ?? 'buyer'}.` });
  }, [importer, toast]);

  /* ── Edit mode handlers ── */
  const enterEditMode = useCallback(() => {
    if (!importer) return;
    setEditForm({
      name: importer.name,
      panel_layout: panelLayoutDisplay(importer),
      barcode_placement: importer.barcode_placement ?? '',
      // The dict shape doesn't round-trip cleanly through a single text input,
      // so surface it to the editor as the same human-readable summary shown
      // on the detail page. Saving replaces the stored value with whatever the
      // user types — the backend accepts either a string or a dict here.
      brand_treatment: formatProfileDict(importer.brand_treatment),
      handling_symbol_rules: handlingSymbolList(importer.handling_symbol_rules).join(', '),
      notes: importer.notes ?? '',
      buyer_contact: importer.buyer_contact ?? '',
      buyer_email: importer.buyer_email ?? '',
      units: importer.units ?? '',
      countries: (importer.countries ?? []).join(', '),
      required_fields: (importer.required_fields ?? []).join(', '),
    });
    setEditing(true);
  }, [importer]);

  const cancelEdit = () => setEditing(false);

  const saveEdit = useCallback(async () => {
    if (!importerId) return;
    setSaving(true);
    try {
      // Backend ImporterUpdateRequest only accepts dict-shaped values for
      // brand_treatment / panel_layouts / handling_symbol_rules — sending
      // raw strings or arrays returns 422. Coerce here. Fields the backend
      // doesn't model at all (barcode_placement, notes, panel_layout
      // singular) are persisted via the localStorage cache below.
      const symbolList = editForm.handling_symbol_rules
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const handlingDict: Record<string, boolean> = symbolList.reduce(
        (acc, s) => {
          acc[s] = true;
          return acc;
        },
        {} as Record<string, boolean>,
      );

      // Preserve existing dict shape when the user hasn't changed it; only
      // fall back to a synthetic wrapper when there's no prior structure.
      const prevBrand = importer?.brand_treatment;
      const summary = formatProfileDict(prevBrand);
      const brandDict: Record<string, unknown> =
        typeof prevBrand === 'object' && prevBrand !== null && editForm.brand_treatment === summary
          ? (prevBrand as Record<string, unknown>)
          : { description: editForm.brand_treatment };

      const prevLayouts = importer?.panel_layouts;
      const prevLayoutDisplay = panelLayoutDisplay(importer ?? ({} as ImporterProfile));
      const layoutsDict: Record<string, unknown> =
        prevLayouts && typeof prevLayouts === 'object' && editForm.panel_layout === prevLayoutDisplay
          ? prevLayouts
          : (editForm.panel_layout ? { [editForm.panel_layout]: { selected: true } } : {});

      const body: Record<string, unknown> = {
        name: editForm.name,
        brand_treatment: brandDict,
        panel_layouts: layoutsDict,
        handling_symbol_rules: handlingDict,
      };
      await apiPut<Record<string, unknown>>(`/importers/${importerId}`, body);

      // Keep cached onboarding metadata in sync with what the user just
      // edited. The backend response drops fields like panel_layout /
      // barcode_placement / notes, so setImporter(raw) would blank them —
      // re-run the adapter via fetchProfile so localStorage fills the gaps.
      try {
        const key = `labelforge:onboarding:${importerId}`;
        const prev = JSON.parse(localStorage.getItem(key) || '{}');
        const splitList = (s: string) =>
          s.split(',').map((x) => x.trim()).filter(Boolean);
        localStorage.setItem(
          key,
          JSON.stringify({
            ...prev,
            companyName: editForm.name,
            panelLayout: editForm.panel_layout,
            barcodePlacement: editForm.barcode_placement,
            // Cache as the same string[] shape the onboarding flow writes,
            // so the fetchProfile adapter can re-hydrate it cleanly.
            handlingSymbols: symbolList,
            notes: editForm.notes,
            buyerContact: editForm.buyer_contact,
            buyerEmail: editForm.buyer_email,
            units: editForm.units,
            countries: splitList(editForm.countries),
            requiredFields: splitList(editForm.required_fields),
            savedAt: prev.savedAt ?? new Date().toISOString(),
          }),
        );
      } catch {
        /* ignore */
      }

      await fetchProfile();
      setEditing(false);
      toast({ title: 'Profile updated', description: 'Importer profile saved successfully.' });
    } catch (e: any) {
      toast({ title: 'Update failed', description: e.message || 'Could not save changes', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  }, [importerId, editForm, toast, fetchProfile]);

  /* ── Delete handler ── */
  const handleDeleteImporter = useCallback(async () => {
    if (!importerId) return;
    setDeleting(true);
    try {
      await apiDelete(`/importers/${importerId}`);
      toast({ title: 'Importer deleted', description: 'The importer has been removed.' });
      setLocation('/importers');
    } catch (e: any) {
      toast({ title: 'Delete failed', description: e.message || 'Could not delete importer', variant: 'destructive' });
    } finally {
      setDeleting(false);
    }
  }, [importerId, toast, setLocation]);

  /* ── Ad-hoc document types ── */
  const [showAdHoc, setShowAdHoc] = useState(false);
  const [adHocDocs, setAdHocDocs] = useState<string[]>([]);

  const addAdHoc = (id: string) => {
    setAdHocDocs(prev => [...prev, id]);
    setDocs(prev => ({ ...prev, [id]: null }));
    setShowAdHoc(false);
  };

  const AD_HOC_TYPES = Object.keys(DOC_META).filter(k => !(importer?.doc_requirements ?? []).includes(k));

  /* ── Loading state ── */
  if (profileLoading) {
    return <ProfileSkeleton />;
  }

  /* ── Error / not found ── */
  if (profileError || !importer) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
        <AlertCircle className="w-8 h-8 mb-3" />
        <p>{profileError || 'Importer not found.'}</p>
        <Button variant="link" onClick={() => setLocation('/importers')}>Back to Importers</Button>
      </div>
    );
  }

  // Union required slots, ad-hoc slots, *and* any doc_type returned from
  // ``/documents``. Without the third source, importers created outside the
  // onboarding wizard (empty ``doc_requirements``) would render zero tiles
  // even though the API has files attached — the exact symptom reported.
  const attachedDocTypes = Object.keys(docs).filter(
    (k) => docs[k] && !docs[k]?.uploading,
  );
  const allDocIds = Array.from(
    new Set<string>([
      ...(importer.doc_requirements ?? []),
      ...adHocDocs,
      ...attachedDocTypes,
    ]),
  );
  const receivedCount = allDocIds.filter(d => docs[d] && !docs[d]?.uploading).length;
  const pendingCount = allDocIds.filter(d => !docs[d] || docs[d]?.uploading).length;

  return (
    <div className="flex flex-col h-[calc(100vh-56px)]">
      {/* Page header */}
      <div className="border-b px-6 py-5 bg-background shrink-0">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <Building2 className="w-6 h-6 text-primary" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold">{importer.name}</h1>
                {importer.code && (
                  <span className="text-xs font-mono text-muted-foreground">{importer.code}</span>
                )}
                <Badge variant="outline" className={`text-xs ${STATUS_COLORS[importer.status] ?? ''}`}>
                  {importer.status}
                </Badge>
                {importer.profile_version && (
                  <Badge variant="secondary" className="text-xs">v{importer.profile_version}</Badge>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                <span className="flex items-center gap-1"><Globe className="w-3 h-3" />{importer.countries?.join(', ')}</span>
                <span className="flex items-center gap-1"><User className="w-3 h-3" />{importer.buyer_contact}</span>
                <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{importer.buyer_email}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {importer.portal_token && (
              <Button variant="outline" size="sm" onClick={() => window.open(`/portal/importer/${importer.portal_token}`, '_blank')}>
                <ExternalLink className="w-3.5 h-3.5 mr-1.5" /> Portal
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={enterEditMode}>
              <Settings className="w-3.5 h-3.5 mr-1.5" /> Edit
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="text-destructive border-destructive/30 hover:bg-destructive/10">
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete {importer.name}?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will soft-delete the importer and all associated data. This action cannot be easily undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleDeleteImporter}
                    disabled={deleting}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    {deleting ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Trash2 className="w-4 h-4 mr-1.5" />}
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>

        <div className="grid grid-cols-5 gap-4 mt-5">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Onboarding</p>
            <div className="flex items-center gap-2">
              <Progress value={importer.onboarding_progress ?? 0} className="h-1.5 flex-1" />
              <span className="text-xs font-mono tabular-nums font-semibold">{importer.onboarding_progress ?? 0}%</span>
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Orders MTD</p>
            <p className="text-lg font-bold font-mono tabular-nums mt-0.5">{importer.orders_mtd ?? 0}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Open HiTL</p>
            <p className={`text-lg font-bold font-mono tabular-nums mt-0.5 ${(importer.open_hitl ?? 0) > 0 ? 'text-orange-600' : ''}`}>
              {importer.open_hitl ?? 0}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Units</p>
            <p className="text-sm font-medium mt-0.5 capitalize">{importer.units ?? '-'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Partner Since</p>
            <p className="text-sm font-medium mt-0.5">
              {importer.since ? new Date(importer.since).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '-'}
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="flex-1 flex flex-col overflow-hidden">
        <div className="px-6 pt-3 border-b bg-card shrink-0">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="requirements">Label Requirements</TabsTrigger>
            <TabsTrigger value="documents">
              Documents
              {pendingCount > 0 && (
                <span className="ml-1.5 bg-yellow-500 text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center font-bold">
                  {pendingCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="orders" onClick={() => { if (importerOrders.length === 0 && !ordersLoading) fetchOrders(); }}>
              Orders
            </TabsTrigger>
          </TabsList>
        </div>

        <div className="flex-1 overflow-auto bg-background">
          {/* ── Overview ── */}
          <TabsContent value="overview" className="m-0 p-6 space-y-5">
            {/* Onboarding-session banner — only when the agents have run
                but finalize was never clicked. Shows a quick summary of the
                extracted values + a CTA back to the wizard. */}
            {onboardingSession &&
              onboardingSession.status !== 'completed' && (
                <div className="border border-amber-200 bg-amber-50 rounded-xl p-4 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-amber-900 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4" /> Onboarding in review
                      </h3>
                      <p className="text-xs text-amber-800 mt-0.5">
                        Agents extracted data from the uploaded documents. Review and finalize to promote these values to the importer profile.
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setLocation(`/onboarding/importer?importer_id=${importerId}`)}
                    >
                      Review &amp; finalize <ChevronRight className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                    {(['protocol', 'warnings', 'checklist'] as const).map((k) => {
                      const agent = onboardingSession.agents[k];
                      const status = agent?.status ?? 'pending';
                      const palette =
                        status === 'completed'
                          ? 'bg-green-100 text-green-800 border-green-200'
                          : status === 'running'
                          ? 'bg-blue-100 text-blue-800 border-blue-200'
                          : status === 'failed'
                          ? 'bg-red-100 text-red-800 border-red-200'
                          : 'bg-gray-100 text-gray-700 border-gray-200';
                      return (
                        <div key={k} className={`border rounded-md px-2 py-1.5 ${palette}`}>
                          <div className="font-semibold capitalize">{k}</div>
                          <div className="opacity-80">{status}</div>
                        </div>
                      );
                    })}
                  </div>
                  {(() => {
                    const ev = onboardingSession.extracted_values ?? {};
                    const warnings = (ev.warnings as any)?.labels as any[] | undefined;
                    const checklist =
                      ((ev.checklist as any)?.documents as any[] | undefined) ??
                      ((ev.checklist as any)?.items as any[] | undefined);
                    return (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                        {warnings && warnings.length > 0 && (
                          <div>
                            <p className="font-semibold text-amber-900 mb-1">
                              Warning labels ({warnings.length})
                            </p>
                            <ul className="space-y-0.5 list-disc list-inside text-amber-950">
                              {warnings.slice(0, 4).map((w, i) => (
                                <li key={i} className="truncate">
                                  <span className="font-mono">{w.label_code ?? '—'}</span>
                                  {w.text_en ? ` · ${String(w.text_en).slice(0, 64)}${w.text_en.length > 64 ? '…' : ''}` : ''}
                                </li>
                              ))}
                              {warnings.length > 4 && (
                                <li className="text-amber-700">+ {warnings.length - 4} more</li>
                              )}
                            </ul>
                          </div>
                        )}
                        {checklist && checklist.length > 0 && (
                          <div>
                            <p className="font-semibold text-amber-900 mb-1">
                              Checklist items ({checklist.length})
                            </p>
                            <ul className="space-y-0.5 list-disc list-inside text-amber-950">
                              {checklist.slice(0, 4).map((c, i) => (
                                <li key={i} className="truncate">
                                  {String(c.name ?? c.label ?? c.text ?? JSON.stringify(c)).slice(0, 80)}
                                </li>
                              ))}
                              {checklist.length > 4 && (
                                <li className="text-amber-700">+ {checklist.length - 4} more</li>
                              )}
                            </ul>
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}

            {/* Edit mode panel */}
            {editing && (
              <div className="border rounded-xl p-5 space-y-4 bg-card">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold flex items-center gap-2"><Settings className="w-4 h-4" /> Edit Profile</h3>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="ghost" onClick={cancelEdit} disabled={saving}>
                      <X className="w-3.5 h-3.5 mr-1" /> Cancel
                    </Button>
                    <Button size="sm" onClick={saveEdit} disabled={saving}>
                      {saving ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Save className="w-3.5 h-3.5 mr-1" />}
                      Save Changes
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Name</label>
                    <Input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Panel Layout</label>
                    <Input value={editForm.panel_layout} onChange={e => setEditForm(f => ({ ...f, panel_layout: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Barcode Placement</label>
                    <Input value={editForm.barcode_placement} onChange={e => setEditForm(f => ({ ...f, barcode_placement: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Brand Treatment</label>
                    <Input value={editForm.brand_treatment} onChange={e => setEditForm(f => ({ ...f, brand_treatment: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Handling Symbol Rules (comma-separated)</label>
                    <Input value={editForm.handling_symbol_rules} onChange={e => setEditForm(f => ({ ...f, handling_symbol_rules: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Notes</label>
                    <Input value={editForm.notes} onChange={e => setEditForm(f => ({ ...f, notes: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Buyer Contact</label>
                    <Input value={editForm.buyer_contact} onChange={e => setEditForm(f => ({ ...f, buyer_contact: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Buyer Email</label>
                    <Input value={editForm.buyer_email} onChange={e => setEditForm(f => ({ ...f, buyer_email: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Units</label>
                    <Input value={editForm.units} placeholder="imperial | metric | both" onChange={e => setEditForm(f => ({ ...f, units: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Markets (comma-separated)</label>
                    <Input value={editForm.countries} onChange={e => setEditForm(f => ({ ...f, countries: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5 col-span-2">
                    <label className="text-xs font-medium text-muted-foreground">Required Fields (comma-separated)</label>
                    <Input value={editForm.required_fields} onChange={e => setEditForm(f => ({ ...f, required_fields: e.target.value }))} />
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-5">
              <div className="border rounded-xl p-5 space-y-3">
                <h3 className="text-sm font-semibold flex items-center gap-2"><Tag className="w-4 h-4" /> Label Specification</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Panel Layout</span>
                    <span className="font-medium">{panelLayoutDisplay(importer) || '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Barcode Placement</span>
                    <span className="font-medium">{importer.barcode_placement || '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Brand Treatment</span>
                    <span className="font-medium">{formatProfileDict(importer.brand_treatment) || '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Label Language</span>
                    <div className="flex gap-1">
                      {(importer.label_languages ?? []).map((l) => (
                        <Badge key={l} variant="secondary" className="text-xs uppercase">{l}</Badge>
                      ))}
                    </div>
                  </div>
                </div>
                {(() => {
                  const symbols = handlingSymbolList(importer.handling_symbol_rules);
                  if (!symbols.length) return null;
                  return (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1.5">Handling Symbols</p>
                      <div className="flex flex-wrap gap-1.5">
                        {symbols.map((s) => (
                          <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </div>

              <div className="border rounded-xl p-5 space-y-3">
                <h3 className="text-sm font-semibold flex items-center gap-2"><FileText className="w-4 h-4" /> Document Status</h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="flex flex-col items-center p-3 rounded-lg bg-green-50 border border-green-100">
                    <span className="text-2xl font-bold font-mono text-green-700">{receivedCount}</span>
                    <span className="text-xs text-green-600 mt-0.5">Received</span>
                  </div>
                  <div className="flex flex-col items-center p-3 rounded-lg bg-yellow-50 border border-yellow-100">
                    <span className="text-2xl font-bold font-mono text-yellow-700">{pendingCount}</span>
                    <span className="text-xs text-yellow-600 mt-0.5">Pending</span>
                  </div>
                </div>
                <div className="space-y-1.5">
                  {allDocIds.map((d) => {
                    const f = docs[d];
                    const meta = DOC_META[d] ?? FALLBACK_DOC(d);
                    return (
                      <div key={d} className="flex items-center gap-2 text-xs">
                        {f && !f.uploading ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
                        ) : (
                          <Clock className="w-3.5 h-3.5 text-yellow-500 shrink-0" />
                        )}
                        <span className={f && !f.uploading ? 'text-foreground' : 'text-muted-foreground truncate'}>
                          {meta.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {importer.notes && (
              <div className="border rounded-xl p-5">
                <h3 className="text-sm font-semibold mb-2">Notes</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{importer.notes}</p>
              </div>
            )}

            {importer.status === 'invited' && (
              <div className="flex items-start gap-3 border border-yellow-200 bg-yellow-50 rounded-xl p-4">
                <AlertCircle className="w-4 h-4 text-yellow-600 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-yellow-800">Awaiting buyer portal completion</p>
                  <p className="text-xs text-yellow-700 mt-0.5">
                    An invite was sent to {importer.buyer_email}. The importer profile will be activated once they complete the portal flow.
                  </p>
                </div>
              </div>
            )}
          </TabsContent>

          {/* ── Requirements ── */}
          <TabsContent value="requirements" className="m-0 p-6">
            <div className="max-w-lg space-y-5">
              <div>
                <h3 className="font-semibold mb-3 flex items-center gap-2"><Tag className="w-4 h-4" /> Required Label Fields</h3>
                {(importer.required_fields ?? []).length > 0 ? (
                  <div className="space-y-1">
                    {importer.required_fields.map((f) => (
                      <div key={f} className="flex items-center gap-3 py-2 border-b last:border-0 text-sm">
                        <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                        {f}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No required fields configured yet.</p>
                )}
              </div>
            </div>
          </TabsContent>

          {/* ── Documents ── */}
          <TabsContent value="documents" className="m-0 p-6">
            <div className="max-w-2xl space-y-5">
              {/* Header */}
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold flex items-center gap-2">
                    <FilePlus className="w-4 h-4" /> Document Vault
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {receivedCount} of {allDocIds.length} required documents received
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      allDocIds.filter(d => !docs[d]).forEach(d => handleRequest(d));
                    }}
                    disabled={pendingCount === 0}
                  >
                    <Send className="w-3.5 h-3.5 mr-1.5" /> Request All Pending
                  </Button>
                </div>
              </div>

              {/* Progress bar */}
              {allDocIds.length > 0 && (
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Document completion</span>
                    <span className="font-mono">{Math.round((receivedCount / allDocIds.length) * 100)}%</span>
                  </div>
                  <Progress value={(receivedCount / allDocIds.length) * 100} className="h-2" />
                </div>
              )}

              {/* Doc cards — grouped by category */}
              {allDocIds.length > 0 ? (
                <div className="space-y-6">
                  {(() => {
                    const CATEGORY_ORDER = ['Order Documents', 'Label & Protocol', 'Brand Assets', 'Compliance', 'Customs', 'Other'];
                    const grouped: Record<string, string[]> = {};
                    allDocIds.forEach(docId => {
                      const cat = (DOC_META[docId] ?? FALLBACK_DOC(docId)).category;
                      if (!grouped[cat]) grouped[cat] = [];
                      grouped[cat].push(docId);
                    });
                    return CATEGORY_ORDER.filter(c => grouped[c]?.length).map(category => (
                      <div key={category}>
                        <div className="text-[11px] font-bold text-muted-foreground/60 uppercase tracking-wider mb-3">{category}</div>
                        <div className="space-y-3">
                          {grouped[category].map(docId => (
                            <DocCard
                              key={docId}
                              docId={docId}
                              importerId={importerId}
                              file={docs[docId] ?? null}
                              onUploadComplete={handleUploadComplete}
                              onDelete={handleDeleteDoc}
                              onRequest={handleRequest}
                            />
                          ))}
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-40 border-2 border-dashed rounded-xl text-muted-foreground">
                  <FileText className="w-8 h-8 mb-2 opacity-30" />
                  <p className="text-sm">No document requirements configured.</p>
                  <p className="text-xs mt-1 opacity-70">Go to the onboarding wizard to set them up.</p>
                </div>
              )}

              {/* Add ad-hoc document */}
              <div className="pt-2">
                {!showAdHoc ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full border-dashed"
                    onClick={() => setShowAdHoc(true)}
                    disabled={AD_HOC_TYPES.filter(t => !adHocDocs.includes(t)).length === 0}
                  >
                    <Plus className="w-3.5 h-3.5 mr-2" /> Add Additional Document
                  </Button>
                ) : (
                  <div className="border rounded-xl p-4 space-y-2 bg-card">
                    <p className="text-sm font-medium">Select document type to add</p>
                    <div className="grid grid-cols-1 gap-1.5">
                      {AD_HOC_TYPES.filter(t => !adHocDocs.includes(t)).map(t => (
                        <button
                          key={t}
                          onClick={() => addAdHoc(t)}
                          className="flex items-center gap-3 text-left px-3 py-2.5 rounded-lg border hover:border-primary hover:bg-primary/5 transition-colors text-sm"
                        >
                          <File className="w-4 h-4 text-muted-foreground shrink-0" />
                          <div>
                            <div className="font-medium">{DOC_META[t].label}</div>
                            <div className="text-xs text-muted-foreground">{DOC_META[t].desc}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => setShowAdHoc(false)}>Cancel</Button>
                  </div>
                )}
              </div>
            </div>
          </TabsContent>

          {/* ── Orders ── */}
          <TabsContent value="orders" className="m-0 p-6">
            {ordersLoading ? (
              <div className="max-w-2xl space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            ) : ordersError ? (
              <div className="flex items-center gap-2 text-sm text-destructive">
                <AlertCircle className="w-4 h-4" />
                {ordersError}
                <Button variant="link" size="sm" onClick={fetchOrders}>Retry</Button>
              </div>
            ) : importerOrders.length > 0 ? (
              <div className="space-y-2 max-w-2xl">
                {importerOrders.map((o) => (
                  <div
                    key={o.id}
                    className="flex items-center gap-4 p-4 border rounded-lg bg-card hover:border-primary cursor-pointer transition-colors text-sm"
                    onClick={() => setLocation(`/orders/${o.id}`)}
                  >
                    <Package className="w-4 h-4 text-muted-foreground shrink-0" />
                    <div className="flex-1">
                      <div className="font-mono font-semibold">{o.po_number}</div>
                      <div className="text-xs text-muted-foreground">{o.item_count} items</div>
                    </div>
                    <Badge variant="outline" className="text-xs font-mono">{o.state}</Badge>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Progress value={o.progress ?? 0} className="w-16 h-1.5" />
                      {o.progress ?? 0}%
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-40 text-muted-foreground">
                <Layers className="w-8 h-8 mb-2 opacity-40" />
                <p className="text-sm">No orders yet for this importer.</p>
              </div>
            )}
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
