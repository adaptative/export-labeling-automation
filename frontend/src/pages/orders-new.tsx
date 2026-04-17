import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useLocation } from 'wouter';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Upload, FileText, FileSpreadsheet, X, CheckCircle2, AlertTriangle, ArrowLeft, Loader2, Zap,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { apiGet, apiPost, apiUpload } from '@/api/authInterceptor';

interface UploadedFile {
  id: string;
  file: File;
  name: string;
  sizeMb: number;
  detectedType: string;
  confidence: number;
  status: 'uploading' | 'classified' | 'low_confidence' | 'pending' | 'error';
  docId?: string;
}

interface ImporterOption {
  importer_id: string;
  name: string;
  code: string;
}

const DOC_TYPE_OPTIONS = [
  { value: 'PO', label: 'Purchase Order (PO)' },
  { value: 'PI', label: 'Proforma Invoice (PI)' },
  { value: 'PROTOCOL', label: 'Label Protocol' },
  { value: 'WARNING_LABELS', label: 'Warning Guidelines' },
  { value: 'CHECKLIST', label: 'QA Checklist' },
  { value: 'BRAND_GUIDE', label: 'Brand Guide' },
  { value: 'LOGO', label: 'Logo' },
  { value: 'CARE_ICONS', label: 'Care Icons' },
  { value: 'MSDS', label: 'Material Safety Data Sheet' },
  { value: 'CUSTOMS_CODE', label: 'HS Code / Customs' },
];

// Map backend doc_class to short display value
const CLASS_TO_SHORT: Record<string, string> = {
  PURCHASE_ORDER: 'PO',
  PROFORMA_INVOICE: 'PI',
  PROTOCOL: 'PROTOCOL',
  WARNING_LABELS: 'WARNING_LABELS',
  CHECKLIST: 'CHECKLIST',
  UNKNOWN: 'UNKNOWN',
};

export default function OrdersNew() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [dragActive, setDragActive] = useState(false);
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [importer, setImporter] = useState('');
  const [importers, setImporters] = useState<ImporterOption[]>([]);
  const [poReference, setPoReference] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load importers from API
  useEffect(() => {
    apiGet<{ importers: ImporterOption[]; total: number }>('/importers')
      .then((data) => {
        setImporters(data.importers);
      })
      .catch(() => {
        // Fallback importers if API not available
        setImporters([
          { importer_id: 'IMP-ACME', name: 'Sagebrook Home', code: 'ACME' },
          { importer_id: 'IMP-GLOBEX', name: 'Pier 1', code: 'GLOBEX' },
        ]);
      });
  }, []);

  const processFiles = useCallback(async (rawFiles: FileList | File[]) => {
    const newFiles: UploadedFile[] = Array.from(rawFiles).map((file, idx) => ({
      id: `upload-${Date.now()}-${idx}`,
      file,
      name: file.name,
      sizeMb: file.size / (1024 * 1024),
      detectedType: 'UNKNOWN',
      confidence: 0,
      status: 'pending' as const,
    }));

    setFiles(prev => [...prev, ...newFiles]);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  }, [processFiles]);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files);
      e.target.value = '';
    }
  }, [processFiles]);

  const removeFile = (id: string) => {
    setFiles(prev => prev.filter(f => f.id !== id));
  };

  const handleSubmit = async () => {
    if (!importer || files.length === 0) return;
    setSubmitting(true);

    try {
      // 1. Create the order
      const order = await apiPost<{ id: string; po_number: string }>('/orders', {
        importer_id: importer,
        po_reference: poReference || undefined,
        due_date: dueDate || undefined,
      });

      // 2. Upload each file to the order
      const uploadResults = await Promise.allSettled(
        files.map(async (f) => {
          const formData = new FormData();
          formData.append('file', f.file);

          const result = await apiUpload<{
            id: string;
            doc_class: string;
            confidence: number;
            classification_status: string;
          }>(`/orders/${order.id}/documents?order_id=${order.id}`, formData);

          // Update file state with classification result
          setFiles(prev =>
            prev.map(pf =>
              pf.id === f.id
                ? {
                    ...pf,
                    docId: result.id,
                    detectedType: CLASS_TO_SHORT[result.doc_class] || result.doc_class,
                    confidence: result.confidence,
                    status: result.confidence >= 0.9
                      ? 'classified'
                      : result.confidence >= 0.7
                        ? 'low_confidence'
                        : 'pending',
                  }
                : pf,
            ),
          );

          return result;
        }),
      );

      const succeeded = uploadResults.filter(r => r.status === 'fulfilled').length;
      const failed = uploadResults.filter(r => r.status === 'rejected').length;

      toast({
        title: 'Order created',
        description: `${order.po_number} created with ${succeeded} document${succeeded !== 1 ? 's' : ''}${failed > 0 ? ` (${failed} failed)` : ''}. Pipeline starting.`,
      });

      setLocation(`/orders/${order.id}`);
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to create order',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const fileIcon = (name: string) => {
    if (name.endsWith('.xlsx') || name.endsWith('.xls')) return <FileSpreadsheet className="w-4 h-4 text-green-600" />;
    return <FileText className="w-4 h-4 text-blue-600" />;
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => setLocation('/orders')}>
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">New Order</h1>
          <p className="text-sm text-muted-foreground">Upload PO, PI, and any supporting documents. The Intake Agent will auto-classify them.</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-2 space-y-6">
          <div
            className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors cursor-pointer
              ${dragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/30'}`}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={handleClick}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.xlsx,.xls,.png,.jpg,.jpeg"
              className="hidden"
              onChange={handleFileInput}
            />
            <Upload className={`w-10 h-10 mx-auto mb-3 ${dragActive ? 'text-primary' : 'text-muted-foreground'}`} />
            <p className="font-medium text-sm">
              {dragActive ? 'Drop files here...' : 'Drag & drop your PO, PI, and supporting files'}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              PDF, XLSX, PNG, JPG — up to 25 MB per file
            </p>
          </div>

          {files.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Zap className="w-4 h-4 text-primary" />
                    Documents
                  </CardTitle>
                  <Badge variant="outline" className="text-xs">
                    {files.length} file{files.length !== 1 ? 's' : ''}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/30">
                      <TableHead>File</TableHead>
                      <TableHead className="w-[180px]">Type</TableHead>
                      <TableHead className="w-[100px] text-center">Confidence</TableHead>
                      <TableHead className="w-[60px]" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {files.map(file => (
                      <TableRow key={file.id}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {fileIcon(file.name)}
                            <div>
                              <div className="text-sm font-medium">{file.name}</div>
                              <div className="text-xs text-muted-foreground tabular-nums">{file.sizeMb.toFixed(file.sizeMb < 0.1 ? 3 : 1)} MB</div>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          {file.status === 'pending' ? (
                            <span className="text-xs text-muted-foreground">Will classify on upload</span>
                          ) : (
                            <Select defaultValue={file.detectedType}>
                              <SelectTrigger className="h-8 text-xs">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {DOC_TYPE_OPTIONS.map(opt => (
                                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          {file.status === 'pending' ? (
                            <Badge variant="outline" className="text-xs text-muted-foreground">—</Badge>
                          ) : file.confidence >= 0.9 ? (
                            <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs gap-1">
                              <CheckCircle2 className="w-3 h-3" />
                              {(file.confidence * 100).toFixed(0)}%
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-xs gap-1">
                              <AlertTriangle className="w-3 h-3" />
                              {(file.confidence * 100).toFixed(0)}%
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => removeFile(file.id)} disabled={submitting}>
                            <X className="w-3.5 h-3.5" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Order Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-xs">Importer</Label>
                <Select value={importer} onValueChange={setImporter}>
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="Select importer..." />
                  </SelectTrigger>
                  <SelectContent>
                    {importers.map(imp => (
                      <SelectItem key={imp.importer_id} value={imp.importer_id}>
                        {imp.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">PO Reference (optional)</Label>
                <Input
                  placeholder="PO#25370"
                  className="h-9"
                  value={poReference}
                  onChange={(e) => setPoReference(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Due Date</Label>
                <Input
                  type="date"
                  className="h-9"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-muted/30">
            <CardContent className="pt-4">
              <h4 className="text-xs font-medium text-muted-foreground mb-2">What happens next?</h4>
              <ol className="text-xs text-muted-foreground space-y-1.5 list-decimal list-inside">
                <li>Intake Agent classifies your files</li>
                <li>PO Parser extracts line items</li>
                <li>PI Parser reads dimensions & weights</li>
                <li>Fusion Agent joins PO + PI data</li>
                <li>Compliance rules auto-applied</li>
                <li>Die-cuts & approval PDFs generated</li>
              </ol>
            </CardContent>
          </Card>

          <Button
            className="w-full"
            disabled={files.length === 0 || !importer || submitting}
            onClick={handleSubmit}
          >
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Creating order...
              </>
            ) : (
              <>
                <Upload className="w-4 h-4 mr-2" />
                Create Order & Start Pipeline
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
