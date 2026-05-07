import { useState } from 'react';
import AnalysesView from './AnalysesView.jsx';
import TradingView from './TradingView.jsx';

const TABS = [
  { id: 'analyses', label: 'Analyses' },
  { id: 'trading', label: 'Trading (Backtest)' },
];

export default function App() {
  const [tab, setTab] = useState('analyses');

  return (
    <div className="flex flex-col h-screen bg-gray-50 text-gray-900">
      <header className="border-b bg-white px-6 py-3 flex items-center gap-6">
        <h1 className="font-bold text-lg">Prediction Market Analysis</h1>
        <nav className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 text-sm rounded ${
                tab === t.id ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <div className="flex-1 overflow-hidden">
        {tab === 'analyses' && <AnalysesView />}
        {tab === 'trading' && <TradingView />}
      </div>
    </div>
  );
}
