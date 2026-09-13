"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent, RefObject } from "react";

/** Commit a swipe past this fraction of the stage width… */
const DISTANCE_RATIO = 0.18;
/** …or above this flick velocity in px/ms, whichever happens first. */
const VELOCITY = 0.4;
/** Vertical intent beyond this abandons the horizontal gesture. */
const VERTICAL_SLOP = 12;

type Drag = { pointerId: number; startX: number; startY: number; startedAt: number };

export type StackSwipe = {
  /** Attach to the element that owns the gesture; also the width reference. */
  stageRef: RefObject<HTMLDivElement | null>;
  /** Measured stage width — how far a card travels to leave the screen. */
  step: number;
  /** Live pointer offset in px, 0 when at rest. */
  dragX: number;
  dragging: boolean;
  handlers: {
    onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
    onPointerDown: (event: PointerEvent<HTMLDivElement>) => void;
    onPointerMove: (event: PointerEvent<HTMLDivElement>) => void;
    onPointerUp: (event: PointerEvent<HTMLDivElement>) => void;
    onPointerCancel: () => void;
  };
};

/**
 * The shared physics behind every card deck in the app.
 *
 * It owns only the gesture — pointer capture, the rubber band at the ends of a
 * deck, the distance/velocity commit thresholds and arrow-key stepping — and
 * reports how far the pointer has travelled. What a deck *is* (a stack of
 * categories, a stack of patients), how its cards are laid out and what they
 * contain stay with the component that calls this.
 *
 * Direction is the standard physical model:
 *
 *   swipe LEFT  → the current card travels LEFT  and the NEXT card
 *                 arrives from the RIGHT
 *   swipe RIGHT → the current card travels RIGHT and the PREVIOUS card
 *                 arrives from the LEFT
 */
export function useStackSwipe({
  index,
  count,
  onMove,
}: {
  /** Index of the card currently in front. */
  index: number;
  /** How many cards the deck holds. */
  count: number;
  /** Called with +1 to advance and -1 to go back; ends are already clamped. */
  onMove: (delta: number) => void;
}): StackSwipe {
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);
  const [dragX, setDragX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [step, setStep] = useState(0);

  const last = count - 1;

  // A card travels the full stage width, so it clears the viewport entirely
  // instead of stopping half-way over what stands behind it.
  useEffect(() => {
    const element = stageRef.current;
    if (!element) return;
    const measure = () => setStep(element.getBoundingClientRect().width);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const move = useCallback(
    (delta: number) => {
      const next = index + delta;
      if (next >= 0 && next < count) onMove(delta);
    },
    [index, count, onMove],
  );

  const endDrag = useCallback(() => {
    dragRef.current = null;
    setDragging(false);
    setDragX(0);
  }, []);

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    // Controls inside the deck keep their own behaviour.
    if (event.target instanceof Element && event.target.closest("button, a")) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startedAt: event.timeStamp || performance.now(),
    };
    setDragging(true);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;

    // Let the page scroll if the gesture is clearly vertical.
    if (Math.abs(dy) > VERTICAL_SLOP && Math.abs(dy) > Math.abs(dx)) {
      endDrag();
      return;
    }
    if (Math.abs(dx) < 2) return;

    try {
      if (!stageRef.current?.hasPointerCapture(event.pointerId)) {
        stageRef.current?.setPointerCapture(event.pointerId);
      }
    } catch {
      /* pointer capture is an enhancement, not a requirement */
    }

    // Resist past the ends of the deck instead of tearing free.
    const atStart = index === 0 && dx > 0;
    const atEnd = index === last && dx < 0;
    setDragX(atStart || atEnd ? dx * 0.32 : dx);
  }

  function handlePointerUp(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    const dx = event.clientX - drag.startX;
    const elapsed = Math.max(1, (event.timeStamp || performance.now()) - drag.startedAt);
    const velocity = Math.abs(dx) / elapsed;
    const threshold = (step || 320) * DISTANCE_RATIO;

    endDrag();
    if (Math.abs(dx) < 6) return;
    if (Math.abs(dx) < threshold && velocity < VELOCITY) return;
    move(dx < 0 ? 1 : -1);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
    }
  }

  return {
    stageRef,
    step,
    dragX,
    dragging,
    handlers: {
      onKeyDown: handleKeyDown,
      onPointerDown: handlePointerDown,
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
      onPointerCancel: endDrag,
    },
  };
}
