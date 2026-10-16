import React from 'react';
import type { AnalysisResponse } from '../api';
import { LogViewer } from './LogViewer';

const CATEGORY_LABELS: Record<string, string> = {
  dependency: 'Dependency',
  infrastructure: 'Infrastructure',
  authentication: 'Authentication',
  permission: 'Permission',
  compilation: 'Compilation',
  syntax: 'Syntax',
  configuration: 'Configuration',
  environment: 'Environment',
  test: 'Test',
  unknown: 'Unknown',
};

const CATEGORY_COLORS: Record<string, string> = {
  dependency: 'text-amber-400 bg-amber-950/50 border-amber-800',
  infrastructure: 'text-red-400 bg-red-950/50 border-red-800',
  authentication: 'text-orange-400 bg-orange-950/50 border-orange-800',
  permission: 'text-orange-400 bg-orange-950/50 border-orange-800',
  compilation: 'text-purple-400 bg-purple-950/50 border-purple-800',
  syntax: 'text-purple-400 bg-purple-950/50 border-purple-800',
  configuration: 'text-blue-400 bg-blue-950/50 border-blue-800',
  environment: 'text-cyan-400 bg-cyan-950/50 border-cyan-800',
  test: 'text-rose-400 bg-rose-950/50 border-rose-800',
  unknown: 'text-slate-400 bg-slate-800/50 border-slate-700',
};

interface StatCardProps {
  label: string;
  value: number | string;
  accent?: string;
}

const StatCard: React.FC<StatCardProps> = ({ label, value, accent = 'text-slate-100' }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-5 py-4">
    <div className={`text-2xl font-bold tabular-nums ${accent}`}>{value}</div>
    <div className="text-xs text-slate-500 mt-1">{label}</div>
  </div>
);

interface AnalysisResultProps {
  result: AnalysisResponse;
  onReset: () => void;
}

export const AnalysisResult: React.FC<AnalysisResultProps> = ({ result, onReset }) => {
  const rc = result.root_cause;
  const categoryColor = CATEGORY_COLORS[rc?.category ?? 'unknown'] ?? CATEGORY_COLORS.unknown;
  const categoryLabel = CATEGORY_LABELS[rc?.category ?? 'unknown'] ?? 'Unknown';

  const primaryLineNumbers = new Set(result.primary_evidence.map((l) => l.line_number));
  const supportLineNumbers = new Set(result.supporting_evidence.map((l) => l.line_number));
  const cascadeLineNumbers = new Set(result.cascading_failures.map((l) => l.line_number));

  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `whyci-analysis-${result.source_name}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportMarkdown = () => {
    const lines: string[] = [
      `# WhyCI Analysis: ${result.source_name}`,
      '',
      `> **Note:** ${result.analysis_notes.join(' ')}`,
      '',
      '## Summary',
      '',
      `| Metric | Value |`,
      `|--------|-------|`,
      `| Total lines | ${result.total_lines} |`,
      `| Errors | ${result.error_count} |`,
      `| Warnings | ${result.warning_count} |`,
      `| Failure clusters | ${result.failure_clusters.length} |`,
      '',
    ];

    if (rc) {
      lines.push(
        '## Root-Cause Candidate',
        '',
        `**Line ${rc.line_number}:** \`${rc.text}\``,
        '',
        `- Category: **${categoryLabel}**`,
        `- Priority score: **${rc.priority_score.toFixed(3)}** (deterministic weight, not AI confidence)`,
        `- Explanation: ${rc.explanation}`,
        '',
        '### Why this was selected',
        ...rc.score_reasons.map((r) => `- ${r}`),
        '',
      );
    } else {
      lines.push('## Root-Cause Candidate', '', '_No high-priority candidate found._', '');
    }

    if (result.debugging_suggestions.length) {
      lines.push('## Debugging Suggestions', '', ...result.debugging_suggestions.map((s) => `- ${s}`), '');
    }

    if (result.redaction) {
      lines.push(
        '## Redaction',
        '',
        result.redaction.applied
          ? `Applied: ${result.redaction.replacement_count} replacement(s) using rules: ${result.redaction.matched_rules.join(', ')}`
          : 'No secrets detected.',
        '',
      );
    }

    const md = lines.join('\n');
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `whyci-analysis-${result.source_name}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyReport = async () => {
    const text = [
      `WhyCI Analysis: ${result.source_name}`,
      `Errors: ${result.error_count}  Warnings: ${result.warning_count}  Lines: ${result.total_lines}`,
      '',
      rc
        ? `Root cause (line ${rc.line_number}): ${rc.text}\nScore: ${rc.priority_score.toFixed(3)}  Category: ${categoryLabel}\n${rc.explanation}`
        : 'No clear root-cause candidate.',
      '',
      ...result.debugging_suggestions,
    ].join('\n');
    await navigator.clipboard.writeText(text);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Analysis Results</h2>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">{result.source_name}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={copyReport} className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-700 text-slate-300 hover:border-slate-500 transition-colors">
            Copy report
          </button>
          <button onClick={exportMarkdown} className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-700 text-slate-300 hover:border-slate-500 transition-colors">
            Export .md
          </button>
          <button onClick={exportJSON} className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-700 text-slate-300 hover:border-slate-500 transition-colors">
            Export JSON
          </button>
          <button onClick={onReset} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors">
            ← New analysis
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Total lines" value={result.total_lines.toLocaleString()} />
        <StatCard
          label="Errors"
          value={result.error_count}
          accent={result.error_count > 0 ? 'text-red-400' : 'text-slate-100'}
        />
        <StatCard
          label="Warnings"
          value={result.warning_count}
          accent={result.warning_count > 0 ? 'text-yellow-400' : 'text-slate-100'}
        />
        <StatCard label="Failure clusters" value={result.failure_clusters.length} />
      </div>

      {/* Root cause */}
      {rc ? (
        <div className={`rounded-xl border p-5 ${categoryColor}`}>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-bold uppercase tracking-widest opacity-70">Root-cause candidate</span>
                <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold ${categoryColor}`}>
                  {categoryLabel}
                </span>
              </div>
              <p className="font-mono text-sm break-all">{rc.text}</p>
              <p className="text-xs opacity-60 mt-1">Line {rc.line_number}</p>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-3xl font-bold tabular-nums">{(rc.priority_score * 100).toFixed(0)}</div>
              <div className="text-xs opacity-60">priority score</div>
              <div className="text-xs opacity-40 mt-0.5">(deterministic, not AI)</div>
            </div>
          </div>

          <p className="text-sm mt-3 opacity-80">{rc.explanation}</p>

          {rc.score_reasons.length > 0 && (
            <ul className="mt-3 space-y-1">
              {rc.score_reasons.map((r, i) => (
                <li key={i} className="text-xs opacity-70 flex gap-1.5">
                  <span>•</span><span>{r}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-5">
          <p className="text-sm text-slate-400 font-medium">No high-priority root-cause candidate found</p>
          <p className="text-xs text-slate-500 mt-1">
            {result.analysis_notes.find((n) => n.includes('No high-priority')) ??
              'The log may contain only terminal-status lines or no recognised failure patterns.'}
          </p>
        </div>
      )}

      {/* Evidence */}
      <div className="space-y-3">
        <LogViewer
          title="Primary evidence"
          lines={result.primary_evidence}
          highlightLineNumbers={primaryLineNumbers}
        />
        <LogViewer
          title="Supporting evidence"
          lines={result.supporting_evidence}
          highlightLineNumbers={supportLineNumbers}
          defaultExpanded={false}
        />
        <LogViewer
          title={`Cascading failures (${result.cascading_failures.length})`}
          lines={result.cascading_failures}
          highlightLineNumbers={cascadeLineNumbers}
          defaultExpanded={result.cascading_failures.length > 0}
        />
        <LogViewer
          title="Failure clusters — all error lines"
          lines={result.failure_clusters.flatMap((c) => c.lines)}
          highlightLineNumbers={primaryLineNumbers}
          defaultExpanded={false}
          maxVisible={30}
        />
        <LogViewer
          title="Surrounding context"
          lines={result.relevant_context}
          defaultExpanded={false}
        />
      </div>

      {/* Debugging suggestions */}
      {result.debugging_suggestions.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <h3 className="text-sm font-semibold text-slate-200 mb-3">Suggested debugging steps</h3>
          <ol className="space-y-2">
            {result.debugging_suggestions.map((s, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-300">
                <span className="text-indigo-400 shrink-0 font-mono">{i + 1}.</span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Redaction */}
      {result.redaction && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 flex items-start gap-3">
          <svg className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <div>
            <p className="text-xs font-semibold text-emerald-400">Secret redaction</p>
            {result.redaction.applied ? (
              <p className="text-xs text-slate-400 mt-0.5">
                {result.redaction.replacement_count} secret value(s) replaced with [REDACTED]
                {result.redaction.matched_rules.length > 0 &&
                  ` · rules: ${result.redaction.matched_rules.join(', ')}`}
              </p>
            ) : (
              <p className="text-xs text-slate-400 mt-0.5">No credentials detected in this log.</p>
            )}
            <p className="text-xs text-slate-600 mt-1">
              Regex-based detection — cannot guarantee all secrets are caught.
            </p>
          </div>
        </div>
      )}

      {/* Analysis notes */}
      {result.analysis_notes.length > 0 && (
        <div className="rounded-xl border border-slate-800 px-4 py-3">
          {result.analysis_notes.map((note, i) => (
            <p key={i} className="text-xs text-slate-500">{note}</p>
          ))}
        </div>
      )}
    </div>
  );
};
