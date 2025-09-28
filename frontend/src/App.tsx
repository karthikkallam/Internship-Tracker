import { useCallback, useEffect, useMemo, useState } from 'react';
import JobCard from './components/JobCard';
import NotificationToast from './components/NotificationToast';
import { useWebSocket } from './hooks/useWebSocket';
import { Job, ToastMessage } from './types';

const resolveApiBase = (): string => {
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;
  if (envUrl) {
    return envUrl.replace(/\/$/, '');
  }
  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return 'http://localhost:8000';
};

const API_BASE = resolveApiBase();
const WS_BASE = (() => {
  const envWs = (import.meta.env.VITE_WS_URL as string | undefined)?.replace(/\/$/, '');
  if (envWs) {
    return envWs;
  }
  try {
    const url = new URL(API_BASE);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = '/ws';
    return url.toString().replace(/\/$/, '');
  } catch {
    return 'ws://localhost:8000/ws';
  }
})();

const MAX_JOBS = 200;
const MAX_TOASTS = 4;

function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadJobs = async () => {
      setIsLoading(true);
      try {
        const response = await fetch(`${API_BASE}/jobs?limit=${MAX_JOBS}`);
        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }
        const payload = (await response.json()) as Job[];
        if (!cancelled) {
          setJobs(payload ?? []);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Failed to fetch jobs', err);
          setError('Unable to load internships right now.');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadJobs();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleIncomingJob = useCallback((job: Job) => {
    setJobs((prev) => {
      if (prev.some((existing) => existing.id === job.id)) {
        return prev;
      }
      return [job, ...prev].slice(0, MAX_JOBS);
    });

    setToasts((prev) => {
      const updated = [{
        id: String(job.id),
        title: job.title,
        description: `${job.company}${job.location ? ` • ${job.location}` : ''}`,
        url: job.url
      }, ...prev];
      return updated.slice(0, MAX_TOASTS);
    });
  }, []);

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload?.type === 'job' && payload?.data) {
          handleIncomingJob(payload.data as Job);
        }
      } catch (err) {
        console.error('Unable to parse websocket message', err);
      }
    },
    [handleIncomingJob]
  );

  const { readyState } = useWebSocket(WS_BASE, { onMessage: handleMessage });

  const connectionStatus = useMemo(() => {
    switch (readyState) {
      case WebSocket.OPEN:
        return { label: 'Live updates', color: 'bg-emerald-500/80' };
      case WebSocket.CONNECTING:
        return { label: 'Connecting…', color: 'bg-amber-400/80' };
      default:
        return { label: 'Offline', color: 'bg-rose-500/80' };
    }
  }, [readyState]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="flex flex-col gap-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-widest text-brand-300/80">Internship Tracker</p>
              <h1 className="text-3xl font-bold text-slate-50 sm:text-4xl">Real-time internship feed</h1>
              <p className="text-sm text-slate-400">
                Aggregating internship postings from top ATS providers. Stay ready as soon as new roles go live.
              </p>
            </div>
            <div className="inline-flex items-center gap-2 self-start rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1 text-xs font-medium text-slate-200 shadow">
              <span className={`h-2 w-2 rounded-full ${connectionStatus.color}`} />
              {connectionStatus.label}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
              <p className="text-xs uppercase tracking-widest text-slate-500">Total roles</p>
              <p className="mt-1 text-2xl font-semibold text-slate-100">{jobs.length}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
              <p className="text-xs uppercase tracking-widest text-slate-500">Websocket</p>
              <p className="mt-1 text-2xl font-semibold text-slate-100">{connectionStatus.label}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
              <p className="text-xs uppercase tracking-widest text-slate-500">Sources</p>
              <p className="mt-1 text-2xl font-semibold text-slate-100">Greenhouse · Lever · Ashby · SmartRecruiters · Recruitee</p>
            </div>
          </div>
        </header>

        <main className="flex-1">
          {isLoading ? (
            <div className="flex items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/60 py-20 text-slate-400">
              Loading internships…
            </div>
          ) : error ? (
            <div className="flex items-center justify-center rounded-2xl border border-rose-500/40 bg-rose-950/20 py-12 text-rose-200">
              {error}
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/60 py-20 text-slate-400">
              No internships found yet. Check back soon!
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {jobs.map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
            </div>
          )}
        </main>
      </div>

      <NotificationToast toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default App;
