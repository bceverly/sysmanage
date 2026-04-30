import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, IconButton } from '@mui/material';
import { ChevronLeft, ChevronRight } from '@mui/icons-material';

interface ScrollableButtonBarProps {
  /**
   * The buttons / nodes to lay out horizontally.  The bar guarantees
   * none of them wrap (whiteSpace: nowrap) and adds prev/next arrows
   * when the row overflows the viewport.
   */
  children: React.ReactNode;
  /** Optional sx overrides for the outer wrapper. */
  sx?: object;
  /** Distance scrolled per arrow click in pixels.  Default 240. */
  scrollStep?: number;
}

/**
 * Generic horizontal scrollable bar with MUI-style prev/next arrows.
 * Used for the Hosts page action button row so labels never wrap and
 * a narrow viewport gets pannable controls.
 */
const ScrollableButtonBar: React.FC<ScrollableButtonBarProps> = ({
  children,
  sx,
  scrollStep = 240,
}) => {
  // eslint-disable-next-line no-undef
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  const updateButtons = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const epsilon = 1;
    setCanLeft(el.scrollLeft > epsilon);
    setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - epsilon);
  }, []);

  useEffect(() => {
    updateButtons();
    const el = scrollerRef.current;
    if (!el) return undefined;
    el.addEventListener('scroll', updateButtons, { passive: true });
    // eslint-disable-next-line no-undef
    const ro = new ResizeObserver(updateButtons);
    ro.observe(el);
    globalThis.addEventListener('resize', updateButtons);
    return () => {
      el.removeEventListener('scroll', updateButtons);
      ro.disconnect();
      globalThis.removeEventListener('resize', updateButtons);
    };
  }, [updateButtons]);

  // Re-check when children change (permission gates flip, etc.)
  useEffect(() => {
    updateButtons();
  }, [children, updateButtons]);

  const scrollBy = (delta: number) => {
    scrollerRef.current?.scrollBy({ left: delta, behavior: 'smooth' });
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', minWidth: 0, ...sx }}>
      <IconButton
        size="small"
        onClick={() => scrollBy(-scrollStep)}
        aria-label="Scroll left"
        sx={{
          visibility: canLeft ? 'visible' : 'hidden',
          flex: '0 0 auto',
        }}
      >
        <ChevronLeft />
      </IconButton>
      <Box
        ref={scrollerRef}
        sx={{
          flex: '1 1 auto',
          minWidth: 0,
          overflowX: 'auto',
          overflowY: 'hidden',
          // Hide native scrollbar so the chrome stays clean.
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          '&::-webkit-scrollbar': { display: 'none' },
        }}
      >
        <Box
          sx={{
            display: 'inline-flex',
            flexDirection: 'row',
            gap: 2,
            // Children must not wrap — children are responsible for
            // their own labels staying on one line, but we also force
            // it here to belt-and-suspenders the MUI Button label.
            whiteSpace: 'nowrap',
            '& .MuiButton-root': { whiteSpace: 'nowrap', flexShrink: 0 },
          }}
        >
          {children}
        </Box>
      </Box>
      <IconButton
        size="small"
        onClick={() => scrollBy(scrollStep)}
        aria-label="Scroll right"
        sx={{
          visibility: canRight ? 'visible' : 'hidden',
          flex: '0 0 auto',
        }}
      >
        <ChevronRight />
      </IconButton>
    </Box>
  );
};

export default ScrollableButtonBar;
