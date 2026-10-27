import type { Metadata } from 'next'
import { LegalPage } from '@/components/LegalPage'

export const metadata: Metadata = {
  title: 'Privacy Policy — Snugd',
  description: 'What Snugd collects, why, who processes it, and how to delete it.',
}

// Keep this in step with what the code actually does. When a processor, a
// data type or the deletion flow changes, change this page in the same PR.
export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="October 26, 2026">
      <p>
        Snugd (&quot;Snugd&quot;, &quot;we&quot;, &quot;us&quot;) is an apartment-hunting app at snugd.ai, currently
        operated by an individual in the United States. This policy explains what we collect when you use the
        website or the Snugd mobile apps, why, and what you can do about it. Questions:{' '}
        <a href="mailto:privacy@snugd.ai">privacy@snugd.ai</a>.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>
          <strong>Account details from Google.</strong> When you sign in with Google we receive your name, email
          address and profile picture. We don&apos;t receive your Google password or access anything else in your
          Google account.
        </li>
        <li>
          <strong>What you search for.</strong> City, budget, bedrooms, move-in date and any preferences you type.
          You can search without an account.
        </li>
        <li>
          <strong>What you save.</strong> Favourite listings and the listings you compare.
        </li>
        <li>
          <strong>Tours.</strong> Listings you add to your tour pipeline and everything you attach to them: written
          notes, voice notes and their transcripts, photos, tags, ratings and your decision.
        </li>
        <li>
          <strong>Commute addresses.</strong> Work or school addresses you enter so we can estimate commute times.
        </li>
        <li>
          <strong>Feedback and waitlist requests.</strong> Messages you send through the feedback button, and the
          email and city you give us if you ask to be told when Snugd reaches your city.
        </li>
        <li>
          <strong>Invite codes.</strong> If you arrive through an invite link, which code you used, so we know which
          channels bring people to Snugd.
        </li>
        <li>
          <strong>Usage events.</strong> Records of actions in the app, such as running a search, saving a listing or
          starting a tour, tied to your account if you are signed in. We use these to understand how Snugd is used
          and to fix problems. We don&apos;t use advertising trackers or third-party analytics scripts.
        </li>
        <li>
          <strong>Technical data.</strong> IP address and request logs kept by our hosting providers, used for
          security, rate limiting and troubleshooting.
        </li>
      </ul>
      <p>
        Your browser stores your sign-in session and a few preferences locally. We don&apos;t set advertising
        cookies.
      </p>

      <h2>How we use it</h2>
      <ul>
        <li>To run the app: search, rank and compare listings, keep your favourites and tours, and show commute times.</li>
        <li>To send emails about your account and, if you turn them on, alerts about new listings.</li>
        <li>To provide AI features (below), only after you have agreed to them in the app.</li>
        <li>To keep Snugd secure, prevent abuse, and understand which features are used so we can improve them.</li>
      </ul>
      <p>We don&apos;t sell your personal information, and we don&apos;t share it for advertising.</p>

      <h2>AI features</h2>
      <p>
        Snugd&apos;s AI features score and compare listings, draft emails to landlords, plan tour days, tidy up your
        notes and write a decision brief. To do this we send the relevant listing details and the content you
        provide — your preferences, notes and transcripts — to our AI providers. Voice notes are sent to OpenAI to
        be transcribed; other AI features use Anthropic&apos;s Claude. We ask for your agreement before turning AI
        features on.
      </p>
      <p>
        These providers process the data to return a result to us. Under their API terms they don&apos;t use it to
        train their models.
      </p>

      <h2>Who processes your data</h2>
      <p>We use these service providers to run Snugd. Each gets only what it needs for its part:</p>
      <ul>
        <li><strong>Supabase</strong> — sign-in and account database.</li>
        <li><strong>Amazon Web Services</strong> — our servers, database, and storage for tour photos and voice notes (United States).</li>
        <li><strong>Vercel</strong> — hosting for the website.</li>
        <li><strong>Google</strong> — sign-in, and Google Maps for addresses and commute times.</li>
        <li><strong>Anthropic</strong> and <strong>OpenAI</strong> — AI features and voice transcription, as above.</li>
        <li><strong>Resend</strong> — sending email.</li>
      </ul>
      <p>
        Listing information comes from public rental listings. We may also disclose information if the law requires
        it, or to protect the safety of our users or others.
      </p>

      <h2>How long we keep it</h2>
      <p>
        We keep your account data for as long as you have an account. When you delete your account, we delete your
        profile, saved listings, tours, notes, recordings, photos and commute addresses within 30 days. Usage events are kept with the link to your account removed. Backups roll over within a further 30
        days.
      </p>

      <h2>Your choices</h2>
      <ul>
        <li><strong>See and export your data:</strong> Settings → Export my data downloads your saved listings.</li>
        <li><strong>Correct it:</strong> edit or delete notes, photos and addresses in the app.</li>
                <li>
          <strong>Delete your account:</strong> email <a href="mailto:privacy@snugd.ai">privacy@snugd.ai</a> from the
          address you sign in with, and we will delete it as described above. In-app deletion is coming.
        </li>
        <li>
          <strong>Other requests:</strong> depending on where you live you may have further rights, such as asking
          for a copy of everything we hold about you. Email us and we will respond within 30 days.
        </li>
      </ul>

      <h2>Security</h2>
      <p>
        Data is encrypted in transit, and access to your records is restricted to your own account. No system is
        perfectly secure; if we learn of a breach that affects you, we will tell you.
      </p>

      <h2>Children</h2>
      <p>
        Snugd is not for children under 13, and we don&apos;t knowingly collect their information. If you believe a
        child has given us information, email us and we will delete it.
      </p>

      <h2>Changes</h2>
      <p>
        If we change this policy we will update the date above, and for significant changes we will tell you in the
        app or by email before they take effect.
      </p>
    </LegalPage>
  )
}
