/**
 * Lightweight JSON/DSL editor with syntax highlighting.
 *
 * Uses the classic "transparent textarea over a highlighted <pre>" trick, so
 * we get syntax colors without pulling in Prism.js or react-syntax-highlighter.
 * The highlighter is token-based: keys, strings, numbers, booleans, operators,
 * and punctuation each get their own class.
 */
import React, { useEffect, useMemo, useRef } from 'react';
import { cn } from '@/lib/utils';

interface DslEditorProps {
  value: string;
  onChange: (next: string) => void;
  error?: string | null;
  placeholder?: string;
  rows?: number;
  className?: string;
  readOnly?: boolean;
  ariaLabel?: string;
}

const TOKEN_REGEX = new RegExp(
  [
    '(?<comment>//[^\\n]*)',
    '(?<string>"(?:\\\\.|[^"\\\\])*")',
    '(?<number>-?\\b\\d+(?:\\.\\d+)?\\b)',
    '(?<bool>\\b(?:true|false|null)\\b)',
    '(?<keyword>\\b(?:AND|OR|NOT|in|not_in|op|field|value|values|child|children|conditions|requirements|category)\\b)',
    '(?<operator>==|!=|>=|<=|>|<)',
    '(?<brace>[{}\\[\\]])',
    '(?<punct>[:,])',
  ].join('|'),
  'g',
);

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function highlight(source: string): string {
  // Ensure a trailing newline so the overlay doesn't collapse on the last
  // empty row (mirrors textarea behavior).
  const src = source.endsWith('\n') ? source + ' ' : source;
  let out = '';
  let cursor = 0;
  for (const m of src.matchAll(TOKEN_REGEX)) {
    const start = m.index ?? 0;
    if (start > cursor) out += escapeHtml(src.slice(cursor, start));
    const groups = m.groups ?? {};
    let cls = 'dsl-plain';
    if (groups.comment) cls = 'dsl-comment';
    else if (groups.string) cls = 'dsl-string';
    else if (groups.number) cls = 'dsl-number';
    else if (groups.bool) cls = 'dsl-bool';
    else if (groups.keyword) cls = 'dsl-keyword';
    else if (groups.operator) cls = 'dsl-operator';
    else if (groups.brace) cls = 'dsl-brace';
    else if (groups.punct) cls = 'dsl-punct';
    out += `<span class="${cls}">${escapeHtml(m[0])}</span>`;
    cursor = start + m[0].length;
  }
  if (cursor < src.length) out += escapeHtml(src.slice(cursor));
  return out;
}

export function DslEditor({
  value,
  onChange,
  error,
  placeholder,
  rows = 14,
  className,
  readOnly = false,
  ariaLabel,
}: DslEditorProps) {
  const preRef = useRef<HTMLPreElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const highlighted = useMemo(() => highlight(value || ''), [value]);

  // Keep the <pre> scrolled in lockstep with the textarea so highlighting
  // stays aligned on long inputs.
  useEffect(() => {
    const ta = textareaRef.current;
    const pre = preRef.current;
    if (!ta || !pre) return;
    const syncScroll = () => {
      pre.scrollTop = ta.scrollTop;
      pre.scrollLeft = ta.scrollLeft;
    };
    ta.addEventListener('scroll', syncScroll);
    return () => ta.removeEventListener('scroll', syncScroll);
  }, []);

  return (
    <div className={cn('dsl-editor relative rounded-md border bg-slate-950 text-slate-50', className)}>
      <style>{DSL_STYLES}</style>
      <pre
        ref={preRef}
        aria-hidden="true"
        className="dsl-pre pointer-events-none absolute inset-0 m-0 overflow-auto whitespace-pre p-3 font-mono text-xs leading-5"
        // eslint-disable-next-line react/no-danger -- highlighted is escaped
        dangerouslySetInnerHTML={{ __html: highlighted || '&nbsp;' }}
      />
      <textarea
        ref={textareaRef}
        className="dsl-textarea relative w-full resize-y overflow-auto whitespace-pre bg-transparent p-3 font-mono text-xs leading-5 text-transparent caret-white outline-none selection:bg-blue-500/40"
        style={{ minHeight: `${rows * 1.25}rem` }}
        rows={rows}
        value={value}
        placeholder={placeholder}
        readOnly={readOnly}
        spellCheck={false}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.value)}
      />
      {error && (
        <div className="absolute bottom-1 right-2 rounded bg-red-600/90 px-2 py-0.5 text-[11px] text-white shadow">
          {error}
        </div>
      )}
    </div>
  );
}

const DSL_STYLES = `
.dsl-editor .dsl-keyword  { color: #c4b5fd; font-weight: 600; }
.dsl-editor .dsl-string   { color: #86efac; }
.dsl-editor .dsl-number   { color: #fcd34d; }
.dsl-editor .dsl-bool     { color: #f472b6; font-weight: 600; }
.dsl-editor .dsl-operator { color: #f97316; }
.dsl-editor .dsl-brace    { color: #e2e8f0; }
.dsl-editor .dsl-punct    { color: #94a3b8; }
.dsl-editor .dsl-comment  { color: #64748b; font-style: italic; }
.dsl-editor .dsl-plain    { color: #cbd5e1; }
.dsl-editor textarea::placeholder { color: #64748b; }
`;

/**
 * Read-only code block using the same highlighter. Convenient for detail views
 * that need to display DSL without making it editable.
 */
export function DslPreview({ value, className }: { value: string; className?: string }) {
  const highlighted = useMemo(() => highlight(value || ''), [value]);
  return (
    <div className={cn('dsl-editor rounded-md border bg-slate-950', className)}>
      <style>{DSL_STYLES}</style>
      <pre
        className="dsl-pre m-0 overflow-auto whitespace-pre p-3 font-mono text-xs leading-5 text-slate-50"
        // eslint-disable-next-line react/no-danger -- highlighted is escaped
        dangerouslySetInnerHTML={{ __html: highlighted || '<span class="dsl-plain">(empty)</span>' }}
      />
    </div>
  );
}
