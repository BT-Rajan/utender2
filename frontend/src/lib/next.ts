// Where to go after signing in or up: only an invitation link, never an
// arbitrary (possibly external) address taken from the URL.
export function safeNext(value: string | null): string | null {
  return value && /^\/invite\/[A-Za-z0-9_-]+$/.test(value) ? value : null;
}
