import React, { useState } from 'react';
import { Play, Award, AlertTriangle } from 'lucide-react';
import api from '../services/api';

export default function Benchmark() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.get('/benchmark');
      setData(res);
    } catch (err) {
      setError('Benchmark could not run. Confirm the retrieval index is loaded.');
    } finally {
      setBusy(false);
    }
  };

  const summary = data?.benchmark_summary;
  const results = data?.detailed_results || [];
  const matchedTop3 = results.filter((r) => r.match_rank && r.match_rank <= 3).length;

  return (
    <div className="space-y-5">
      <div className="panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <span className="tech-label">Ground-truth retrieval suite</span>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-em-steel">
            Every figure below is measured on this machine against the current index. Recall and rank are
            computed from the actual retrieved order.
          </p>
        </div>
        <button onClick={run} disabled={busy} className="btn-amber">
          <Play className="h-3.5 w-3.5" />
          {busy ? 'Evaluating…' : 'Run suite'}
        </button>
      </div>

      {error && (
        <div className="panel border-l-2 border-l-em-fault p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-em-fault" />
            <p className="text-xs text-em-graphite">{error}</p>
          </div>
        </div>
      )}

      {!data && !busy && (
        <div className="panel p-10 text-center">
          <Award className="mx-auto h-8 w-8 text-em-line" />
          <p className="mt-3 text-sm font-semibold text-em-graphite">Suite ready</p>
          <p className="mx-auto mt-1 max-w-md text-xs text-em-steel">
            Run the suite to measure Recall@1/3/5, mean reciprocal rank and retrieval latency.
          </p>
        </div>
      )}

      {summary && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            {[
              ['Recall @ 1', `${(summary.recall_at_1 * 100).toFixed(1)}%`, 'Expected result ranked first'],
              ['Recall @ 3', `${(summary.recall_at_3 * 100).toFixed(1)}%`, 'Within top three'],
              ['Recall @ 5', `${(summary.recall_at_5 * 100).toFixed(1)}%`, 'Within top five'],
              ['MRR', summary.mrr, 'Mean reciprocal rank'],
              ['Mean retrieval latency', `${summary.mean_retrieval_latency_ms} ms`, 'Local index search'],
            ].map(([label, value, detail]) => (
              <div key={label} className="panel p-4">
                <span className="tech-label">{label}</span>
                <span className="tech-value tnum mt-1.5 block text-xl">{value}</span>
                <span className="mt-0.5 block text-2xs text-em-muted">{detail}</span>
              </div>
            ))}
          </div>

          <div className="panel">
            <div className="panel-head">
              <span className="tech-label">Per-query results</span>
              <span className="tech-value tnum">
                {summary.test_cases_evaluated} queries · {matchedTop3} matched in top three
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-em-panelDeep">
                  <tr>
                    {['Query', 'Expected component', 'Retrieved first', 'Similarity', 'Hit rank', 'Latency'].map(
                      (h) => (
                        <th key={h} className="tech-label px-3 py-2 font-semibold">
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-em-line">
                  {results.map((r) => (
                    <tr key={r.query} className="hover:bg-em-paper">
                      <td className="px-3 py-2 text-em-graphite">{r.query}</td>
                      <td className="px-3 py-2 text-em-graphite">{r.expected_component}</td>
                      <td className="px-3 py-2 text-em-steel">{r.retrieved_top1}</td>
                      <td className="px-3 py-2 font-mono tnum text-em-steel">
                        {(r.top1_similarity * 100).toFixed(1)}%
                      </td>
                      <td className="px-3 py-2">
                        {r.match_rank ? (
                          <span className={r.match_rank <= 3 ? 'chip-success' : 'chip-amber'}>
                            Rank {r.match_rank}
                          </span>
                        ) : (
                          <span className="chip-fault">No match in top 5</span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono tnum text-em-steel">{r.latency_ms} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="border-t border-em-line px-3 py-2.5 text-2xs leading-relaxed text-em-muted">
              Retrieval accuracy is limited by what the corpus actually records: where many cases share the
              same reported symptom but differ in recorded failure, the expected label is not separable from
              the text alone. Figures are reported as measured, without adjustment.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
