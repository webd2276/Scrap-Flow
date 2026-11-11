import { useEffect, useRef, useState, type RefObject } from "react";

interface Options {
  /** Stop observing after the first intersection. Defaults to true. */
  once?: boolean;
  rootMargin?: string;
  threshold?: number;
}

/**
 * Track whether an element is in the viewport. Used for count-up stats and for
 * mounting PDF thumbnails only when they scroll near the strip.
 */
export function useInView<T extends HTMLElement>(
  options: Options = {},
): [RefObject<T>, boolean] {
  const { once = true, rootMargin = "0px", threshold = 0.15 } = options;
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) {
      return;
    }

    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            if (once) {
              observer.disconnect();
            }
          } else if (!once) {
            setInView(false);
          }
        }
      },
      { rootMargin, threshold },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [once, rootMargin, threshold]);

  return [ref, inView];
}
