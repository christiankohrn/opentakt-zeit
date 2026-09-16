import type { ReactNode } from "react";

export function ExportButtons({
  onCsv,
  onPdf,
  pdfDisabled = false,
}: {
  onCsv?: () => void;
  onPdf: () => void;
  pdfDisabled?: boolean;
}) {
  return (
    <div className="flex shrink-0 items-center gap-2">
      {onCsv ? (
        <button type="button" className="rounded-lg border border-line bg-card px-3 py-1 text-sm" onClick={onCsv}>
          CSV
        </button>
      ) : null}
      <button
        type="button"
        disabled={pdfDisabled}
        className="rounded-lg border border-present bg-present px-3 py-1 text-sm text-white disabled:opacity-40"
        onClick={onPdf}
      >
        PDF
      </button>
    </div>
  );
}

export default function ReportToolbar({
  title,
  children,
  actions,
}: {
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <>
      <h1 className="mt-2 text-xl font-medium">{title}</h1>
      <div className="mt-2 flex items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-2">{children}</div>
        {actions ? <div className="ml-auto shrink-0">{actions}</div> : null}
      </div>
    </>
  );
}
