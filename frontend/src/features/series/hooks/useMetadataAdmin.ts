import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../../shared/api-client';
import { useCountdown } from '../../../shared/hooks';
import {
  removeMetadata,
  saveMetadataText,
  searchMetadataCandidates,
  selectMetadata,
  type MetadataCandidate,
} from '../../../shared/series';

export const TITLE_MAX = 200;
export const DESCRIPTION_MAX = 4000;

export type CandidatesState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; items: MetadataCandidate[] }
  | { status: 'error' }
  | { status: 'rate-limited' };

export interface Feedback {
  kind: 'success' | 'error';
  text: string;
}

/** Search + manual actions of the admin metadata panel. Messages never expose technical details. */
export function useMetadataAdmin(seriesId: string, onChanged: () => void) {
  const [candidates, setCandidates] = useState<CandidatesState>({ status: 'idle' });
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const countdown = useCountdown();
  const searchAbort = useRef<AbortController | null>(null);
  const inflight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      searchAbort.current?.abort();
    };
  }, []);

  const search = useCallback(
    async (query: string) => {
      const q = query.trim();
      if (!q || inflight.current || countdown.remaining > 0) return;
      inflight.current = true;
      searchAbort.current?.abort();
      const controller = new AbortController();
      searchAbort.current = controller;
      setFeedback(null);
      setCandidates({ status: 'loading' });
      try {
        const items = await searchMetadataCandidates(seriesId, q, controller.signal);
        if (!controller.signal.aborted) setCandidates({ status: 'ready', items });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 429) {
          countdown.start(error.retryAfterSeconds ?? 30);
          setCandidates({ status: 'rate-limited' });
        } else {
          setCandidates({ status: 'error' });
        }
      } finally {
        inflight.current = false;
      }
    },
    [seriesId, countdown],
  );

  const run = useCallback(
    async (action: () => Promise<unknown>, success: string, failure: string) => {
      if (inflight.current) return false;
      inflight.current = true;
      setBusy(true);
      setFeedback(null);
      try {
        await action();
        if (!mounted.current) return true;
        setFeedback({ kind: 'success', text: success });
        onChanged();
        return true;
      } catch {
        if (mounted.current) setFeedback({ kind: 'error', text: failure });
        return false;
      } finally {
        inflight.current = false;
        if (mounted.current) setBusy(false);
      }
    },
    [onChanged],
  );

  const choose = useCallback(
    (candidate: MetadataCandidate) =>
      run(
        () =>
          selectMetadata(seriesId, {
            provider: candidate.provider,
            external_id: candidate.external_id,
          }),
        'Metadados aplicados.',
        'Não foi possível aplicar estes metadados.',
      ),
    [run, seriesId],
  );

  const saveText = useCallback(
    (title: string, description: string) =>
      run(
        () => saveMetadataText(seriesId, { title: title.trim(), description }),
        'Texto salvo.',
        'Não foi possível salvar o texto.',
      ),
    [run, seriesId],
  );

  const remove = useCallback(
    () =>
      run(
        () => removeMetadata(seriesId),
        'Metadados removidos.',
        'Não foi possível remover os metadados.',
      ),
    [run, seriesId],
  );

  return {
    candidates,
    busy,
    feedback,
    retryIn: countdown.remaining,
    search,
    choose,
    saveText,
    remove,
  };
}
