import { useEffect, useState } from "react";

/**
 * Sticky-nav scroll spy. Observes the given section ids and reports the one
 * crossing a narrow band near the top of the viewport, so long sections do not
 * steal the highlight from short ones.
 */
export function useActiveSection(ids: readonly string[], fallback: string): string {
  const [active, setActive] = useState(fallback);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") {
      return;
    }

    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((element): element is HTMLElement => element !== null);

    if (elements.length === 0) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);

        if (visible[0]) {
          setActive(visible[0].target.id);
        }
      },
      { rootMargin: "-42% 0px -52% 0px", threshold: [0, 0.2, 0.5, 1] },
    );

    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [ids]);

  return active;
}
