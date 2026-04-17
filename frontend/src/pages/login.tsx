import React, { useState } from 'react';
import { useLocation } from 'wouter';
import { useAuthStore } from '../store/authStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

function LabelforgeAnimation() {
  return (
    <svg
      viewBox="0 0 480 480"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="w-full max-w-[420px]"
    >
      <style>{`
        @keyframes scanLine {
          0%, 100% { transform: translateY(0); opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { transform: translateY(100px); opacity: 0; }
        }
        @keyframes docSlide {
          0% { transform: translateY(20px); opacity: 0; }
          20% { transform: translateY(0); opacity: 1; }
          80% { opacity: 1; }
          100% { opacity: 1; }
        }
        @keyframes checkDraw {
          0% { stroke-dashoffset: 24; }
          100% { stroke-dashoffset: 0; }
        }
        @keyframes dataFlow {
          0% { stroke-dashoffset: 20; }
          100% { stroke-dashoffset: 0; }
        }
        @keyframes fadeLoop {
          0%, 100% { opacity: 0.15; }
          50% { opacity: 0.4; }
        }
        @keyframes labelPrint {
          0% { transform: scaleY(0); transform-origin: top; }
          60% { transform: scaleY(1); transform-origin: top; }
          100% { transform: scaleY(1); transform-origin: top; }
        }
        @keyframes barcode {
          0% { width: 0; }
          100% { width: 100%; }
        }
        @keyframes gearSpin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes gearSpinReverse {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(-360deg); }
        }
        @keyframes pulseRing {
          0% { r: 6; opacity: 0.6; }
          50% { r: 10; opacity: 0; }
          100% { r: 6; opacity: 0; }
        }
        @keyframes flowDash {
          0% { stroke-dashoffset: 16; }
          100% { stroke-dashoffset: 0; }
        }
        @keyframes nodeAppear {
          0% { transform: scale(0); opacity: 0; }
          50% { transform: scale(1.15); opacity: 1; }
          100% { transform: scale(1); opacity: 1; }
        }
        .scan-line { animation: scanLine 3s ease-in-out infinite; }
        .doc-enter { animation: docSlide 2s ease-out forwards; }
        .check-mark { stroke-dasharray: 24; stroke-dashoffset: 24; animation: checkDraw 0.6s ease-out forwards; }
        .data-line { stroke-dasharray: 6 4; animation: dataFlow 1.5s linear infinite; }
        .grid-fade { animation: fadeLoop 4s ease-in-out infinite; }
        .label-body { animation: labelPrint 2.5s ease-out forwards; }
        .gear1 { transform-origin: 344px 240px; animation: gearSpin 6s linear infinite; }
        .gear2 { transform-origin: 372px 260px; animation: gearSpinReverse 4s linear infinite; }
        .pulse { animation: pulseRing 2s ease-out infinite; }
        .flow-path { stroke-dasharray: 8 8; animation: flowDash 1s linear infinite; }
        .node-pop { animation: nodeAppear 0.5s ease-out forwards; opacity: 0; }
      `}</style>

      {/* Background grid */}
      <g className="grid-fade">
        {Array.from({ length: 12 }).map((_, i) => (
          <line key={`gv-${i}`} x1={40 * i} y1={0} x2={40 * i} y2={480} stroke="currentColor" strokeWidth="0.5" className="text-primary/10" />
        ))}
        {Array.from({ length: 12 }).map((_, i) => (
          <line key={`gh-${i}`} x1={0} y1={40 * i} x2={480} y2={40 * i} stroke="currentColor" strokeWidth="0.5" className="text-primary/10" />
        ))}
      </g>

      {/* === Stage 1: Source Document (left) === */}
      <g className="doc-enter" style={{ animationDelay: '0s' }}>
        {/* Document shape */}
        <rect x="40" y="140" width="100" height="130" rx="6" className="fill-background stroke-primary/40" strokeWidth="1.5" />
        {/* Page fold */}
        <path d="M115 140 L140 140 L140 165 L115 165 Z" className="fill-muted stroke-primary/30" strokeWidth="1" />
        <path d="M115 140 L140 165" className="stroke-primary/30" strokeWidth="1" />
        {/* Text lines */}
        <rect x="52" y="158" width="50" height="3" rx="1.5" className="fill-primary/20" />
        <rect x="52" y="168" width="42" height="3" rx="1.5" className="fill-primary/15" />
        <rect x="52" y="178" width="55" height="3" rx="1.5" className="fill-primary/20" />
        <rect x="52" y="188" width="38" height="3" rx="1.5" className="fill-primary/15" />
        <rect x="52" y="202" width="48" height="3" rx="1.5" className="fill-primary/12" />
        <rect x="52" y="212" width="55" height="3" rx="1.5" className="fill-primary/15" />
        <rect x="52" y="222" width="30" height="3" rx="1.5" className="fill-primary/12" />
        {/* Scan line */}
        <rect x="44" y="145" width="92" height="2" rx="1" className="fill-primary/60 scan-line" />
      </g>

      {/* === Flow arrow 1 === */}
      <g style={{ animationDelay: '0.8s' }} className="doc-enter">
        <path d="M150 205 L185 205" className="stroke-primary/30 flow-path" strokeWidth="1.5" fill="none" />
        <polygon points="185,200 195,205 185,210" className="fill-primary/30" />
      </g>

      {/* === Stage 2: Processing Engine (center) === */}
      <g className="doc-enter" style={{ animationDelay: '0.5s' }}>
        {/* Central processor box */}
        <rect x="195" y="155" width="120" height="100" rx="8" className="fill-background stroke-primary/50" strokeWidth="1.5" />

        {/* Extraction rows */}
        <g>
          <text x="210" y="178" className="fill-primary/70" fontSize="8" fontFamily="monospace">EXTRACT</text>
          <rect x="260" y="170" width="40" height="6" rx="2" className="fill-primary/15" />
          <rect x="260" y="170" width="28" height="6" rx="2" className="fill-primary/40">
            <animate attributeName="width" from="0" to="28" dur="2s" begin="1s" fill="freeze" />
          </rect>
        </g>
        <g>
          <text x="210" y="198" className="fill-primary/70" fontSize="8" fontFamily="monospace">FUSE</text>
          <rect x="260" y="190" width="40" height="6" rx="2" className="fill-primary/15" />
          <rect x="260" y="190" width="35" height="6" rx="2" className="fill-primary/40">
            <animate attributeName="width" from="0" to="35" dur="2s" begin="1.5s" fill="freeze" />
          </rect>
        </g>
        <g>
          <text x="210" y="218" className="fill-primary/70" fontSize="8" fontFamily="monospace">VALIDATE</text>
          <rect x="260" y="210" width="40" height="6" rx="2" className="fill-primary/15" />
          <rect x="260" y="210" width="40" height="6" rx="2" className="fill-primary/40">
            <animate attributeName="width" from="0" to="40" dur="2s" begin="2s" fill="freeze" />
          </rect>
        </g>
        <g>
          <text x="210" y="243" className="fill-primary/70" fontSize="8" fontFamily="monospace">COMPOSE</text>
          <rect x="260" y="235" width="40" height="6" rx="2" className="fill-primary/15" />
          <rect x="260" y="235" width="32" height="6" rx="2" className="fill-primary/40">
            <animate attributeName="width" from="0" to="32" dur="2s" begin="2.5s" fill="freeze" />
          </rect>
        </g>

        {/* Gears */}
        <g className="gear1">
          <circle cx="344" cy="240" r="14" className="stroke-primary/20" strokeWidth="1.5" fill="none" />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
            <rect
              key={angle}
              x="341" y="224"
              width="6" height="6" rx="1"
              className="fill-primary/20"
              transform={`rotate(${angle} 344 240)`}
            />
          ))}
          <circle cx="344" cy="240" r="5" className="fill-primary/10 stroke-primary/25" strokeWidth="1" />
        </g>
        <g className="gear2">
          <circle cx="372" cy="260" r="10" className="stroke-primary/15" strokeWidth="1.5" fill="none" />
          {[0, 60, 120, 180, 240, 300].map((angle) => (
            <rect
              key={angle}
              x="370" y="249"
              width="4" height="4" rx="1"
              className="fill-primary/15"
              transform={`rotate(${angle} 372 260)`}
            />
          ))}
          <circle cx="372" cy="260" r="3.5" className="fill-primary/8 stroke-primary/20" strokeWidth="1" />
        </g>
      </g>

      {/* === Flow arrow 2 === */}
      <g style={{ animationDelay: '1.5s' }} className="doc-enter">
        <path d="M315 205 L350 205" className="stroke-primary/30 flow-path" strokeWidth="1.5" fill="none" />
        <polygon points="350,200 360,205 350,210" className="fill-primary/30" />
      </g>

      {/* === Stage 3: Output Label (right) === */}
      <g className="doc-enter" style={{ animationDelay: '1s' }}>
        <g className="label-body">
          <rect x="360" y="140" width="90" height="130" rx="4" className="fill-background stroke-primary/40" strokeWidth="1.5" />

          {/* Label header */}
          <rect x="370" y="150" width="70" height="14" rx="2" className="fill-primary/10" />
          <text x="380" y="160" className="fill-primary/60" fontSize="7" fontFamily="monospace" fontWeight="600">WARNING</text>

          {/* Barcode */}
          {[0, 5, 8, 12, 15, 19, 22, 25, 28, 32, 35, 38, 41, 44, 48, 51, 54, 57, 60].map((x, i) => (
            <rect
              key={`bar-${i}`}
              x={375 + x}
              y="172"
              width={i % 3 === 0 ? 3 : 2}
              height="20"
              className="fill-primary/30"
            />
          ))}

          {/* Label content lines */}
          <rect x="375" y="200" width="60" height="2.5" rx="1" className="fill-primary/20" />
          <rect x="375" y="208" width="50" height="2.5" rx="1" className="fill-primary/15" />
          <rect x="375" y="216" width="55" height="2.5" rx="1" className="fill-primary/18" />
          <rect x="375" y="224" width="40" height="2.5" rx="1" className="fill-primary/12" />

          {/* Compliance check icon */}
          <circle cx="420" cy="250" r="10" className="fill-primary/10 stroke-primary/40" strokeWidth="1.5" />
          <path
            d="M414 250 L418 254 L426 246"
            className="stroke-primary/70 check-mark"
            strokeWidth="2"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ animationDelay: '3s' }}
          />
        </g>
      </g>

      {/* === Bottom: Pipeline status nodes === */}
      <g>
        {[
          { x: 90, label: 'Intake', delay: '0.2s' },
          { x: 170, label: 'Extract', delay: '0.5s' },
          { x: 255, label: 'Validate', delay: '0.8s' },
          { x: 340, label: 'Compose', delay: '1.1s' },
          { x: 410, label: 'Deliver', delay: '1.4s' },
        ].map((node, i) => (
          <g key={node.label} className="node-pop" style={{ animationDelay: node.delay }}>
            <circle cx={node.x} cy="330" r="6" className="fill-primary/20 stroke-primary/40" strokeWidth="1" />
            <circle cx={node.x} cy="330" className="stroke-primary/30 pulse" strokeWidth="1" fill="none" style={{ animationDelay: `${i * 0.4}s` }}>
              <animate attributeName="r" values="6;12;6" dur="2.5s" begin={`${i * 0.4}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.5;0;0.5" dur="2.5s" begin={`${i * 0.4}s`} repeatCount="indefinite" />
            </circle>
            <circle cx={node.x} cy="330" r="2.5" className="fill-primary/50" />
            <text x={node.x} y="348" textAnchor="middle" className="fill-muted-foreground/70" fontSize="7" fontFamily="monospace">{node.label}</text>
            {i < 4 && (
              <line
                x1={node.x + 10}
                y1={330}
                x2={[170, 255, 340, 410][i] - 10}
                y2={330}
                className="stroke-primary/20 data-line"
                strokeWidth="1"
              />
            )}
          </g>
        ))}
      </g>

      {/* === Top tagline === */}
      <text x="240" y="110" textAnchor="middle" className="fill-primary/50" fontSize="11" fontFamily="monospace" fontWeight="500">
        Automated Label Compliance
      </text>
      <text x="240" y="125" textAnchor="middle" className="fill-muted-foreground/50" fontSize="8" fontFamily="monospace">
        Intake → Extract → Validate → Compose → Deliver
      </text>
    </svg>
  );
}

export default function Login() {
  const [, setLocation] = useLocation();
  const { loginUser, isLoading, error: authError } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (email && password) {
      try {
        await loginUser(email, password);
        setLocation('/');
      } catch (err: any) {
        setError(err.message || 'Login failed');
      }
    }
  };

  const handleSSOGoogle = () => {
    window.location.href = '/api/v1/auth/oidc/google/authorize';
  };

  const handleSSOMS = () => {
    window.location.href = '/api/v1/auth/saml/microsoft/login';
  };

  return (
    <div className="min-h-screen w-full flex bg-background">
      <div className="hidden lg:flex w-1/2 bg-muted items-center justify-center relative overflow-hidden">
        <div className="absolute inset-0 bg-sidebar/5" />
        <LabelforgeAnimation />
      </div>
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8">
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-2 text-center">
            <h1 className="text-3xl font-bold font-mono text-primary">Labelforge</h1>
            <p className="text-sm text-muted-foreground">Sign in to your account</p>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            {(error || authError) && (
              <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md" data-testid="login-error">
                {error || authError}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@nakodacraft.com"
                required
                disabled={isLoading}
                data-testid="input-email"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <a href="#" className="text-xs text-primary hover:underline">Forgot password?</a>
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isLoading}
                data-testid="input-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={isLoading} data-testid="button-submit-login">
              {isLoading ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border"></div>
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-2 text-muted-foreground">Or continue with</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Button variant="outline" className="w-full" type="button" onClick={handleSSOGoogle} disabled={isLoading} data-testid="button-sso-google">
              Google
            </Button>
            <Button variant="outline" className="w-full" type="button" onClick={handleSSOMS} disabled={isLoading} data-testid="button-sso-ms">
              Microsoft
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
