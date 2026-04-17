import React, { useState, useEffect } from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { FileText, Search, Filter, Loader2, Eye, RefreshCw } from 'lucide-react';
import { apiGet } from '@/api/authInterceptor';

interface DocumentItem {
  id: string;
  order_id: string;
  filename: string;
  doc_class: string;
  confidence?: number;
  size_bytes?: number;
  page_count?: number;
  uploaded_at: string;
  classification_status?: string;
  // Legacy fields from older API
  parsed?: boolean;
  storage_url?: string;
}

interface DocumentDetail extends DocumentItem {
  storage_key?: string;
  content_hash?: string | null;
}

const CLASS_LABELS: Record<string, string> = {
  PURCHASE_ORDER: 'Purchase Order',
  PROFORMA_INVOICE: 'Proforma Invoice',
  PROTOCOL: 'Protocol',
  WARNING_LABELS: 'Warning Labels',
  CHECKLIST: 'Checklist',
  UNKNOWN: 'Unknown',
};

const CLASS_BADGE_COLORS: Record<string, string> = {
  PURCHASE_ORDER: 'bg-blue-50 text-blue-700 border-blue-200',
  PROFORMA_INVOICE: 'bg-purple-50 text-purple-700 border-purple-200',
  PROTOCOL: 'bg-green-50 text-green-700 border-green-200',
  WARNING_LABELS: 'bg-amber-50 text-amber-700 border-amber-200',
  CHECKLIST: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  UNKNOWN: 'bg-gray-50 text-gray-500 border-gray-200',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function confidenceBadge(confidence?: number) {
  if (confidence == null) return <span className="text-muted-foreground">—</span>;
  if (confidence >= 0.9) {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-700 font-medium">
        {(confidence * 100).toFixed(0)}%
      </span>
    );
  }
  if (confidence >= 0.7) {
    return (
      <span className="inline-flex items-center gap-1 text-amber-600 font-medium">
        {(confidence * 100).toFixed(0)}%
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-red-600 font-medium">
      {confidence > 0 ? `${(confidence * 100).toFixed(0)}%` : '—'}
    </span>
  );
}

export default function Documents() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [classFilter, setClassFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (classFilter && classFilter !== 'all') params.set('doc_class', classFilter);
      if (statusFilter && statusFilter !== 'all') params.set('classification_status', statusFilter);
      const query = params.toString() ? `?${params.toString()}` : '';

      const data = await apiGet<{ documents: DocumentItem[]; total: number }>(`/documents${query}`);
      setDocuments(data.documents);
      setTotal(data.total);
    } catch {
      setDocuments([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [classFilter, statusFilter]);

  const openDetail = async (docId: string) => {
    try {
      const detail = await apiGet<DocumentDetail>(`/documents/${docId}`);
      setSelectedDoc(detail);
      setDetailOpen(true);
    } catch {
      // silently fail
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Documents Inbox</h1>
          <p className="text-sm text-muted-foreground">
            Cross-order document classifications and extractions.
            {!loading && <span className="ml-1 font-medium">{total} document{total !== 1 ? 's' : ''}</span>}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchDocuments} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <Select value={classFilter} onValueChange={setClassFilter}>
            <SelectTrigger className="h-8 w-[180px] text-xs">
              <SelectValue placeholder="All types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All types</SelectItem>
              <SelectItem value="PURCHASE_ORDER">Purchase Order</SelectItem>
              <SelectItem value="PROFORMA_INVOICE">Proforma Invoice</SelectItem>
              <SelectItem value="PROTOCOL">Protocol</SelectItem>
              <SelectItem value="WARNING_LABELS">Warning Labels</SelectItem>
              <SelectItem value="CHECKLIST">Checklist</SelectItem>
              <SelectItem value="UNKNOWN">Unknown</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="h-8 w-[160px] text-xs">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="classified">Classified</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Document</TableHead>
              <TableHead>Order</TableHead>
              <TableHead>Classification</TableHead>
              <TableHead className="text-center">Confidence</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-[60px]" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : documents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                  No documents found.
                </TableCell>
              </TableRow>
            ) : (
              documents.map((doc) => (
                <TableRow key={doc.id} className="cursor-pointer hover:bg-muted/50" onClick={() => openDetail(doc.id)}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-blue-600 shrink-0" />
                      <div>
                        <div className="text-sm font-medium">{doc.filename}</div>
                        <div className="text-xs text-muted-foreground font-mono">{doc.id}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{doc.order_id}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={`text-xs ${CLASS_BADGE_COLORS[doc.doc_class] || CLASS_BADGE_COLORS.UNKNOWN}`}
                    >
                      {CLASS_LABELS[doc.doc_class] || doc.doc_class}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-center tabular-nums">
                    {confidenceBadge(doc.confidence)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground tabular-nums">
                    {doc.size_bytes != null ? formatBytes(doc.size_bytes) : '—'}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={doc.classification_status === 'classified' ? 'default' : 'secondary'}
                      className="text-xs"
                    >
                      {doc.classification_status || (doc.parsed ? 'classified' : 'pending')}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); openDetail(doc.id); }}>
                      <Eye className="w-3.5 h-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Document detail dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              {selectedDoc?.filename || 'Document Detail'}
            </DialogTitle>
          </DialogHeader>
          {selectedDoc && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-muted-foreground">ID</span>
                  <p className="font-mono">{selectedDoc.id}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Order</span>
                  <p className="font-mono">{selectedDoc.order_id}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Classification</span>
                  <p>
                    <Badge variant="outline" className={`text-xs ${CLASS_BADGE_COLORS[selectedDoc.doc_class] || ''}`}>
                      {CLASS_LABELS[selectedDoc.doc_class] || selectedDoc.doc_class}
                    </Badge>
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Confidence</span>
                  <p>{confidenceBadge(selectedDoc.confidence)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Size</span>
                  <p>{selectedDoc.size_bytes != null ? formatBytes(selectedDoc.size_bytes) : '—'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Pages</span>
                  <p>{selectedDoc.page_count || '—'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Status</span>
                  <p>
                    <Badge variant={selectedDoc.classification_status === 'classified' ? 'default' : 'secondary'} className="text-xs">
                      {selectedDoc.classification_status}
                    </Badge>
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Uploaded</span>
                  <p>{new Date(selectedDoc.uploaded_at).toLocaleString()}</p>
                </div>
              </div>
              {selectedDoc.content_hash && (
                <div>
                  <span className="text-muted-foreground text-xs">Content Hash</span>
                  <p className="font-mono text-xs break-all">{selectedDoc.content_hash}</p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
