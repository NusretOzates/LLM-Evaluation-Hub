export function CatalogAlert({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "The catalog could not be loaded.";
  return (
    <p className="alert" role="alert">
      {message}
    </p>
  );
}
