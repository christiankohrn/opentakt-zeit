import ConfirmDialog from "./ConfirmDialog";

export default function UnsavedChangesDialog({
  onStay,
  onDiscard,
}: {
  onStay: () => void;
  onDiscard: () => void;
}) {
  return (
    <ConfirmDialog
      title="Ungespeicherte Änderungen"
      body="Wenn du die Bearbeitung verlässt, gehen die Änderungen verloren."
      confirmLabel="Verwerfen"
      cancelLabel="Bleiben"
      onCancel={onStay}
      onConfirm={onDiscard}
    />
  );
}
