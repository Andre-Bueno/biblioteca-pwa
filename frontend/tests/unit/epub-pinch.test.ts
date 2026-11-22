import { describe, expect, it } from 'vitest';
import {
  PINCH_SETTLE_MS,
  PINCH_STALE_MS,
  RESIZE_HOLD_MS,
  USER_SCROLL_MS,
  createPinchGuard,
  createReflowHold,
} from '../../src/features/reader/epub/pinch';

describe('createPinchGuard', () => {
  it('is not blocked before any touch, nor for a single finger', () => {
    const guard = createPinchGuard();
    expect(guard.blocked(0)).toBe(false);
    guard.start(1, 0);
    guard.touches(1, 10);
    expect(guard.blocked(20)).toBe(false);
  });

  it('blocks while two fingers are down and for PINCH_SETTLE_MS after the last one lifts', () => {
    const guard = createPinchGuard();
    guard.start(2, 0);
    expect(guard.blocked(100)).toBe(true);
    guard.touches(1, 200); // one finger left: still the same gesture
    expect(guard.blocked(300)).toBe(true);
    guard.touches(0, 400);
    expect(guard.blocked(400 + PINCH_SETTLE_MS - 1)).toBe(true);
    expect(guard.blocked(400 + PINCH_SETTLE_MS)).toBe(false);
  });

  it('touchcancel (reset) clears a pinch at once', () => {
    const guard = createPinchGuard();
    guard.start(2, 0);
    guard.reset();
    expect(guard.blocked(1)).toBe(false);
    expect(guard.remaining(1)).toBe(0);
  });

  it('a one-finger touchstart ends a pinch whose touchend was lost', () => {
    const guard = createPinchGuard();
    guard.start(2, 0);
    guard.touches(2, 50);
    guard.start(1, 100);
    expect(guard.blocked(101)).toBe(false);
  });

  it('a pinch with no touch event for more than PINCH_STALE_MS expires', () => {
    const guard = createPinchGuard();
    guard.start(2, 0);
    expect(guard.blocked(PINCH_STALE_MS)).toBe(true);
    expect(guard.blocked(PINCH_STALE_MS + 1)).toBe(false);
  });

  it('remaining tells when the block is over', () => {
    const guard = createPinchGuard();
    guard.start(2, 0);
    guard.touches(0, 100);
    expect(guard.remaining(200)).toBe(PINCH_SETTLE_MS - 100);
    expect(guard.remaining(100 + PINCH_SETTLE_MS)).toBe(0);
  });
});

describe('createReflowHold', () => {
  it('holds on a width change only', () => {
    const hold = createReflowHold(400);
    expect(hold.onResize(400, 1000)).toBe(false); // height-only
    expect(hold.active(1000)).toBe(false);
    expect(hold.onResize(800, 1000)).toBe(true);
    expect(hold.active(1000 + RESIZE_HOLD_MS - 1)).toBe(true);
    expect(hold.active(1000 + RESIZE_HOLD_MS)).toBe(false);
  });

  it('a user scroll ends the hold and a resize right after it does not hold', () => {
    const hold = createReflowHold(400);
    hold.onResize(800, 1000);
    hold.userMoved(1100);
    expect(hold.active(1100)).toBe(false);
    expect(hold.onResize(500, 1100 + USER_SCROLL_MS - 1)).toBe(false);
    expect(hold.onResize(300, 1100 + USER_SCROLL_MS + 1000)).toBe(true);
  });

  it('extend lengthens an active hold only', () => {
    const hold = createReflowHold(400);
    hold.extend(0);
    expect(hold.active(1)).toBe(false);
    hold.onResize(800, 0);
    hold.extend(RESIZE_HOLD_MS - 10);
    expect(hold.active(RESIZE_HOLD_MS + 100)).toBe(true);
  });
});
