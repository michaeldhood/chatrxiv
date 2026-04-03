"use client";

import { useCallback, useEffect, useRef, useState } from 'react';

export interface OutlineItem {
  id: string;
  label: string;
  userIndex: number;
}

interface ChatOutlineRailProps {
  items: OutlineItem[];
  activeIndex: number;
  onSelect: (userIndex: number) => void;
  onActiveChange: (userIndex: number) => void;
}

/**
 * Notion-style document outline rail.
 *
 * Renders a fixed right-edge "ruler" with a tick mark per user message
 * placed at a proportional document position (minimap coordinates).
 * Hovering (fine pointer) or tapping (coarse/touch) reveals a scrollable
 * outline panel to the left. Updates the active index via scrollspy as the
 * user scrolls the page.
 */
export function ChatOutlineRail({
  items,
  activeIndex,
  onSelect,
  onActiveChange,
}: ChatOutlineRailProps) {
  // Proportional document positions (0–1) for each tick.
  const [tickPositions, setTickPositions] = useState<number[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  // Whether the device has a fine pointer that supports hover.
  const [hasHover, setHasHover] = useState(false);

  const rafRef = useRef<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setHasHover(window.matchMedia('(hover: hover) and (pointer: fine)').matches);
  }, []);

  // Measure each anchor's document Y, normalized by total scroll height.
  // The resulting proportion drives the tick's `top` % within the fixed
  // rail — so tick at 50% → 50vh, matching a document-midpoint anchor.
  const measure = useCallback(() => {
    const docHeight = document.documentElement.scrollHeight;
    if (docHeight === 0 || items.length === 0) return;

    const newPositions = items.map((item) => {
      const el = document.getElementById(item.id);
      if (!el) return 0;
      const docY = el.getBoundingClientRect().top + window.scrollY;
      // Clamp so ticks never clip past the rail edges.
      return Math.min(0.97, Math.max(0.03, docY / docHeight));
    });
    setTickPositions(newPositions);
  }, [items]);

  // Re-measure after layout settles (fonts, images, filter changes).
  useEffect(() => {
    const t = setTimeout(measure, 150);
    return () => clearTimeout(t);
  }, [measure]);

  useEffect(() => {
    window.addEventListener('resize', measure, { passive: true });
    return () => window.removeEventListener('resize', measure);
  }, [measure]);

  // Scrollspy: pick the user message whose top is nearest above 20% of viewport.
  useEffect(() => {
    const onScroll = () => {
      if (rafRef.current !== null) return;
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        const threshold = window.innerHeight * 0.2;
        let found = 0;
        for (let i = 0; i < items.length; i++) {
          const el = document.getElementById(items[i].id);
          if (!el) continue;
          if (el.getBoundingClientRect().top <= threshold) found = i;
        }
        onActiveChange(found);
      });
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [items, onActiveChange]);

  // Close the touch-toggled panel when clicking outside.
  useEffect(() => {
    if (hasHover || !isExpanded) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setIsExpanded(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [hasHover, isExpanded]);

  if (items.length === 0) return null;

  return (
    <div
      ref={containerRef}
      className="fixed right-0 inset-y-0 z-50 flex items-stretch"
      style={{ width: '28px' }}
      onMouseEnter={() => hasHover && setIsExpanded(true)}
      onMouseLeave={() => hasHover && setIsExpanded(false)}
      onClick={() => !hasHover && setIsExpanded((p) => !p)}
    >
      {/* Outline panel — slides in from the right */}
      <div
        className={`absolute right-full top-1/2 -translate-y-1/2 w-72 max-h-[70vh]
          bg-card border border-border rounded-lg shadow-xl overflow-hidden
          transition-all duration-150 ease-out
          ${isExpanded
            ? 'opacity-100 pointer-events-auto translate-x-0'
            : 'opacity-0 pointer-events-none translate-x-2'
          }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-3 py-2 border-b border-border sticky top-0 bg-card/95 backdrop-blur-sm">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            User Messages
          </span>
        </div>
        <div className="overflow-y-auto max-h-[calc(70vh-36px)]">
          {items.map((item) => {
            const isActive = item.userIndex === activeIndex;
            return (
              <button
                key={item.userIndex}
                onClick={() => {
                  onSelect(item.userIndex);
                  if (!hasHover) setIsExpanded(false);
                }}
                className={`w-full px-3 py-2.5 text-left flex items-start gap-2.5 border-b border-border/60 last:border-b-0 transition-colors ${
                  isActive
                    ? 'bg-primary/10 border-l-2 border-l-primary'
                    : 'hover:bg-muted/60'
                }`}
              >
                <span className="shrink-0 w-5 h-5 text-center leading-5 bg-muted rounded text-[10px] font-semibold text-muted-foreground mt-0.5">
                  {item.userIndex + 1}
                </span>
                <span className="text-[13px] text-foreground leading-snug line-clamp-2">
                  {item.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Rail: center track line + proportional tick marks */}
      <div className="relative flex-1">
        <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-px bg-border/50" />

        {items.map((item, i) => {
          const pct = tickPositions[i];
          if (pct == null) return null;
          const isActive = item.userIndex === activeIndex;

          return (
            <button
              key={item.userIndex}
              title={`#${item.userIndex + 1}: ${item.label}`}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(item.userIndex);
              }}
              className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 p-1.5 cursor-pointer group/tick"
              style={{ top: `${pct * 100}%` }}
            >
              <div
                className={`rounded-full transition-all duration-150 ${
                  isActive
                    ? 'w-[10px] h-[3px] bg-primary shadow-[0_0_4px_var(--color-primary)]'
                    : 'w-[5px] h-[5px] bg-muted-foreground/30 group-hover/tick:bg-muted-foreground/70 group-hover/tick:w-[8px] group-hover/tick:h-[3px]'
                }`}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
