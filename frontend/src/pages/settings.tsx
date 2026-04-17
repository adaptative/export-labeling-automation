import React, { useState, useEffect } from 'react';
import { useLocation } from 'wouter';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { User, Lock, ShieldCheck, Bell } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import {
  useProfile, useUpdateProfile, useChangePassword,
  useMFAStatus, useEnableMFA, useVerifyMFA, useDisableMFA,
} from '@/hooks/useSettings';
import {
  useNotificationPreferences, useUpdateNotificationPreferences,
} from '@/hooks/useNotifications';
import { notificationTypeLabel, type EventPreference } from '@/api/notifications';

function ProfileSection() {
  const { data: profile, isLoading } = useProfile();
  const updateProfile = useUpdateProfile();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [timezone, setTimezone] = useState('UTC');

  useEffect(() => {
    if (profile) {
      setName(profile.display_name);
      setPhone(profile.phone || '');
      setTimezone(profile.timezone);
    }
  }, [profile]);

  if (isLoading) {
    return <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-10 w-full" />)}</div>;
  }

  const handleSave = () => {
    updateProfile.mutate({
      display_name: name,
      phone: phone || undefined,
      timezone,
    });
  };

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <div className="space-y-2">
          <Label>Email</Label>
          <Input value={profile?.email || ''} disabled className="bg-muted" />
        </div>
        <div className="space-y-2">
          <Label>Display name</Label>
          <Input value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label>Phone</Label>
          <Input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+1-555-0100" />
        </div>
        <div className="space-y-2">
          <Label>Timezone</Label>
          <Select value={timezone} onValueChange={setTimezone}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="UTC">UTC</SelectItem>
              <SelectItem value="America/New_York">Eastern (US)</SelectItem>
              <SelectItem value="America/Chicago">Central (US)</SelectItem>
              <SelectItem value="America/Los_Angeles">Pacific (US)</SelectItem>
              <SelectItem value="Asia/Kolkata">India (IST)</SelectItem>
              <SelectItem value="Europe/London">London (GMT)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <Button onClick={handleSave} disabled={updateProfile.isPending}>
        {updateProfile.isPending ? 'Saving...' : 'Save changes'}
      </Button>
      {updateProfile.isSuccess && (
        <p className="text-sm text-green-600">Profile updated.</p>
      )}
    </div>
  );
}

function SecuritySection() {
  const changePassword = useChangePassword();
  const { data: mfa, isLoading: mfaLoading } = useMFAStatus();
  const enableMFA = useEnableMFA();
  const verifyMFA = useVerifyMFA();
  const disableMFA = useDisableMFA();

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [mfaSetup, setMfaSetup] = useState<{ secret: string; qr_uri: string } | null>(null);

  const handleChangePassword = async () => {
    try {
      await changePassword.mutateAsync({ current_password: currentPw, new_password: newPw });
      setCurrentPw('');
      setNewPw('');
    } catch {
      // error displayed via mutation state
    }
  };

  const handleStartMFA = async () => {
    const result = await enableMFA.mutateAsync('totp');
    setMfaSetup(result);
  };

  const handleVerifyMFA = async () => {
    await verifyMFA.mutateAsync(mfaCode);
    setMfaSetup(null);
    setMfaCode('');
  };

  return (
    <div className="space-y-8">
      {/* Password section */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-muted-foreground" />
          <h3 className="font-medium">Change password</h3>
        </div>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Current password</Label>
            <Input type="password" value={currentPw} onChange={e => setCurrentPw(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>New password</Label>
            <Input type="password" value={newPw} onChange={e => setNewPw(e.target.value)} />
          </div>
        </div>
        <Button onClick={handleChangePassword} disabled={changePassword.isPending || !currentPw || !newPw}>
          {changePassword.isPending ? 'Changing...' : 'Change password'}
        </Button>
        {changePassword.isSuccess && <p className="text-sm text-green-600">Password changed.</p>}
        {changePassword.isError && <p className="text-sm text-destructive">{changePassword.error.message}</p>}
      </div>

      {/* MFA section */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-muted-foreground" />
          <h3 className="font-medium">Multi-factor authentication</h3>
        </div>

        {mfaLoading ? (
          <Skeleton className="h-10 w-48" />
        ) : mfa?.enabled ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge variant="default">Enabled</Badge>
              <span className="text-sm text-muted-foreground">Method: {mfa.method}</span>
            </div>
            <Button variant="destructive" size="sm" onClick={() => disableMFA.mutate()} disabled={disableMFA.isPending}>
              Disable MFA
            </Button>
          </div>
        ) : mfaSetup ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Add this secret to your authenticator app:
            </p>
            <code className="block p-3 bg-muted rounded text-sm font-mono break-all">{mfaSetup.secret}</code>
            <div className="space-y-2">
              <Label>Verification code</Label>
              <div className="flex gap-2">
                <Input value={mfaCode} onChange={e => setMfaCode(e.target.value)} placeholder="123456" className="w-32" />
                <Button onClick={handleVerifyMFA} disabled={verifyMFA.isPending || mfaCode.length < 6}>
                  Verify
                </Button>
              </div>
            </div>
            {verifyMFA.isError && <p className="text-sm text-destructive">{verifyMFA.error.message}</p>}
          </div>
        ) : (
          <div>
            <Badge variant="secondary">Disabled</Badge>
            <Button variant="outline" size="sm" className="ml-3" onClick={handleStartMFA} disabled={enableMFA.isPending}>
              Enable MFA
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function NotificationsSection() {
  const { data, isLoading } = useNotificationPreferences();
  const update = useUpdateNotificationPreferences();
  const [local, setLocal] = useState<EventPreference[] | null>(null);

  useEffect(() => {
    if (data?.preferences) setLocal(data.preferences);
  }, [data]);

  if (isLoading || !local) {
    return <div className="space-y-3">{[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-12 w-full" />)}</div>;
  }

  const togglePref = (idx: number, patch: Partial<EventPreference>) => {
    setLocal(prev => prev!.map((p, i) => (i === idx ? { ...p, ...patch, channels: { ...p.channels, ...(patch.channels ?? {}) } } : p)));
  };

  const toggleChannel = (idx: number, channel: keyof EventPreference['channels'], value: boolean) => {
    setLocal(prev => prev!.map((p, i) => (i === idx ? { ...p, channels: { ...p.channels, [channel]: value } } : p)));
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="font-medium text-sm flex items-center gap-2">
          <Bell className="w-4 h-4 text-muted-foreground" />
          Event preferences
        </h3>
        <p className="text-xs text-muted-foreground">
          Choose which events trigger alerts and on which channels. Preferences apply tenant-wide.
        </p>
      </div>

      <div className="border rounded-md divide-y">
        <div className="grid grid-cols-6 px-3 py-2 text-[11px] uppercase tracking-wide text-muted-foreground bg-muted/30">
          <div className="col-span-2">Event</div>
          <div className="text-center">Email</div>
          <div className="text-center">Slack</div>
          <div className="text-center">PagerDuty</div>
          <div className="text-center">In-app</div>
        </div>
        {local.map((pref, idx) => (
          <div key={pref.event_type} className="grid grid-cols-6 px-3 py-2.5 items-center gap-2">
            <div className="col-span-2">
              <div className="text-sm font-medium">{notificationTypeLabel(pref.event_type)}</div>
              <div className="text-[11px] text-muted-foreground font-mono">{pref.event_type}</div>
            </div>
            <div className="flex justify-center">
              <Switch
                checked={pref.channels.email}
                onCheckedChange={(v: boolean) => toggleChannel(idx, 'email', v)}
                disabled={!pref.enabled}
              />
            </div>
            <div className="flex justify-center">
              <Switch
                checked={pref.channels.slack}
                onCheckedChange={(v: boolean) => toggleChannel(idx, 'slack', v)}
                disabled={!pref.enabled}
              />
            </div>
            <div className="flex justify-center">
              <Switch
                checked={pref.channels.pagerduty}
                onCheckedChange={(v: boolean) => toggleChannel(idx, 'pagerduty', v)}
                disabled={!pref.enabled}
              />
            </div>
            <div className="flex justify-center">
              <Switch
                checked={pref.channels.in_app}
                onCheckedChange={(v: boolean) => toggleChannel(idx, 'in_app', v)}
                disabled={!pref.enabled}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Disabled channels suppress new alerts. Existing notifications remain in your inbox.
        </p>
        <Button
          onClick={() => update.mutate(local)}
          disabled={update.isPending}
        >
          {update.isPending ? 'Saving…' : 'Save preferences'}
        </Button>
      </div>
      {update.isSuccess && (
        <p className="text-xs text-green-600">Notification preferences updated.</p>
      )}
      {update.isError && (
        <p className="text-xs text-red-600">Failed to save — try again.</p>
      )}
    </div>
  );
}

export default function Settings() {
  const [location] = useLocation();
  const section = location.split('/settings/')[1] || 'profile';

  const titleMap: Record<string, { label: string; desc: string; icon: React.ReactNode }> = {
    profile: {
      label: 'Profile',
      desc: 'Manage your personal information.',
      icon: <User className="w-6 h-6" />,
    },
    security: {
      label: 'Security',
      desc: 'Password and authentication settings.',
      icon: <Lock className="w-6 h-6" />,
    },
    notifications: {
      label: 'Notifications',
      desc: 'Control which events send alerts and where.',
      icon: <Bell className="w-6 h-6" />,
    },
  };
  const info = titleMap[section] ?? titleMap.profile;

  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          {info.icon}
          Settings: {info.label}
        </h1>
        <p className="text-sm text-muted-foreground">{info.desc}</p>
      </div>

      {section === 'security' && <SecuritySection />}
      {section === 'notifications' && <NotificationsSection />}
      {section !== 'security' && section !== 'notifications' && <ProfileSection />}
    </div>
  );
}
