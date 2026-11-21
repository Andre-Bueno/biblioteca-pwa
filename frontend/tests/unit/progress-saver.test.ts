import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createProgressSaver } from '../../src/shared/progress/progress-saver';

describe('createProgressSaver', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('debounces ~800 ms and sends only the last locator', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const saver = createProgressSaver({ save });
    saver.report(1);
    await vi.advanceTimersByTimeAsync(500);
    saver.report(2);
    await vi.advanceTimersByTimeAsync(500);
    expect(save).not.toHaveBeenCalled(); // the timer restarted at the second report
    await vi.advanceTimersByTimeAsync(400);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith(2, { keepalive: false });
  });

  it('flush(true) sends the pending value immediately with keepalive', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const saver = createProgressSaver({ save });
    saver.report(7);
    await saver.flush(true);
    expect(save).toHaveBeenCalledWith(7, { keepalive: true });
    await vi.advanceTimersByTimeAsync(2000);
    expect(save).toHaveBeenCalledTimes(1); // the debounce timer was cancelled
  });

  it('does not resend the baseline or an already saved locator', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const saver = createProgressSaver({ save });
    saver.setBaseline(4);
    saver.report(4);
    await vi.advanceTimersByTimeAsync(2000);
    expect(save).not.toHaveBeenCalled();
    saver.report(5);
    await vi.advanceTimersByTimeAsync(900);
    saver.report(5);
    await vi.advanceTimersByTimeAsync(2000);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('keeps reading alive on failure: reports error status and retries later', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValue(undefined);
    const statuses: string[] = [];
    const saver = createProgressSaver({ save, retryMs: 5000, onStatus: (s) => statuses.push(s) });
    saver.report(3);
    await vi.advanceTimersByTimeAsync(900);
    expect(statuses).toContain('error');
    await vi.advanceTimersByTimeAsync(5000);
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith(3, { keepalive: false });
    expect(statuses.at(-1)).toBe('idle');
  });

  it('a newer locator replaces the failed one', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValue(undefined);
    const saver = createProgressSaver({ save, retryMs: 5000 });
    saver.report(3);
    await vi.advanceTimersByTimeAsync(900);
    saver.report(8);
    await vi.advanceTimersByTimeAsync(900);
    expect(save).toHaveBeenLastCalledWith(8, { keepalive: false });
  });

  it('a keepalive flush never races an in-flight save: one at a time, newest value last', async () => {
    const releases: (() => void)[] = [];
    const order: { locator: number; keepalive: boolean }[] = [];
    let active = 0;
    let maxActive = 0;
    const save = vi.fn((locator: number, { keepalive }: { keepalive: boolean }) => {
      order.push({ locator, keepalive });
      active += 1;
      maxActive = Math.max(maxActive, active);
      return new Promise<void>((resolve) =>
        releases.push(() => {
          active -= 1;
          resolve();
        }),
      );
    });
    const saver = createProgressSaver({ save });

    saver.report(5);
    await vi.advanceTimersByTimeAsync(900); // PUT 5 is now in flight
    expect(save).toHaveBeenCalledTimes(1);

    saver.report(6);
    saver.report(7); // 6 is replaced: the latest value always wins
    const flushed = saver.flush(true); // page hidden while PUT 5 is still pending
    expect(save).toHaveBeenCalledTimes(1); // not raced

    releases[0]!();
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenCalledTimes(2);
    releases[1]!();
    await flushed;

    expect(order).toEqual([
      { locator: 5, keepalive: false },
      { locator: 7, keepalive: true },
    ]);
    expect(maxActive).toBe(1);
  });

  it('a flush requested right before dispose still sends the newest value after the in-flight one', async () => {
    const releases: (() => void)[] = [];
    const save = vi.fn<(locator: number, options: { keepalive: boolean }) => Promise<void>>(
      () => new Promise<void>((resolve) => releases.push(resolve)),
    );
    const saver = createProgressSaver({ save });
    saver.report(1);
    await vi.advanceTimersByTimeAsync(900);
    saver.report(2);
    void saver.flush(true);
    saver.dispose(); // reader unmounted
    releases[0]!();
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenLastCalledWith(2, { keepalive: true });
  });

  it('dispose stops everything', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const saver = createProgressSaver({ save });
    saver.report(1);
    saver.dispose();
    await vi.advanceTimersByTimeAsync(5000);
    expect(save).not.toHaveBeenCalled();
  });
});
