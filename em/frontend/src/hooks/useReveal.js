import { useEffect, useRef, useState } from 'react';

/**
 * Reveal-on-scroll helper for the landing experience.
 *
 * Uses IntersectionObserver rather than a scroll listener so long pages stay
 * cheap, and degrades to "always visible" when the API is unavailable.
 */
export default function useReveal({ threshold = 0.18, once = true } = {}) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;

    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisible(true);
            if (once) observer.unobserve(entry.target);
          } else if (!once) {
            setVisible(false);
          }
        });
      },
      { threshold, rootMargin: '0px 0px -8% 0px' }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold, once]);

  return [ref, visible];
}
