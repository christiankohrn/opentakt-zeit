export default function LoadingNote({ className = "mt-8" }: { className?: string }) {
  return (
    <p className={`${className} text-sm text-muted`} role="status">
      Laden …
    </p>
  );
}
