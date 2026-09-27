import { useState } from "react";
import { closedMonthDetail } from "./api";
import ConfirmDialog from "./components/ConfirmDialog";

type Fail = (message: string) => void;

export function useClosedMonth() {
  const [prompt, setPrompt] = useState<string | null>(null);
  const [job, setJob] = useState<null | { run: () => Promise<void>; fail: Fail }>(null);
  const [busy, setBusy] = useState(false);

  async function attempt(action: (confirmClosed: boolean) => Promise<void>, fail: Fail) {
    try {
      await action(false);
    } catch (err) {
      const message = closedMonthDetail(err);
      if (!message) {
        fail(err instanceof Error ? err.message : "Fehler");
        return;
      }
      setPrompt(message);
      setJob({ run: () => action(true), fail });
    }
  }

  function cancel() {
    if (busy) return;
    setPrompt(null);
    setJob(null);
  }

  async function confirm() {
    if (!job) return;
    setBusy(true);
    try {
      await job.run();
      setPrompt(null);
      setJob(null);
    } catch (err) {
      job.fail(err instanceof Error ? err.message : "Speichern fehlgeschlagen");
      setPrompt(null);
      setJob(null);
    } finally {
      setBusy(false);
    }
  }

  const dialog = prompt ? (
    <ConfirmDialog
      title="Monat ist abgeschlossen"
      body={prompt}
      confirmLabel={busy ? "Speichern …" : "Speichern und neu rechnen"}
      busy={busy}
      onCancel={cancel}
      onConfirm={() => void confirm()}
    />
  ) : null;

  return { attempt, dialog };
}
