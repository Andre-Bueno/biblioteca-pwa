import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api-client';
import { getVersion, requestUpdate } from './api';
import { versionOfTag } from './types';
import { useVersion } from './useVersion';

export type UpdatePhase = 'idle' | 'confirming' | 'sending' | 'requested' | 'done' | 'timeout';

export const POLL_MS = 5000;
/** About 5 minutes of polling. */
export const POLL_MAX_TICKS = 60;

function messageFor(error: unknown): string {
  const status = error instanceof ApiError ? error.status : 0;
  if (status === 503) return 'O servidor não está configurado para atualizar automaticamente.';
  if (status === 502)
    return 'Não foi possível acionar a atualização no servidor. Tente mais tarde.';
  if (status === 429) return 'Muitas tentativas. Aguarde um pouco e tente de novo.';
  return 'Não foi possível solicitar a atualização agora.';
}

/**
 * The admin's update flow: confirm, ask the server (which calls its deploy webhook), then poll
 * `/system/version` until `current` is the requested version. Polling stops when the component
 * leaves the screen, tolerates network failures (the container restarts) and gives up after
 * about 5 minutes (the update keeps running on the server).
 */
export function useUpdateFlow() {
  const { info, applyInfo, dismiss, dismissedTag } = useVersion();
  const [phase, setPhase] = useState<UpdatePhase>('idle');
  const [target, setTarget] = useState<{ tag: string; version: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notesOpen, setNotesOpen] = useState(false);
  const unmounted = useRef(new AbortController());

  useEffect(() => {
    const controller = new AbortController();
    unmounted.current = controller;
    return () => controller.abort();
  }, []);

  // The server may already be running an update (the page was reloaded meanwhile).
  const serverTag = info?.update.state === 'requested' ? info.update.tag : null;
  const effectiveTarget =
    target ?? (serverTag ? { tag: serverTag, version: versionOfTag(serverTag) } : null);
  const effectivePhase: UpdatePhase = phase === 'idle' && serverTag ? 'requested' : phase;

  const targetVersion = effectiveTarget?.version ?? null;
  useEffect(() => {
    if (effectivePhase !== 'requested' || targetVersion === null) return undefined;
    const controller = new AbortController();
    let ticks = 0;
    const timer = setInterval(() => {
      ticks += 1;
      if (ticks > POLL_MAX_TICKS) {
        clearInterval(timer);
        setPhase('timeout');
        return;
      }
      getVersion(controller.signal)
        .then((next) => {
          if (controller.signal.aborted) return;
          if (next.current === targetVersion) {
            clearInterval(timer);
            applyInfo(next);
            setPhase('done');
          } else if (next.update.state === 'failed') {
            clearInterval(timer);
            setTarget(null);
            setPhase('idle');
            setError('A atualização falhou no servidor.');
          }
        })
        .catch(() => undefined); // the app is restarting: just try again on the next tick
    }, POLL_MS);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [effectivePhase, targetVersion, applyInfo]);

  const ask = useCallback(() => {
    setError(null);
    setPhase('confirming');
  }, []);
  const cancel = useCallback(() => setPhase('idle'), []);

  const tag = info?.latest?.tag ?? null;
  const confirm = useCallback(async () => {
    if (!tag) return;
    setError(null);
    setPhase('sending');
    const signal = unmounted.current.signal;
    try {
      const result = await requestUpdate(tag, signal);
      if (signal.aborted) return;
      setTarget({ tag: result.tag, version: versionOfTag(result.tag) });
      setPhase('requested');
    } catch (failure) {
      if (signal.aborted) return;
      if (failure instanceof ApiError && failure.status === 409) {
        setTarget({ tag, version: versionOfTag(tag) });
        setError('A atualização já foi solicitada. Acompanhando o progresso.');
        setPhase('requested');
        return;
      }
      setError(messageFor(failure));
      setPhase('idle');
    }
  }, [tag]);

  const toggleNotes = useCallback(() => setNotesOpen((value) => !value), []);
  const dismissNow = useCallback(() => {
    if (tag) dismiss(tag);
  }, [tag, dismiss]);

  const latest = info?.latest ?? null;
  const offered = !!info?.update_available && latest !== null && dismissedTag !== latest.tag;
  return {
    info,
    latest,
    phase: effectivePhase,
    /** Version the flow is waiting for / reached. */
    targetVersion,
    error,
    notesOpen,
    /** The banner shows for an offered update or while a flow is running/finished. */
    visible: offered || effectivePhase !== 'idle',
    ask,
    cancel,
    confirm,
    toggleNotes,
    dismiss: dismissNow,
  };
}
