import React, { useState } from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Search, Bot, User, Monitor, ChevronLeft, ChevronRight } from 'lucide-react';
import { useAuditLog, useAuditEntry, type AuditEntry } from '@/hooks/useAuditLog';

const ACTION_COLORS: Record<string, string> = {
  CREATE: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  GENERATE: 'bg-blue-50 text-blue-700 border-blue-200',
  CLASSIFY: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  VALIDATE: 'bg-violet-50 text-violet-700 border-violet-200',
  APPROVE: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  REJECT: 'bg-red-50 text-red-700 border-red-200',
  DELETE: 'bg-red-50 text-red-700 border-red-200',
  UPDATE: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  EXTRACT: 'bg-blue-50 text-blue-700 border-blue-200',
};

const ACTOR_ICON: Record<string, React.ReactNode> = {
  user: <User className="w-3 h-3" />,
  agent: <Bot className="w-3 h-3" />,
  system: <Monitor className="w-3 h-3" />,
};

const PAGE_SIZE = 20;

export default function Audit() {
  const [search, setSearch] = useState('');
  const [actorTypeFilter, setActorTypeFilter] = useState<string>('all');
  const [actionFilter, setActionFilter] = useState<string>('all');
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading } = useAuditLog({
    search: search || undefined,
    actor_type: actorTypeFilter !== 'all' ? actorTypeFilter : undefined,
    action: actionFilter !== 'all' ? actionFilter : undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const { data: selectedEntry } = useAuditEntry(selectedId);

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const entries = data?.entries ?? [];

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Audit Log</h1>
        <p className="text-sm text-muted-foreground">
          {total > 0 ? `Showing ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total} entries` : 'System-wide action history'}
        </p>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search actors, resources..."
            className="pl-8 h-9"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          />
        </div>
        <Select value={actorTypeFilter} onValueChange={(v) => { setActorTypeFilter(v); setPage(0); }}>
          <SelectTrigger className="w-36 h-9"><SelectValue placeholder="All actors" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All actors</SelectItem>
            <SelectItem value="user">Human</SelectItem>
            <SelectItem value="agent">Agent</SelectItem>
            <SelectItem value="system">System</SelectItem>
          </SelectContent>
        </Select>
        <Select value={actionFilter} onValueChange={(v) => { setActionFilter(v); setPage(0); }}>
          <SelectTrigger className="w-40 h-9"><SelectValue placeholder="All actions" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All actions</SelectItem>
            <SelectItem value="CREATE">CREATE</SelectItem>
            <SelectItem value="UPDATE">UPDATE</SelectItem>
            <SelectItem value="DELETE">DELETE</SelectItem>
            <SelectItem value="APPROVE">APPROVE</SelectItem>
            <SelectItem value="REJECT">REJECT</SelectItem>
            <SelectItem value="GENERATE">GENERATE</SelectItem>
            <SelectItem value="CLASSIFY">CLASSIFY</SelectItem>
            <SelectItem value="VALIDATE">VALIDATE</SelectItem>
            <SelectItem value="EXTRACT">EXTRACT</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="border rounded-md bg-card shadow-sm">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead className="w-[170px]">Timestamp</TableHead>
              <TableHead className="w-[160px]">Actor</TableHead>
              <TableHead className="w-[110px]">Action</TableHead>
              <TableHead className="w-[120px]">Resource</TableHead>
              <TableHead className="w-[100px]">ID</TableHead>
              <TableHead>Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={6} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : entries.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center py-12 text-muted-foreground">No audit entries match the current filters.</TableCell></TableRow>
            ) : (
              entries.map((log) => (
                <TableRow key={log.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setSelectedId(log.id)}>
                  <TableCell className="tabular-nums text-xs text-muted-foreground">
                    {new Date(log.timestamp).toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0
                        ${log.actor_type === 'agent' ? 'bg-primary/10 text-primary' : log.actor_type === 'user' ? 'bg-orange-100 text-orange-600' : 'bg-gray-100 text-gray-500'}`}>
                        {ACTOR_ICON[log.actor_type]}
                      </div>
                      <span className="text-sm font-medium truncate max-w-[120px]">{log.actor}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[10px] ${ACTION_COLORS[log.action] || 'bg-gray-50 text-gray-600'}`}>
                      {log.action}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs">{log.resource_type}</TableCell>
                  <TableCell className="font-mono text-xs text-primary">{log.resource_id}</TableCell>
                  <TableCell className="text-xs text-muted-foreground truncate max-w-[250px]">{log.detail}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">Page {page + 1} of {totalPages}</p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
              <ChevronLeft className="w-4 h-4 mr-1" /> Previous
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}>
              Next <ChevronRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        </div>
      )}

      <Dialog open={!!selectedId} onOpenChange={(open) => { if (!open) setSelectedId(null); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Audit Entry — {selectedEntry?.id}</DialogTitle>
          </DialogHeader>
          {selectedEntry && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div><span className="text-muted-foreground">Actor:</span> {selectedEntry.actor}</div>
                <div><span className="text-muted-foreground">Type:</span> {selectedEntry.actor_type}</div>
                <div><span className="text-muted-foreground">Action:</span> {selectedEntry.action}</div>
                <div><span className="text-muted-foreground">Resource:</span> {selectedEntry.resource_type}</div>
                <div><span className="text-muted-foreground">Resource ID:</span> {selectedEntry.resource_id}</div>
                <div><span className="text-muted-foreground">IP:</span> {selectedEntry.ip_address}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Timestamp:</span>{' '}
                {new Date(selectedEntry.timestamp).toLocaleString()}
              </div>
              <div>
                <span className="text-muted-foreground">Detail:</span> {selectedEntry.detail}
              </div>
              {selectedEntry.metadata && (
                <div>
                  <span className="text-muted-foreground">Metadata:</span>
                  <pre className="mt-1 p-3 bg-muted rounded text-xs overflow-auto max-h-48">
                    {JSON.stringify(selectedEntry.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
