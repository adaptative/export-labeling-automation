import React, { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Search, Download, FileCode, FileText, Image, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import { useArtifacts, useArtifact, useArtifactProvenance } from '@/hooks/useArtifacts';
import { ProvenanceChain } from '@/components/ProvenanceChain';

const TYPE_ICONS: Record<string, React.ReactNode> = {
  die_cut_svg: <FileCode className="w-8 h-8 text-purple-400" />,
  compliance_report: <FileText className="w-8 h-8 text-blue-400" />,
  fused_item: <Image className="w-8 h-8 text-green-400" />,
};

const TYPE_LABELS: Record<string, string> = {
  die_cut_svg: 'Die-Cut SVG',
  compliance_report: 'Compliance Report',
  fused_item: 'Fused Item',
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

export default function Artifacts() {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showProvenance, setShowProvenance] = useState(false);

  const { data, isLoading } = useArtifacts({
    search: search || undefined,
    artifact_type: typeFilter !== 'all' ? typeFilter : undefined,
  });

  const { data: detail } = useArtifact(selectedId);
  const { data: provenanceData } = useArtifactProvenance(showProvenance ? selectedId : null);

  const artifacts = data?.artifacts ?? [];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Artifact Gallery</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} artifacts` : 'Generated assets and their provenance chains.'}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search hashes, IDs..." className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-44 h-9"><SelectValue placeholder="All types" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            <SelectItem value="die_cut_svg">Die-Cut SVG</SelectItem>
            <SelectItem value="compliance_report">Compliance Report</SelectItem>
            <SelectItem value="fused_item">Fused Item</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i}><CardContent className="p-4"><div className="h-40 animate-pulse bg-muted rounded" /></CardContent></Card>
          ))}
        </div>
      ) : artifacts.length === 0 ? (
        <div className="border rounded-md p-12 text-center text-muted-foreground bg-card">
          No artifacts match the current filters.
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {artifacts.map((art) => (
            <Card key={art.artifact_id} className="cursor-pointer hover:border-primary overflow-hidden transition-colors" onClick={() => { setSelectedId(art.artifact_id); setShowProvenance(false); }}>
              <div className="h-32 bg-muted flex items-center justify-center border-b">
                {TYPE_ICONS[art.artifact_type] || <FileText className="w-8 h-8 text-gray-400" />}
              </div>
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <div className="font-mono text-sm font-medium">{art.artifact_id}</div>
                  <Badge variant="outline" className="text-[10px]">{TYPE_LABELS[art.artifact_type] || art.artifact_type}</Badge>
                </div>
                <div className="text-xs text-muted-foreground font-mono truncate" title={art.content_hash}>
                  {art.content_hash.slice(0, 24)}...
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {new Date(art.created_at).toLocaleDateString()}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!selectedId} onOpenChange={(open) => { if (!open) { setSelectedId(null); setShowProvenance(false); } }}>
        <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {detail?.artifact_id}
              <Badge variant="outline">{TYPE_LABELS[detail?.artifact_type ?? ''] || detail?.artifact_type}</Badge>
            </DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-4">
              <div className="h-40 bg-muted rounded-lg flex items-center justify-center border">
                {TYPE_ICONS[detail.artifact_type] || <FileText className="w-12 h-12 text-gray-400" />}
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-muted-foreground">Type:</span> {TYPE_LABELS[detail.artifact_type] || detail.artifact_type}</div>
                <div><span className="text-muted-foreground">Size:</span> {formatBytes(detail.size_bytes)}</div>
                <div><span className="text-muted-foreground">MIME:</span> {detail.mime_type}</div>
                <div><span className="text-muted-foreground">Created:</span> {new Date(detail.created_at).toLocaleString()}</div>
                {detail.order_id && <div><span className="text-muted-foreground">Order:</span> <span className="text-primary">{detail.order_id}</span></div>}
                {detail.created_by && <div><span className="text-muted-foreground">Created by:</span> {detail.created_by}</div>}
              </div>

              <div>
                <span className="text-sm text-muted-foreground">Content Hash:</span>
                <p className="font-mono text-xs mt-0.5 break-all">{detail.content_hash}</p>
              </div>

              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setShowProvenance(!showProvenance)}>
                  <ExternalLink className="w-3.5 h-3.5 mr-1.5" />
                  {showProvenance ? 'Hide' : 'View'} Provenance
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <a href={`/api/v1/artifacts/${detail.artifact_id}/download`} target="_blank" rel="noopener noreferrer">
                    <Download className="w-3.5 h-3.5 mr-1.5" />
                    Download
                  </a>
                </Button>
              </div>

              {showProvenance && provenanceData && (
                <div className="border-t pt-4">
                  <h3 className="text-sm font-semibold mb-3">Provenance Chain</h3>
                  <ProvenanceChain steps={provenanceData.steps} />
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
