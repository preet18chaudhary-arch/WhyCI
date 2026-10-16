import React, { useState } from 'react';
import type { LogLineModel } from '../api';

interface LogViewerProps {
  lines: LogLineModel[];
  title: string;
  highlightLineNumbers?: Set<number>;
  defaultExpanded?: boolean;
  maxVisible?: number;
}

const lineClass = (text: string): string => {
  const t = text.toLowerCase();
  if (
    t.includes('error') || t.includes('fail') || t.includes('fatal') ||
    t.includes('exception') || t.includes('traceback') || t.includes('##[error]')
  ) return 'text-red-400';
  if (t.includes('warning') || t.includes('warn') || t.includes('##[warning]'))
    return 'text-yellow-400';
  return 'text-slate-300';
};

export const LogViewer: React.FC<LogViewerProps> = ({
  lines, title, highlightLineNumbers = new Set(), defaultExpanded = true, maxVisible = 50,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [search, setSearch] = useState('');
  const [showAll, setShowAll] = useState(false);

  if (!lines.length) return null;

  const filtered = search
    ? lines.filter((l) => l.text.toLowerCase().includes(search.toLowerCase()))
    : lines;

  const visible = showAll ? filtered : filtered.slice(0, maxVisible);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-800/50 transition-colors"
      >
        <span className="text-sm font-semibold text-slate-200">{title}</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500">{lines.length} line{lines.length !== 1 ? 's' : ''}</span>
          <svg
            className={`w-4 h-4 text-slate-500 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-800">
          {lines.length > 5 && (
            <div className="px-4 py-2 border-b border-slate-800">
              <input
                type="text"
                placeholder="Filter lines…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200
                  placeholder-slate-500 border border-slate-700 focus:outline-none focus:border-indigo-500"
              />
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <tbody>
                {visible.map((line) => (
                  <tr
                    key={line.line_number}
                    className={
                      highlightLineNumbers.has(line.line_number)
                        ? 'bg-indigo-950/50 border-l-2 border-indigo-500'
                        : 'hover:bg-slate-800/30'
                    }
                  >
                    <td className="pl-4 pr-3 py-0.5 text-slate-600 select-none w-12 text-right shrink-0">
                      {line.line_number}
                    </td>
                    <td className={`pr-4 py-0.5 whitespace-pre-wrap break-all ${lineClass(line.text)}`}>
                      {line.text || <span className="text-slate-700">{'(blank)'}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length > maxVisible && !showAll && (
            <button
              onClick={() => setShowAll(true)}
              className="w-full py-2 text-xs text-indigo-400 hover:text-indigo-300 border-t border-slate-800 transition-colors"
            >
              Show {filtered.length - maxVisible} more lines…
            </button>
          )}
          {filtered.length === 0 && search && (
            <p className="px-4 py-4 text-xs text-slate-500 text-center">No lines match "{search}"</p>
          )}
        </div>
      )}
    </div>
  );
};
