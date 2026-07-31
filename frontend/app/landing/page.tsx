'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { supabase } from '@/lib/supabase';

/* ──────────────────────────── constants ──────────────────────────── */

const FEATURES = [
  { emoji: '🔍', title: 'AI Match Scoring', desc: 'Every listing scored 0-100% against your budget, commute, and priorities with AI reasoning.' },
  { emoji: '🏢', title: 'Floorplan-Aware Search', desc: 'Search by bedroom count and we match the real floorplan inside each building — a 3-bed unit in a mixed building actually shows up.' },
  { emoji: '🛏️', title: 'By-the-Bed Pricing', desc: 'Shared student housing shows per-bed and whole-unit cost side by side, so a "cheap" listing never fools you.' },
  { emoji: '📱', title: 'Multi-Channel Outreach', desc: 'AI drafts your inquiry. Call, text, or paste into the contact form — one tap.' },
  { emoji: '🗺️', title: 'AI Day Planner', desc: 'Multiple tours one day? AI builds an optimized route with travel times.' },
  { emoji: '🎤', title: 'Voice Capture', desc: 'Hold-to-record during tours. Whisper transcribes, AI organizes into pros/cons.' },
  { emoji: '⚖️', title: 'Side-by-Side Compare', desc: 'AI scores 2-3 apartments across value, space, amenities + custom categories from your preferences.' },
  { emoji: '💰', title: 'True Cost Calculator', desc: 'Rent + utilities + fees with per-person splitting. Regional estimates fill gaps.' },
  { emoji: '🚗', title: 'Commute Calculator', desc: 'Drive, transit, and walk times to your work or school on every listing.' },
  { emoji: '🏆', title: 'AI Decision Brief', desc: 'After touring, AI synthesizes your ratings, notes, and costs — picks your top match.' },
];

const HOW_IT_WORKS = [
  { step: 1, title: 'Search & Compare', desc: 'Browse with AI scores, true cost, and commute. Compare and favorite in parallel.' },
  { step: 2, title: 'Start Touring', desc: 'Move favorites into your 5-stage pipeline. Each apartment gets its own tracker.' },
  { step: 3, title: 'Reach Out', desc: 'AI drafts your inquiry. Call, text, or contact form — one tap per channel.' },
  { step: 4, title: 'Tour & Capture', desc: 'Voice notes, photos, star ratings, pro/con tags. All structured automatically.' },
  { step: 5, title: 'Get Your Top Pick', desc: 'AI Decision Brief synthesizes everything into your best match with reasoning.' },
];

const TECH_STACK = ['Claude AI', 'Next.js 16', 'FastAPI', 'Supabase', 'Whisper', 'Stripe', 'AWS ECS'];

const CHANNEL_NAMES: Record<string, string> = {
  LINKEDIN: 'via LinkedIn', GIRLHACKS: 'via GirlHacks', PNC: 'via PNC',
  REDDIT: 'via Reddit', PENNSTATE: 'via Penn State', UPITT: 'via UPitt',
  FACEBOOK: 'via Facebook', WOMENTECH: 'via Women in Tech', BETA: 'General beta',
};

const DEFAULT_CODE = 'BETA-XXXXX'; // ← REPLACE with your actual default invite code
const QA_URL = 'https://qa.snugd.ai'; // ← Your QA URL
const YOUTUBE_ID = '-XJYuerLpqQ';

/* ──────────────────────────── components ──────────────────────────── */

function CheckIcon() {
  return (
    <svg className="w-5 h-5 text-[var(--color-primary)] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
    </svg>
  );
}

function HeartIcon({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 01-.383-.218 25.18 25.18 0 01-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0112 5.052 5.5 5.5 0 0116.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 01-4.244 3.17 15.247 15.247 0 01-.383.219l-.022.012-.007.004-.003.001a.752.752 0 01-.704 0l-.003-.001z" />
    </svg>
  );
}

/* ── Waitlist Form ── */
function WaitlistForm({ compact = false }: { compact?: boolean }) {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setStatus('loading');
    const { error } = await supabase
      .from('waitlist')
      .insert({ email: email.trim().toLowerCase(), name: name.trim() || null, referral_source: 'landing_page' });
    if (error) {
      if (error.code === '23505' || error.message?.toLowerCase().includes('duplicate')) {
        setStatus('success');
        setMessage("You're already on the list! We'll reach out soon.");
        return;
      }
      setStatus('error');
      setMessage('Something went wrong. Please try again.');
      return;
    }
    setStatus('success');
    setMessage("You're on the list! We'll reach out soon.");
  };

  if (status === 'success') {
    return (
      <div className="flex items-center gap-3 py-4">
        <div className="w-10 h-10 rounded-full bg-[var(--color-primary)]/10 flex items-center justify-center flex-shrink-0">
          <CheckIcon />
        </div>
        <p className="text-[var(--color-primary)] font-medium">{message}</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className={compact ? 'flex flex-col sm:flex-row gap-3' : 'space-y-3'}>
      {!compact && (
        <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Your name (optional)"
          className="w-full px-4 py-3 rounded-xl border border-[var(--color-border)] bg-white text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/30 focus:border-[var(--color-primary)] transition" />
      )}
      <input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@email.com"
        className="w-full px-4 py-3 rounded-xl border border-[var(--color-border)] bg-white text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/30 focus:border-[var(--color-primary)] transition" />
      <button type="submit" disabled={status === 'loading'}
        className="px-6 py-3 rounded-xl bg-[var(--color-primary)] text-white font-semibold hover:bg-[var(--color-primary-light)] disabled:opacity-60 transition whitespace-nowrap flex-shrink-0">
        {status === 'loading' ? 'Joining...' : compact ? 'Join Waitlist' : 'Get Early Access'}
      </button>
      {status === 'error' && <p className="text-sm text-red-600">{message}</p>}
    </form>
  );
}

/* ── Beta Code Box ── */
function BetaCodeBox({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      const el = document.createElement('textarea');
      el.value = code; el.style.position = 'fixed'; el.style.opacity = '0';
      document.body.appendChild(el); el.select();
      try { document.execCommand('copy'); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch {}
      document.body.removeChild(el);
    });
  }, [code]);

  return (
    <button onClick={copy} className="w-full bg-white/[.08] border-2 border-[var(--color-primary-light)] rounded-2xl p-5 cursor-pointer hover:border-emerald-400 hover:bg-white/[.12] transition relative group">
      <p className="text-xs text-[var(--color-primary-light)] font-semibold uppercase tracking-[2px] mb-2">Your Invite Code</p>
      <p className="font-mono text-3xl font-bold text-white tracking-[3px]">{code}</p>
      <p className="text-xs text-white/40 mt-2">Tap to copy</p>
      <span className={`absolute -top-2.5 right-4 bg-emerald-500 text-white text-xs font-semibold px-3 py-0.5 rounded-full transition-opacity ${copied ? 'opacity-100' : 'opacity-0'}`}>
        Copied!
      </span>
    </button>
  );
}

/* ──────────────────────────── Main Page Content ──────────────────────────── */

function LandingContent() {
  const searchParams = useSearchParams();
  const codeParam = searchParams.get('code');
  const betaCode = codeParam || DEFAULT_CODE;
  const hasBetaCode = !!codeParam;
  const channelPrefix = betaCode.split('-')[0];
  const channelName = CHANNEL_NAMES[channelPrefix] || '';
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', h, { passive: true });
    return () => window.removeEventListener('scroll', h);
  }, []);

  useEffect(() => {
    const header = document.querySelector('header');
    const bottomNav = document.querySelector('nav.fixed.bottom-0');
    header?.classList.add('hidden');
    bottomNav?.classList.add('hidden');
    return () => { header?.classList.remove('hidden'); bottomNav?.classList.remove('hidden'); };
  }, []);

  const scrollToBeta = useCallback(() => {
    document.getElementById('beta')?.scrollIntoView({ behavior: 'smooth' });
  }, []);
  const scrollToWaitlist = useCallback(() => {
    document.getElementById('waitlist')?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* NAV */}
      <nav className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${scrolled ? 'bg-[var(--color-bg)]/90 backdrop-blur-md shadow-sm border-b border-[var(--color-border)]' : 'bg-transparent'}`}>
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <HeartIcon className="w-5 h-5 text-[var(--color-accent)]" />
            <span className="text-xl font-bold text-[var(--color-text)]">snugd</span>
            <span className="text-xl font-bold text-[var(--color-primary)]">.ai</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#features" className="hidden md:block text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition">Features</a>
            <a href="#how" className="hidden md:block text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition">How It Works</a>
            <button onClick={hasBetaCode ? scrollToBeta : scrollToWaitlist}
              className="px-5 py-2 rounded-xl bg-[var(--color-primary)] text-white text-sm font-semibold hover:bg-[var(--color-primary-light)] transition">
              {hasBetaCode ? 'Get Beta Access' : 'Join Waitlist'}
            </button>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section className="pt-24 pb-12 md:pt-28 md:pb-16">
        <div className="max-w-5xl mx-auto px-6 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--color-primary)]/10 border border-[var(--color-primary)]/20 text-[var(--color-primary)] text-xs font-semibold mb-5">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-primary)] animate-pulse" />
              {hasBetaCode ? 'Beta access — free Pro for 90 days' : 'Beta live across 8 cities'}
            </span>
            <h1 className="text-4xl md:text-5xl font-bold text-[var(--color-text)] leading-tight tracking-tight mb-4">
              Stop apartment hunting{' '}
              <span className="text-[var(--color-primary)]">with scattered notes.</span>
            </h1>
            <p className="text-lg text-[var(--color-text-secondary)] leading-relaxed mb-8 max-w-lg">
              Snugd is the AI co-pilot that scores listings, calculates true costs, captures tour notes by voice, and tells you which apartment to pick.
            </p>
            {hasBetaCode ? (
              <div>
                <button onClick={scrollToBeta} className="px-8 py-3.5 rounded-xl bg-[var(--color-primary)] text-white text-base font-semibold hover:bg-[var(--color-primary-light)] transition">
                  Get Your Beta Code ↓
                </button>
                <p className="text-xs text-[var(--color-text-muted)] mt-3">Free Pro access · 90 days · No credit card</p>
              </div>
            ) : (
              <div>
                <WaitlistForm compact />
                <p className="text-xs text-[var(--color-text-muted)] mt-3">Free tier available · No credit card required</p>
              </div>
            )}
          </div>
          {/* Video */}
          <div className="rounded-2xl overflow-hidden border border-[var(--color-border)] shadow-xl bg-black" style={{ aspectRatio: '9/16', maxHeight: 480 }}>
            <iframe className="w-full h-full" src={`https://www.youtube.com/embed/${YOUTUBE_ID}`} title="Snugd Demo" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />
          </div>
        </div>
      </section>

      {/* BETA ACCESS — shown prominently when ?code= is present */}
      {hasBetaCode && (
        <section id="beta" className="py-16 bg-[var(--color-primary-dark)]">
          <div className="max-w-lg mx-auto px-6 text-center">
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 border border-white/15 text-[var(--color-primary-light)] text-xs font-semibold mb-4">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-primary-light)] animate-pulse" />
              Free Pro Access — 90 Days
            </span>
            <h2 className="text-3xl font-bold text-white mb-2">Try the beta now</h2>
            <p className="text-white/50 mb-6">Copy your invite code, open the app, sign in with Google, paste the code.</p>

            <BetaCodeBox code={betaCode} />

            {channelName && (
              <p className="text-xs text-white/30 mt-2">{channelName}</p>
            )}

            <div className="flex justify-center gap-8 my-8">
              {['Copy code', 'Open app', 'Sign in', 'Paste code'].map((s, i) => (
                <div key={s} className="text-center">
                  <div className="w-8 h-8 rounded-full bg-white/10 text-[var(--color-primary-light)] font-bold text-sm flex items-center justify-center mx-auto mb-2">
                    {i + 1}
                  </div>
                  <p className="text-xs text-white/50">{s}</p>
                </div>
              ))}
            </div>

            <a href={QA_URL} target="_blank" rel="noopener noreferrer"
              className="inline-block px-10 py-3.5 rounded-xl bg-[var(--color-primary-light)] text-white text-lg font-semibold hover:bg-emerald-400 transition">
              Open Snugd Beta →
            </a>
          </div>
        </section>
      )}

      {/* FEATURES */}
      <section id="features" className="py-20">
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-[var(--color-text)] mb-3">Everything you need to find home</h2>
            <p className="text-[var(--color-text-secondary)] max-w-lg mx-auto">Ten AI-powered tools that replace spreadsheets, scattered notes, and gut feelings.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {FEATURES.map(f => (
              <div key={f.title} className="group p-5 rounded-2xl bg-white border border-[var(--color-border)] hover:border-[var(--color-primary)]/30 hover:shadow-lg transition-all">
                <span className="text-2xl">{f.emoji}</span>
                <h3 className="text-sm font-bold text-[var(--color-text)] mt-3 mb-1">{f.title}</h3>
                <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" className="py-20 bg-[var(--color-primary-dark)]">
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-3">How it works</h2>
            <p className="text-white/50">Five stages. AI handles the busywork.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {HOW_IT_WORKS.map((s) => (
              <div key={s.step} className="p-5 rounded-2xl bg-white/[.06] border border-white/[.08] hover:bg-white/[.1] transition">
                <div className="w-9 h-9 rounded-full bg-white/[.12] flex items-center justify-center mb-3">
                  <span className="text-white font-bold text-sm">{s.step}</span>
                </div>
                <h3 className="text-white font-semibold text-sm mb-1">{s.title}</h3>
                <p className="text-white/50 text-xs leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CITIES */}
      <section className="py-8 bg-white border-y border-[var(--color-border)]">
        <div className="max-w-5xl mx-auto px-6 text-center">
          <p className="text-sm text-[var(--color-text-secondary)]">Beta live in <span className="font-semibold text-[var(--color-text)]">8 cities</span> and growing</p>
        </div>
      </section>

      {/* TESTIMONIAL */}
      <section className="py-16">
        <div className="max-w-2xl mx-auto px-6 text-center">
          <svg className="w-8 h-8 text-[var(--color-primary)]/20 mx-auto mb-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M4.583 17.321C3.553 16.227 3 15 3 13.011c0-3.5 2.457-6.637 6.03-8.188l.893 1.378c-3.335 1.804-3.987 4.145-4.247 5.621.537-.278 1.24-.375 1.929-.311 1.804.167 3.226 1.648 3.226 3.489a3.5 3.5 0 01-3.5 3.5c-1.073 0-2.099-.49-2.748-1.179zm10 0C13.553 16.227 13 15 13 13.011c0-3.5 2.457-6.637 6.03-8.188l.893 1.378c-3.335 1.804-3.987 4.145-4.247 5.621.537-.278 1.24-.375 1.929-.311 1.804.167 3.226 1.648 3.226 3.489a3.5 3.5 0 01-3.5 3.5c-1.073 0-2.099-.49-2.748-1.179z" />
          </svg>
          <blockquote className="text-xl text-[var(--color-text)] leading-relaxed mb-4 italic">
            &ldquo;I toured 6 apartments in 3 days. Without Snugd, I would&apos;ve forgotten which one had the leaky faucet vs. the noisy street. The decision brief literally picked my apartment for me.&rdquo;
          </blockquote>
          <p className="font-semibold text-[var(--color-text)]">Early beta tester</p>
        </div>
      </section>

      {/* BETA ACCESS — shown lower when no ?code= (visitors can still access if they scroll) */}
      {!hasBetaCode && (
        <section id="beta" className="py-16 bg-[var(--color-primary-dark)]">
          <div className="max-w-lg mx-auto px-6 text-center">
            <h2 className="text-3xl font-bold text-white mb-2">Already have a beta code?</h2>
            <p className="text-white/50 mb-6">Paste your invite code after signing in.</p>
            <a href={QA_URL} target="_blank" rel="noopener noreferrer"
              className="inline-block px-10 py-3.5 rounded-xl bg-[var(--color-primary-light)] text-white text-lg font-semibold hover:bg-emerald-400 transition">
              Open Snugd Beta →
            </a>
          </div>
        </section>
      )}

      {/* WAITLIST — always shown for non-beta-city visitors */}
      <section id="waitlist" className="py-16 bg-white border-t border-[var(--color-border)]">
        <div className="max-w-lg mx-auto px-6 text-center">
          <h2 className="text-3xl font-bold text-[var(--color-text)] mb-2">
            {hasBetaCode ? 'Know someone who needs this?' : 'Not in a beta city yet?'}
          </h2>
          <p className="text-[var(--color-text-secondary)] mb-6">
            {hasBetaCode ? 'Share the waitlist with friends who are apartment hunting.' : 'Join the waitlist and we\'ll let you know when we launch in your area.'}
          </p>
          <WaitlistForm />
        </div>
      </section>

      {/* TECH */}
      <section className="py-6 border-t border-[var(--color-border)]">
        <div className="max-w-5xl mx-auto px-6">
          <div className="flex flex-wrap items-center justify-center gap-x-7 gap-y-2">
            <span className="text-xs text-[var(--color-text-muted)]">Built with</span>
            {TECH_STACK.map(t => (
              <span key={t} className="text-xs font-semibold text-[var(--color-text-secondary)]">{t}</span>
            ))}
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="py-5 border-t border-[var(--color-border)]">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-1.5">
            <HeartIcon className="w-3.5 h-3.5 text-[var(--color-accent)]" />
            <span className="text-sm font-bold text-[var(--color-text-secondary)]">snugd.ai</span>
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">&copy; {new Date().getFullYear()} Snugd. All rights reserved.</p>
          <a href="mailto:founders@snugd.ai" className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-primary)] transition">founders@snugd.ai</a>
        </div>
      </footer>
    </div>
  );
}

/* ── Suspense wrapper required for useSearchParams ── */
export default function LandingPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[var(--color-bg)]" />}>
      <LandingContent />
    </Suspense>
  );
}
