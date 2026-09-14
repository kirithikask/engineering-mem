import { useCallback, useEffect, useState } from 'react';
import api from '../services/api';

/**
 * Live platform status, read from the backend health endpoint.
 *
 * Everything surfaced here is reported by the server (database engine, indexed
 * vector count, whether the local reasoning model answered). Nothing is assumed
 * on the client, so the status strip cannot claim a capability that is down.
 */
export default function useSystemStatus(pollMs = 30000) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const res = await api.get('/health');
      setStatus(res);
      setError(null);
    } catch (err) {
      setStatus(null);
      setError('Platform services unreachable');
    }
  }, []);

  useEffect(() => {
    refresh();
    if (!pollMs) return undefined;
    const timer = setInterval(refresh, pollMs);
    return () => clearInterval(timer);
  }, [refresh, pollMs]);

  const models = status?.models_loaded || {};
  return {
    status,
    error,
    refresh,
    databaseOnline: Boolean(status),
    aiEngineOnline: Boolean(models.qwen_ollama),
    retrievalOnline: Boolean(models.faiss_index),
    sensorModelOnline: Boolean(models.sensor_rf_classifier),
    vectorCount: status?.faiss_vectors ?? null,
    databaseEngine: status?.database || null,
    warnings: status?.warnings || [],
  };
}
