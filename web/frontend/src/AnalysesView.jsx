import { useEffect, useMemo, useRef, useState } from 'react';

function fmtDuration(secs) {
  if (secs == null) return '';
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}m ${s}s`;
}

function StatusBadge({ status }) {
  const colors = {
    pending: 'bg-gray-200 text-gray-700',
    running: 'bg-blue-100 text-blue-800',
    done: 'bg-green-100 text-green-800',
    error: 'bg-red-100 text-red-800',
  };
  return (
    <span className={`px-2 py-0.5 text-xs rounded font-medium ${colors[status] || ''}`}>
      {status}
    </span>
  );
}

export default function AnalysesView() {
  const [analyses, setAnalyses] = useState([]);
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState(null);
  const [job, setJob] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(null);

  useEffect(() => {
    fetch('/api/analyses')
      .then((r) => r.json())
      .then(setAnalyses)
      .catch(() => setAnalyses([]));
  }, []);

  useEffect(() => {
    if (!job) return;
    if (job.status === 'done' || job.status === 'error') return;
    const poll = setInterval(async () => {
      try {
        const r = await fetch(`/api/jobs/${job.id}`);
        setJob(await r.json());
      } catch {
        /* ignore */
      }
    }, 1000);
    return () => clearInterval(poll);
  }, [job]);

  useEffect(() => {
    if (job && job.status === 'running') {
      if (startRef.current == null) startRef.current = Date.now();
      const t = setInterval(() => setElapsed((Date.now() - startRef.current) / 1000), 200);
      return () => clearInterval(t);
    }
    startRef.current = null;
    setElapsed(0);
  }, [job]);

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    return analyses.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        a.name.toLowerCase().includes(q)
    );
  }, [analyses, filter]);

  const runAnalysis = async () => {
    if (!selected) return;
    setJob(null);
    const r = await fetch(`/api/analyses/${selected.name}/run`, { method: 'POST' });
    if (!r.ok) {
      setJob({ id: 'local', status: 'error', error: `Failed to start: ${r.status}`, output_files: {} });
      return;
    }
    setJob(await r.json());
  };

  const isRunning = job && (job.status === 'pending' || job.status === 'running');

  return (
    <div className="flex h-full">
      <aside className="w-96 border-r bg-white flex flex-col">
        <div className="p-4 border-b">
          <p className="text-xs text-gray-500">{analyses.length} analyses available</p>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter analyses..."
            className="mt-2 w-full px-3 py-1.5 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <ul className="overflow-y-auto flex-1">
          {filtered.map((a) => (
            <li key={a.name}>
              <button
                onClick={() => setSelected(a)}
                className={`w-full text-left p-3 hover:bg-gray-50 border-b ${
                  selected?.name === a.name ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
                }`}
              >
                <div className="font-medium text-sm">{a.title}</div>
                <div className="text-xs text-gray-500 mt-1 line-clamp-2">{a.description}</div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="flex-1 overflow-y-auto">
        {!selected && (
          <div className="h-full flex items-center justify-center text-gray-500">
            Select an analysis from the sidebar.
          </div>
        )}
        {selected && (
          <div className="p-8 max-w-5xl">
            <h2 className="text-2xl font-bold">{selected.title}</h2>
            <p className="text-gray-600 mt-1">{selected.description}</p>
            <code className="text-xs text-gray-400">{selected.name}</code>

            <div className="mt-6">
              <button
                onClick={runAnalysis}
                disabled={isRunning}
                className="px-5 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 font-medium"
              >
                {isRunning ? 'Running...' : 'Run analysis'}
              </button>
              {isRunning && <span className="ml-4 text-sm text-gray-600">Elapsed: {fmtDuration(elapsed)}</span>}
            </div>

            {job && (
              <div className="mt-6 bg-white border rounded-lg p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-3">
                  <StatusBadge status={job.status} />
                  <span className="text-xs text-gray-500">job {job.id}</span>
                  {job.duration_seconds != null && (
                    <span className="text-xs text-gray-500">took {fmtDuration(job.duration_seconds)}</span>
                  )}
                </div>
                {job.error && (
                  <pre className="text-xs text-red-700 whitespace-pre-wrap bg-red-50 p-3 rounded overflow-auto max-h-96">
                    {job.error}
                  </pre>
                )}
                {job.status === 'done' && (
                  <div>
                    {(job.output_files?.png || job.output_files?.gif) && (
                      <img
                        src={job.output_files.gif || job.output_files.png}
                        alt={selected.title}
                        className="max-w-full border rounded"
                      />
                    )}
                    <div className="mt-4 flex flex-wrap gap-2">
                      {Object.entries(job.output_files || {}).map(([fmt, url]) => (
                        <a
                          key={fmt}
                          href={url}
                          download
                          className="px-3 py-1 text-sm bg-gray-100 hover:bg-gray-200 border rounded text-gray-700"
                        >
                          {fmt.toUpperCase()}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
