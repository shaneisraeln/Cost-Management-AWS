export function PagePlaceholder({
  title,
  description,
  phase,
}: {
  title: string;
  description: string;
  phase: string;
}) {
  return (
    <div>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 max-w-2xl text-white/60">{description}</p>
      <div className="mt-4 inline-block rounded border border-white/10 px-3 py-1 text-xs text-white/50">
        {phase}
      </div>
    </div>
  );
}
