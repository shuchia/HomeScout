import { redirect } from 'next/navigation'

// There is no paid tier any more (2026-10) — every feature is free for
// signed-in users — so old links to the plans page land on search.
export default function PricingPage() {
  redirect('/')
}
