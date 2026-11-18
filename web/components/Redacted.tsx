/** Shows text with redaction tokens like [PAN] or [PHONE] as dark chips, so people see what was hidden. */
export function Redacted({ text }: { text: string }) {
  const parts = text.split(/(\[[A-Z_]+\])/g);
  return (
    <>
      {parts.map((p, i) =>
        /^\[[A-Z_]+\]$/.test(p) ? (
          <span key={i} className="font-mono-token mx-0.5 rounded bg-redaction-bg px-1.5 py-0.5 text-xs text-redaction-text">
            {p}
          </span>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}
