export default function FieldError({ id, children }: { id?: string; children?: string }) {
  if (!children) return null;
  return (
    <p id={id} className="mt-1 text-sm text-danger" role="alert">
      {children}
    </p>
  );
}
