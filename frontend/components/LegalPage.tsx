import Link from 'next/link'

// Shared shell for /privacy and /terms: readable measure, plain headings, and
// the date the text last changed. Server component — no auth, no client JS.
export function LegalPage({
  title,
  updated,
  children,
}: {
  title: string
  updated: string
  children: React.ReactNode
}) {
  return (
    <article className="max-w-2xl mx-auto px-4 sm:px-6 py-10 text-[15px] leading-relaxed text-[var(--color-text)]
      [&_h2]:text-lg [&_h2]:font-bold [&_h2]:mt-8 [&_h2]:mb-2
      [&_p]:mb-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-3 [&_li]:mb-1
      [&_a]:text-[var(--color-primary)] [&_a]:underline">
      <h1 className="text-2xl font-bold mb-1">{title}</h1>
      <p className="text-sm text-[var(--color-text-muted)] mb-6">Last updated {updated}</p>
      {children}
      <p className="mt-10 text-sm text-[var(--color-text-muted)]">
        <Link href="/privacy">Privacy Policy</Link> · <Link href="/terms">Terms of Service</Link> ·{' '}
        <a href="mailto:privacy@snugd.ai">privacy@snugd.ai</a>
      </p>
    </article>
  )
}
