import { useEffect } from "react";

/** Re-run while the tab is visible: on an interval, when it becomes visible, and on window focus. */
export function useVisiblePoll(ms: number, fn: () => void) {
  useEffect(() => {
    const run = () => {
      if (document.visibilityState === "visible") fn();
    };
    const id = window.setInterval(run, ms);
    document.addEventListener("visibilitychange", run);
    window.addEventListener("focus", run);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", run);
      window.removeEventListener("focus", run);
    };
  }, [ms, fn]);
}
