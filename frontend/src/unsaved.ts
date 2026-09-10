import { useEffect } from "react";
import { useBlocker } from "react-router-dom";

export function useUnsavedGuard(dirty: boolean) {
  const blocker = useBlocker(dirty);

  useEffect(() => {
    const on = (e: BeforeUnloadEvent) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", on);
    return () => window.removeEventListener("beforeunload", on);
  }, [dirty]);

  useEffect(() => {
    if (blocker.state === "blocked" && !dirty) blocker.reset();
  }, [blocker, dirty]);

  return blocker;
}
