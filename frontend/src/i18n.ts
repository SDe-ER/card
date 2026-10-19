// Frappe's own translations, sent in the page boot (card/www/cdms.py), with {0} placeholders.
// As frappe's __(): a translation with context is keyed "text:context" and falls back to the
// plain text. CARD Mobile gives generic words the context "Card Mobile", so its translations
// never override Frappe's or ERPNext's anywhere else.
export function translate(
  messages: Record<string, string> | undefined,
  text: string,
  args: unknown[] = [],
  context?: string,
): string {
  const out = (context && messages?.[`${text}:${context}`]) || messages?.[text] || text
  return out.replace(/\{(\d+)\}/g, (m: string, i: string) => String(args[Number(i)] ?? m))
}

export function __(text: string, args: unknown[] = [], context?: string): string {
  return translate(window.__messages, text, args, context)
}
