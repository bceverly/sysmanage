import React, { useCallback, useEffect, useRef, useState } from 'react';
import { IoChevronBack, IoChevronForward } from 'react-icons/io5';
import './css/ScrollableNavList.css';

interface ScrollableNavListProps {
  /**
   * The pre-rendered <li> children that make up the nav list.  Caller
   * is responsible for the items themselves; this component handles
   * overflow detection + horizontal scroll arrows that mirror MUI's
   * Tabs variant="scrollable" behaviour.
   */
  children: React.ReactNode;
  /**
   * Class names to attach to the inner <ul>.  Existing Navbar styling
   * keeps using ``nav__list`` for desktop layout.
   */
  listClassName?: string;
}

/**
 * Wraps a horizontal list with prev / next scroll buttons that appear
 * only when the content overflows the viewport.  Used for the main
 * top nav (Dashboard / Hosts / ...) so labels never wrap and the user
 * can pan the list when the window is narrow.
 */
const ScrollableNavList: React.FC<ScrollableNavListProps> = ({
  children,
  listClassName = '',
}) => {
  // eslint-disable-next-line no-undef
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  const updateButtons = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const epsilon = 1; // floating-point slack for sub-pixel rounding
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

  // Re-evaluate when children change (plugin nav items appear after
  // license check, language changes resize labels, etc.)
  useEffect(() => {
    updateButtons();
  }, [children, updateButtons]);

  const scrollBy = (delta: number) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: delta, behavior: 'smooth' });
  };

  return (
    <div className="scrollnav">
      <button
        type="button"
        className={`scrollnav__btn scrollnav__btn--left ${canLeft ? '' : 'scrollnav__btn--hidden'}`}
        onClick={() => scrollBy(-200)}
        aria-label="Scroll left"
        tabIndex={canLeft ? 0 : -1}
      >
        <IoChevronBack />
      </button>
      <div className="scrollnav__scroller" ref={scrollerRef}>
        <ul className={`scrollnav__list ${listClassName}`}>{children}</ul>
      </div>
      <button
        type="button"
        className={`scrollnav__btn scrollnav__btn--right ${canRight ? '' : 'scrollnav__btn--hidden'}`}
        onClick={() => scrollBy(200)}
        aria-label="Scroll right"
        tabIndex={canRight ? 0 : -1}
      >
        <IoChevronForward />
      </button>
    </div>
  );
};

export default ScrollableNavList;
