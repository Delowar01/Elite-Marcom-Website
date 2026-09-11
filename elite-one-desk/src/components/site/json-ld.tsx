/**
 * Structured data. Serialised with a `<` escape because `JSON.stringify` will
 * happily emit `</script>` inside a string, and every value here can come from
 * the panel.
 */
export function JsonLd({ data }: { data: Record<string, unknown> | Record<string, unknown>[] }) {
  const json = JSON.stringify(data).replace(/</g, "\\u003c");
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />;
}
