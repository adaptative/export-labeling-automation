import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Bot, Clock, ArrowRight } from 'lucide-react';
import type { ProvenanceStep } from '@/hooks/useArtifacts';

interface ProvenanceChainProps {
  steps: ProvenanceStep[];
}

export function ProvenanceChain({ steps }: ProvenanceChainProps) {
  return (
    <div className="space-y-0">
      {steps.map((step, i) => (
        <div key={step.step_number} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-xs font-bold shrink-0">
              {step.step_number}
            </div>
            {i < steps.length - 1 && <div className="w-px flex-1 bg-border min-h-[24px]" />}
          </div>
          <div className="pb-4 flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Bot className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="text-sm font-medium">{step.agent_id}</span>
              <Badge variant="outline" className="text-[10px]">{step.action}</Badge>
            </div>
            {step.model_id && (
              <p className="text-xs text-muted-foreground">Model: {step.model_id}</p>
            )}
            <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
              <span className="font-mono truncate" title={step.input_hash}>
                In: {step.input_hash.slice(0, 20)}...
              </span>
              <ArrowRight className="w-3 h-3 shrink-0" />
              <span className="font-mono truncate" title={step.output_hash}>
                Out: {step.output_hash.slice(0, 20)}...
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
              <Clock className="w-3 h-3" />
              <span>{new Date(step.timestamp).toLocaleString()}</span>
              <span>({step.duration_ms}ms)</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
