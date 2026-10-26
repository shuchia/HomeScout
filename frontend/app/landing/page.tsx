import { redirect } from 'next/navigation'

// The landing page moved to `/`. Links already shared point here (including
// ?code= invites), so keep the query string.
export default async function LandingRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(await searchParams)) {
    for (const v of [value].flat()) if (v !== undefined) params.append(key, v)
  }
  const qs = params.toString()
  redirect(qs ? `/?${qs}` : '/')
}
