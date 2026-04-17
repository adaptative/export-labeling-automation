import React, { useState } from 'react';
import { useLocation } from 'wouter';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import {
  UserPlus, Shield, ShieldCheck, Users, MoreHorizontal,
} from 'lucide-react';
import {
  useAdminUsers, useInviteUser, useUpdateRole,
  useDeactivateUser, useActivateUser, useSSOConfig, useUpdateSSO,
  type AdminUser,
} from '@/hooks/useAdmin';

const ROLES = ['ADMIN', 'OPS', 'COMPLIANCE', 'EXTERNAL'] as const;

const ROLE_BADGE: Record<string, string> = {
  ADMIN: 'bg-red-50 text-red-700 border-red-200',
  OPS: 'bg-blue-50 text-blue-700 border-blue-200',
  COMPLIANCE: 'bg-amber-50 text-amber-700 border-amber-200',
  EXTERNAL: 'bg-gray-100 text-gray-700 border-gray-200',
};

function UsersSection() {
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState('OPS');

  const filters = roleFilter !== 'all' ? { role: roleFilter } : undefined;
  const { data, isLoading, error } = useAdminUsers(filters);
  const inviteMut = useInviteUser();
  const roleMut = useUpdateRole();
  const deactivateMut = useDeactivateUser();
  const activateMut = useActivateUser();

  const handleInvite = async () => {
    await inviteMut.mutateAsync({ email: inviteEmail, display_name: inviteName, role: inviteRole });
    setInviteOpen(false);
    setInviteEmail('');
    setInviteName('');
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Select value={roleFilter} onValueChange={setRoleFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="All roles" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All roles</SelectItem>
              {ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button size="sm" onClick={() => setInviteOpen(true)}>
          <UserPlus className="w-4 h-4 mr-1.5" /> Invite user
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      ) : error ? (
        <div className="border rounded-md p-8 text-center text-destructive">
          Failed to load users. Please try again.
        </div>
      ) : (
        <div className="border rounded-md">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last active</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.users.map((u: AdminUser) => (
                <TableRow key={u.user_id}>
                  <TableCell className="font-medium">{u.display_name}</TableCell>
                  <TableCell className="text-muted-foreground">{u.email}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={ROLE_BADGE[u.role] || ''}>
                      {u.role}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={u.status === 'active' ? 'default' : 'secondary'}>
                      {u.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {u.last_active ? new Date(u.last_active).toLocaleDateString() : '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Select
                        value={u.role}
                        onValueChange={(role) => roleMut.mutate({ userId: u.user_id, role })}
                      >
                        <SelectTrigger className="w-[120px] h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      {u.status === 'active' ? (
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => deactivateMut.mutate(u.user_id)}
                        >
                          Deactivate
                        </Button>
                      ) : (
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => activateMut.mutate(u.user_id)}
                        >
                          Activate
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite user</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Email</Label>
              <Input value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} placeholder="user@example.com" />
            </div>
            <div className="space-y-2">
              <Label>Name</Label>
              <Input value={inviteName} onChange={e => setInviteName(e.target.value)} placeholder="Full name" />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={inviteRole} onValueChange={setInviteRole}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInviteOpen(false)}>Cancel</Button>
            <Button onClick={handleInvite} disabled={inviteMut.isPending || !inviteEmail || !inviteName}>
              {inviteMut.isPending ? 'Sending...' : 'Send invite'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SecuritySection() {
  const { data: sso, isLoading } = useSSOConfig();
  const updateSSO = useUpdateSSO();
  const [googleClientId, setGoogleClientId] = useState('');

  if (isLoading) {
    return <div className="space-y-3">{[1,2].map(i => <Skeleton key={i} className="h-20 w-full" />)}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="border rounded-md p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-muted-foreground" />
            <div>
              <p className="font-medium">Google OIDC</p>
              <p className="text-sm text-muted-foreground">Sign in with Google Workspace</p>
            </div>
          </div>
          <Switch
            checked={sso?.oidc_google_enabled || false}
            onCheckedChange={(enabled) => updateSSO.mutate({ oidc_google_enabled: enabled })}
          />
        </div>
        {sso?.oidc_google_enabled && (
          <div className="flex items-center gap-2">
            <Input
              placeholder="Client ID"
              value={googleClientId || sso.oidc_google_client_id || ''}
              onChange={e => setGoogleClientId(e.target.value)}
              className="flex-1"
            />
            <Button
              size="sm"
              onClick={() => updateSSO.mutate({ oidc_google_client_id: googleClientId })}
              disabled={!googleClientId}
            >
              Save
            </Button>
          </div>
        )}
      </div>

      <div className="border rounded-md p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-muted-foreground" />
            <div>
              <p className="font-medium">Microsoft SAML</p>
              <p className="text-sm text-muted-foreground">Sign in with Azure AD</p>
            </div>
          </div>
          <Switch
            checked={sso?.saml_microsoft_enabled || false}
            onCheckedChange={(enabled) => updateSSO.mutate({ saml_microsoft_enabled: enabled })}
          />
        </div>
      </div>
    </div>
  );
}

export default function Admin() {
  const [location] = useLocation();
  const section = location.split('/admin/')[1] || 'users';

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Users className="w-6 h-6" />
          Admin: {section === 'users' ? 'Users' : 'Security'}
        </h1>
        <p className="text-sm text-muted-foreground">
          {section === 'users' ? 'Manage user accounts and roles.' : 'Configure SSO and authentication.'}
        </p>
      </div>

      {section === 'security' ? <SecuritySection /> : <UsersSection />}
    </div>
  );
}
