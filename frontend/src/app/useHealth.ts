import { useEffect, useState } from 'react';
import { apiClient } from '../shared/api-client';

export type HealthState =
  { status: 'loading' } | { status: 'ok' } | { status: 'error'; message: string };

export function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ status: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    apiClient
      .get<unknown>('/api/v1/health', controller.signal)
      .then(() => setState({ status: 'ok' }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : 'Erro desconhecido.',
        });
      });
    return () => controller.abort();
  }, []);

  return state;
}
