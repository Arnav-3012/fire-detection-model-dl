import { useEffect, useRef, useState } from "react";

// Scroll-triggered entrance wrapper — fades/rises a card in once it enters
// the viewport, then disconnects its own observer (one-time reveal, not a
// repeating scroll gimmick). Falls back to always-visible if
// IntersectionObserver is unavailable or the element is already on screen
// at mount (so above-the-fold content on first paint never has to "wait"
// for a scroll that isn't coming).
export default function Reveal({ children, className = "", as: Tag = "div", delay = 0, style }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={`reveal${visible ? " reveal--visible" : ""}${className ? ` ${className}` : ""}`}
      style={delay ? { ...style, transitionDelay: `${delay}ms` } : style}
    >
      {children}
    </Tag>
  );
}
