import { useEffect, useMemo, useState } from 'react';

const DEFAULT_PARAMS = {
  starting_cash: 1000,
  buy_below: 0.1,
  sell_above: 0.5,
  max_order_pct: '',
  max_position_pct: '',
  max_daily_loss_pct: '',
  start: '',
  end: '',
  tick_limit: '',
};

function fmt(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return '—';
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function MiniEquityChart({ points }) {
  if (!points || points.length < 2) return null;
  const w = 600;
  const h = 160;
  const ys = points.map((p) => p.equity);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const range = max - min || 1;
  const dx = w / (points.length - 1);
  const path = points
    .map((p, i) => {
      const x = i * dx;
      const y = h - ((p.equity - min) / range) * h;
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-40 border rounded bg-white">
      <path d={path} fill="none" stroke="#2563eb" strokeWidth="1.5" />
    </svg>
  );
}

export default function TradingView() {
  const [markets, setMarkets] = useState([]);
  const [marketFilter, setMarketFilter] = useState('');
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(DEFAULT_PARAMS);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('/api/markets?limit=100&min_trades=2000')
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then(setMarkets)
      .catch(async (r) => {
        const detail = r && r.text ? await r.text().catch(() => '') : '';
        setError(`Failed to load markets: ${detail || r}`);
      });
  }, []);

  useEffect(() => {
    if (!job) return;
    if (job.status === 'done' || job.status === 'error') return;
    const t = setInterval(async () => {
      try {
        const r = await fetch(`/api/backtests/${job.id}`);
        setJob(await r.json());
      } catch {
        /* ignore */
      }
    }, 1000);
    return () => clearInterval(t);
  }, [job]);

  const filteredMarkets = useMemo(() => {
    const q = marketFilter.toLowerCase();
    return markets.filter(
      (m) =>
        (m.question || '').toLowerCase().includes(q) ||
        (m.slug || '').toLowerCase().includes(q) ||
        (m.token_id || '').includes(q)
    );
  }, [markets, marketFilter]);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const canRun =
    selected &&
    form.max_order_pct !== '' &&
    form.max_position_pct !== '' &&
    form.max_daily_loss_pct !== '' &&
    !(job && (job.status === 'pending' || job.status === 'running'));

  const runBacktest = async () => {
    if (!selected) return;
    const payload = {
      condition_id: selected.condition_id || '',
      token_id: selected.token_id,
      question: selected.question || '(unnamed market)',
      end_date_iso: selected.end_date || null,
      start: form.start || null,
      end: form.end || null,
      starting_cash: Number(form.starting_cash),
      buy_below: Number(form.buy_below),
      sell_above: Number(form.sell_above),
      max_order_pct: Number(form.max_order_pct),
      max_position_pct: Number(form.max_position_pct),
      max_daily_loss_pct: Number(form.max_daily_loss_pct),
      tick_limit: form.tick_limit ? Number(form.tick_limit) : null,
    };
    const r = await fetch('/api/backtests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const detail = await r.text();
      setJob({ id: 'local', status: 'error', error: detail });
      return;
    }
    setJob(await r.json());
  };

  const result = job && job.status === 'done' ? job.result : null;

  return (
    <div className="flex h-full">
      <aside className="w-96 border-r bg-white flex flex-col">
        <div className="p-4 border-b">
          <p className="text-xs text-gray-500">{markets.length} markets (top by trade count)</p>
          <input
            value={marketFilter}
            onChange={(e) => setMarketFilter(e.target.value)}
            placeholder="Filter markets..."
            className="mt-2 w-full px-3 py-1.5 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {error && <div className="mt-2 text-xs text-red-600">{error}</div>}
        </div>
        <ul className="overflow-y-auto flex-1">
          {filteredMarkets.map((m) => (
            <li key={m.token_id}>
              <button
                onClick={() => setSelected(m)}
                className={`w-full text-left p-3 hover:bg-gray-50 border-b ${
                  selected?.token_id === m.token_id ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
                }`}
              >
                <div className="font-medium text-sm line-clamp-2">{m.question || '(unknown)'}</div>
                <div className="text-xs text-gray-500 mt-1">
                  {m.n_trades.toLocaleString()} trades · token {m.token_id.slice(0, 12)}…
                </div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="flex-1 overflow-y-auto">
        {!selected && (
          <div className="h-full flex items-center justify-center text-gray-500 text-center px-6">
            <div>
              <div className="text-lg">Select a market to backtest</div>
              <div className="text-sm mt-2">
                Risk caps must be set explicitly — there are no defaults.
              </div>
            </div>
          </div>
        )}

        {selected && (
          <div className="p-8 max-w-4xl space-y-6">
            <div>
              <h2 className="text-xl font-bold">{selected.question || '(unknown market)'}</h2>
              <code className="text-xs text-gray-500 break-all">
                token={selected.token_id}
                {selected.condition_id ? ` · cond=${selected.condition_id}` : ''}
              </code>
            </div>

            <section className="bg-white border rounded p-5 space-y-4">
              <h3 className="font-semibold">Strategy: threshold</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <label>
                  <span className="block text-gray-600">Starting cash (USDC)</span>
                  <input
                    type="number"
                    value={form.starting_cash}
                    onChange={update('starting_cash')}
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
                <label>
                  <span className="block text-gray-600">Tick limit (blank = all)</span>
                  <input
                    type="number"
                    value={form.tick_limit}
                    onChange={update('tick_limit')}
                    placeholder="e.g. 50000"
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
                <label>
                  <span className="block text-gray-600">Buy below price</span>
                  <input
                    type="number"
                    step="0.01"
                    value={form.buy_below}
                    onChange={update('buy_below')}
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
                <label>
                  <span className="block text-gray-600">Sell above price</span>
                  <input
                    type="number"
                    step="0.01"
                    value={form.sell_above}
                    onChange={update('sell_above')}
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
                <label>
                  <span className="block text-gray-600">Date start (ISO, optional)</span>
                  <input
                    type="text"
                    value={form.start}
                    onChange={update('start')}
                    placeholder="2024-01-01"
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
                <label>
                  <span className="block text-gray-600">Date end (ISO, optional)</span>
                  <input
                    type="text"
                    value={form.end}
                    onChange={update('end')}
                    placeholder="2024-12-31"
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
              </div>
            </section>

            <section className="bg-amber-50 border border-amber-200 rounded p-5 space-y-3">
              <h3 className="font-semibold text-amber-900">
                Risk caps <span className="text-xs font-normal">(required, no defaults)</span>
              </h3>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <label>
                  <span className="block text-gray-700">Max order % (0–1)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    value={form.max_order_pct}
                    onChange={update('max_order_pct')}
                    placeholder="0.05"
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
                <label>
                  <span className="block text-gray-700">Max position % (0–1)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    value={form.max_position_pct}
                    onChange={update('max_position_pct')}
                    placeholder="0.20"
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
                <label>
                  <span className="block text-gray-700">Max daily loss % (0–1)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    value={form.max_daily_loss_pct}
                    onChange={update('max_daily_loss_pct')}
                    placeholder="0.10"
                    className="mt-1 w-full px-2 py-1 border rounded"
                  />
                </label>
              </div>
            </section>

            <button
              onClick={runBacktest}
              disabled={!canRun}
              className="px-5 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 font-medium"
            >
              {job && (job.status === 'pending' || job.status === 'running')
                ? 'Running backtest...'
                : 'Run backtest'}
            </button>

            {job && (
              <section className="bg-white border rounded p-5">
                <div className="text-sm mb-3">
                  Status: <strong>{job.status}</strong>
                  {job.duration_seconds != null && (
                    <span className="ml-3 text-gray-500">{job.duration_seconds.toFixed(1)}s</span>
                  )}
                </div>
                {job.error && (
                  <pre className="text-xs text-red-700 whitespace-pre-wrap bg-red-50 p-3 rounded overflow-auto max-h-96">
                    {job.error}
                  </pre>
                )}
                {result && (
                  <div className="space-y-4">
                    {result.error && (
                      <div className="text-sm text-amber-800 bg-amber-50 p-3 rounded">
                        {result.error}
                      </div>
                    )}
                    <div className="grid grid-cols-4 gap-3 text-sm">
                      <Stat label="Final equity" value={`$${fmt(result.final_equity)}`} />
                      <Stat
                        label="P&L"
                        value={`$${fmt(result.pnl)}`}
                        tone={result.pnl >= 0 ? 'pos' : 'neg'}
                      />
                      <Stat
                        label="Return"
                        value={`${fmt(result.return_pct)}%`}
                        tone={result.return_pct >= 0 ? 'pos' : 'neg'}
                      />
                      <Stat label="Trade ticks" value={fmt(result.n_trade_ticks, 0)} />
                      <Stat label="Orders" value={fmt(result.n_orders, 0)} />
                      <Stat label="Fills" value={fmt(result.n_fills, 0)} />
                    </div>
                    <MiniEquityChart points={result.equity_curve} />
                    {result.stats && Object.keys(result.stats).length > 0 && (
                      <details className="text-xs">
                        <summary className="cursor-pointer text-gray-600">Performance stats</summary>
                        <pre className="mt-2 bg-gray-50 p-2 rounded overflow-auto">
                          {JSON.stringify(result.stats, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function Stat({ label, value, tone }) {
  const color =
    tone === 'pos' ? 'text-green-700' : tone === 'neg' ? 'text-red-700' : 'text-gray-900';
  return (
    <div className="border rounded p-3 bg-gray-50">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`mt-1 font-semibold ${color}`}>{value}</div>
    </div>
  );
}
