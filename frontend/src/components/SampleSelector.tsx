import React from 'react';
import type { SampleInfo } from '../api';

interface SampleSelectorProps {
  samples: SampleInfo[];
  loading: boolean;
  onSelect: (id: string) => void;
  disabled?: boolean;
}

export const SampleSelector: React.FC<SampleSelectorProps> = ({
  samples, loading, onSelect, disabled,
}) => {
  if (loading) {
    return (
      <div className="flex gap-2 flex-wrap">
        {[1, 2, 3].map((n) => (
          <div key={n} className="h-8 w-36 rounded-lg bg-slate-800 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Try a sample log</p>
      <div className="flex gap-2 flex-wrap">
        {samples.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            disabled={disabled}
            title={s.description}
            className="px-3 py-1.5 rounded-lg border border-slate-700 text-xs font-medium text-slate-300
              hover:border-indigo-500 hover:text-indigo-300 hover:bg-slate-900 transition-all
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {s.name}
          </button>
        ))}
      </div>
    </div>
  );
};
