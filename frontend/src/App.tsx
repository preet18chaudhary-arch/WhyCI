
import { useCallback, useEffect, useState } from 'react';
import {
  analyzeDemo,
  analyzeUpload,
  fetchSamples,
  fetchHistory,
  clearHistory,
} from './api';
import type { AnalysisResponse, SampleInfo, HistoryItem } from './api';
import { DropZone } from './components/DropZone';
import { SampleSelector } from './components/SampleSelector';
import { AnalysisResult } from './components/AnalysisResult';

type AppState =
  | { kind: 'idle' }
  | { kind: 'loading'; label: string }
  | { kind: 'result'; data: AnalysisResponse }
  | { kind: 'error'; message: string };

export default function App() {
  const [state, setState] = useState<AppState>({ kind: 'idle' });
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [samplesLoading, setSamplesLoading] = useState(true);

  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyMessage, setHistoryMessage] = useState('');
  const [clearingHistory, setClearingHistory] = useState(false);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryMessage('');

    try {
      const items = await fetchHistory();
      setHistory(items);
    } catch (error) {
      setHistoryMessage(
        error instanceof Error
          ? `History load nahi ho paayi: ${error.message}`
          : 'History load nahi ho paayi. Backend check karo.'
      );
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSamples()
      .then(setSamples)
      .catch(() => setSamples([]))
      .finally(() => setSamplesLoading(false));

    void refreshHistory();
  }, [refreshHistory]);

  const handleFile = async (file: File) => {
    const MAX = 10 * 1024 * 1024;

    if (file.size > MAX) {
      setState({
        kind: 'error',
        message: 'File exceeds the 10 MB limit. Please use a smaller log file.',
      });
      return;
    }

    const filename = file.name.toLowerCase();

    if (!filename.endsWith('.log') && !filename.endsWith('.txt')) {
      setState({
        kind: 'error',
        message: 'Only .log and .txt files are accepted.',
      });
      return;
    }

    setState({ kind: 'loading', label: file.name });

    try {
      const result = await analyzeUpload(file);
      setState({ kind: 'result', data: result });
      void refreshHistory();
    } catch (error) {
      setState({
        kind: 'error',
        message:
          error instanceof Error ? error.message : 'Analysis failed.',
      });
    }
  };

  const handleSample = async (id: string) => {
    const sample = samples.find((item) => item.id === id);

    setState({
      kind: 'loading',
      label: sample?.name ?? id,
    });

    try {
      const result = await analyzeDemo(id);
      setState({ kind: 'result', data: result });
      void refreshHistory();
    } catch (error) {
      setState({
        kind: 'error',
        message:
          error instanceof Error ? error.message : 'Could not load sample.',
      });
    }
  };

  const handleClearHistory = async () => {
    if (clearingHistory || historyLoading || history.length === 0) {
      return;
    }

    const confirmed = window.confirm(
      'Kya aap poori analysis history delete karna chahte hain? Yeh action undo nahi ho sakta.'
    );

    if (!confirmed) return;

    setClearingHistory(true);
    setHistoryMessage('');

    try {
      const deleted = await clearHistory();
      setHistory([]);
      setHistoryMessage(`${deleted} history item(s) delete ho gaye.`);
    } catch (error) {
      setHistoryMessage(
        error instanceof Error
          ? `History delete nahi ho paayi: ${error.message}`
          : 'History delete nahi ho paayi.'
      );
    } finally {
      setClearingHistory(false);
    }
  };

  const reset = () => setState({ kind: 'idle' });
  const isLoading = state.kind === 'loading';

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center">
              <svg
                className="w-4 h-4 text-white"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <span className="font-bold text-slate-100 tracking-tight">
              WhyCI
            </span>
          </div>

          <nav className="flex items-center gap-4 text-xs text-slate-500">
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="hover:text-slate-300 transition-colors"
            >
              API docs
            </a>
            <a
              href="https://github.com/preet18chaudhary-arch/WhyCI"
              target="_blank"
              rel="noreferrer"
              className="hover:text-slate-300 transition-colors"
            >
              GitHub
            </a>
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 py-10">
        {state.kind !== 'result' && (
          <div className="mb-10">
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-100">
              Stop guessing.{' '}
              <span className="text-indigo-400">Start fixing.</span>
            </h1>
            <p className="mt-3 text-slate-400 max-w-xl text-sm leading-relaxed">
              WhyCI reads your CI log, redacts secrets, and uses a deterministic
              engine to rank the most likely root cause — with supporting
              evidence and exact line numbers. No AI required. No credentials
              needed.
            </p>
          </div>
        )}

        {state.kind !== 'result' && (
          <div className="space-y-6 mb-10">
            <div className="flex items-start gap-2.5 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
              <svg
                className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                />
              </svg>
              <p className="text-xs text-slate-400">
                <span className="text-emerald-400 font-semibold">
                  Privacy-first.
                </span>{' '}
                Secrets are redacted before analysis. Logs are processed in
                memory and never stored permanently. Regex-based detection
                cannot guarantee that all secrets are caught.
              </p>
            </div>

            <DropZone onFile={handleFile} disabled={isLoading} />

            <SampleSelector
              samples={samples}
              loading={samplesLoading}
              onSelect={handleSample}
              disabled={isLoading}
            />
          </div>
        )}

        <section className="mb-8 rounded-xl border border-slate-800 bg-slate-900/40 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-100">
                Analysis History
              </h2>
              <p className="mt-1 text-xs text-slate-400">
                Recent analyses yahan locally saved hain.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void refreshHistory()}
                disabled={historyLoading || clearingHistory}
                className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
              >
                {historyLoading ? 'Refreshing...' : 'Refresh'}
              </button>

              <button
                type="button"
                onClick={() => void handleClearHistory()}
                disabled={
                  clearingHistory || historyLoading || history.length === 0
                }
                className="rounded-lg border border-red-800 px-3 py-2 text-xs text-red-300 hover:bg-red-950/40 disabled:opacity-40"
              >
                {clearingHistory ? 'Clearing...' : 'Clear History'}
              </button>
            </div>
          </div>

          {historyLoading && (
            <p className="mt-4 text-xs text-slate-400" role="status">
              History load ho rahi hai...
            </p>
          )}

          {!historyLoading && historyMessage && (
            <p className="mt-4 text-xs text-amber-300" role="alert">
              {historyMessage}
            </p>
          )}

          {!historyLoading &&
            !historyMessage &&
            history.length === 0 && (
              <p className="mt-4 text-xs text-slate-500">
                Abhi koi saved analysis nahi hai.
              </p>
            )}

          {history.length > 0 && (
            <ul className="mt-4 space-y-2">
              {history.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 p-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-slate-200 break-words">
                      {item.source_name}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {item.error_count} errors · {item.warning_count} warnings
                      {' · '}
                      {item.created_at}
                    </p>
                  </div>

                  {item.repeat_detected && (
                    <span className="rounded-md bg-amber-950/50 px-2 py-1 text-xs text-amber-300">
                      Repeat ×{item.repeat_count}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {state.kind === 'loading' && (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div className="w-10 h-10 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
            <div className="text-center">
              <p className="text-sm font-medium text-slate-300">
                Analysing {state.label}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Redacting secrets · classifying signals · ranking candidates
              </p>
            </div>
          </div>
        )}

        {state.kind === 'error' && (
          <div className="rounded-xl border border-red-800 bg-red-950/30 p-6">
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 text-red-400 shrink-0 mt-0.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.96-.833-2.732 0L4.072 16.5c-.77.833.192 2.5 1.732 2.5z"
                />
              </svg>
              <div>
                <p className="text-sm font-semibold text-red-300">
                  Analysis failed
                </p>
                <p className="text-sm text-red-400 mt-1">{state.message}</p>
                <button
                  type="button"
                  onClick={reset}
                  className="mt-3 text-xs text-red-300 hover:text-red-200 underline underline-offset-2"
                >
                  Try again
                </button>
              </div>
            </div>
          </div>
        )}

        {state.kind === 'result' && (
          <AnalysisResult result={state.data} onReset={reset} />
        )}
      </main>

      <footer className="border-t border-slate-900 mt-auto">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-5 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <span>WhyCI — deterministic CI failure diagnosis</span>
          <span>
            Scores are heuristic priority weights, not AI confidence and not a
            guaranteed root cause.
          </span>
        </div>
      </footer>
    </div>
  );
}
