'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

/* ──────────────────────────── constants ──────────────────────────── */

const PIPELINE_STAGES = [
  { label: 'Interested', color: 'bg-blue-500', emoji: '💙' },
  { label: 'Outreach', color: 'bg-purple-500', emoji: '📧' },
  { label: 'Scheduled', color: 'bg-amber-500', emoji: '📅' },
  { label: 'Toured', color: 'bg-emerald-500', emoji: '🏠' },
  { label: 'Deciding', color: 'bg-rose-500', emoji: '🤔' },
];

const FEATURES = [
  {
    title: 'AI Match Scoring',
    desc: 'Claude AI reads every listing and scores it against your priorities — commute, budget, vibe, pet policy, and more.',
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
      </svg>
    ),
  },
  {
    title: 'AI Inquiry Emails',
    desc: 'One click drafts a personalized email to the landlord with your details, timeline, and questions — ready to send.',
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
      </svg>
    ),
  },
  {
    title: 'AI Day Planner',
    desc: 'Touring three places Saturday? The AI builds an optimized route with travel times and talking points for each stop.',
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
      </svg>
    ),
  },
  {
    title: 'Voice Capture',
    desc: 'Walk through an apartment, talk out loud. Whisper transcribes your notes and AI organizes them into structured pros/cons.',
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
      </svg>
    ),
  },
  {
    title: 'Side-by-Side Compare',
    desc: 'Pick 2-3 apartments and get an instant breakdown — rent, space, amenities, commute — with an AI-picked winner.',
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
      </svg>
    ),
  },
  {
    title: 'AI Decision Brief',
    desc: 'When you are down to your finalists, get a personalized report weighing trade-offs against your exact priorities.',
    icon: (
      <svg className="w-7 h-7" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
      </svg>
    ),
  },
];

const HOW_IT_WORKS = [
  { step: 1, title: 'Search & Favorite', desc: 'Browse listings across 19 East Coast cities. Heart the ones that catch your eye.' },
  { step: 2, title: 'Start Touring', desc: 'Move favorites into your tour pipeline. Each apartment gets its own stage tracker.' },
  { step: 3, title: 'Send Outreach', desc: 'AI drafts personalized inquiry emails. One click to send to each landlord.' },
  { step: 4, title: 'Tour & Capture', desc: 'Visit in person. Record voice notes that AI transcribes into structured pros/cons.' },
  { step: 5, title: 'Get Your Top Pick', desc: 'AI weighs everything — scores, notes, priorities — and recommends your best match.' },
];

const STATS = [
  { value: '20-40 hrs', label: 'Saved per search' },
  { value: '92%', label: 'Match accuracy' },
  { value: '<60 sec', label: 'AI scoring time' },
  { value: '5', label: 'Pipeline stages' },
];

const FREE_FEATURES = [
  '3 AI searches per day',
  'Basic comparison table',
  'Up to 5 favorites',
  'Tour pipeline (5 active)',
  'Community support',
];

const PRO_FEATURES = [
  'Unlimited AI searches',
  'Claude head-to-head analysis',
  'Unlimited favorites',
  'Full tour pipeline',
  'AI inquiry emails',
  'Voice capture + transcription',
  'AI decision brief',
  'Daily email alerts',
  'Priority support',
];

const TECH_STACK = ['Claude AI', 'Next.js', 'FastAPI', 'Supabase', 'Whisper', 'Stripe'];

/* ──────────────────────────── helpers ──────────────────────────── */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/* ──────────────────────── Waitlist Form ──────────────────────── */

function WaitlistForm({ compact = false }: { compact?: boolean }) {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setStatus('loading');
    try {
      const res = await fetch(`${API_URL}/api/waitlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name: name || null, referral_source: 'landing_page' }),
      });
      const data = await res.json();
      if (!res.ok && res.status !== 200 && res.status !== 201) throw new Error(data.detail || 'Failed');
      setStatus('success');
      setMessage(data.message || "You're in! We'll reach out soon.");
    } catch {
      setStatus('error');
      setMessage('Something went wrong. Please try again.');
    }
  };

  if (status === 'success') {
    return (
      <div className={`flex items-center gap-3 ${compact ? 'py-3' : 'py-6'}`}>
        <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        </div>
        <p className="text-emerald-700 font-medium">{message}</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className={compact ? 'space-y-3' : 'space-y-4'}>
      <div className={compact ? 'flex flex-col sm:flex-row gap-3' : 'flex flex-col gap-3'}>
        {!compact && (
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name (optional)"
            className="w-full px-4 py-3 rounded-xl border border-[var(--color-border)] bg-white text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/30 focus:border-[var(--color-primary)] transition"
          />
        )}
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@email.com"
          className="w-full px-4 py-3 rounded-xl border border-[var(--color-border)] bg-white text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/30 focus:border-[var(--color-primary)] transition"
        />
        <button
          type="submit"
          disabled={status === 'loading'}
          className="px-6 py-3 rounded-xl bg-[var(--color-primary)] text-white font-semibold hover:bg-[var(--color-primary-light)] disabled:opacity-60 transition whitespace-nowrap flex-shrink-0"
        >
          {status === 'loading' ? 'Joining...' : 'Get Early Access'}
        </button>
      </div>
      {status === 'error' && (
        <p className="text-sm text-red-600">{message}</p>
      )}
    </form>
  );
}

/* ─────────────────── Pipeline Stage Mockup ──────────────────── */

function PipelineMockup({ activeStage }: { activeStage: number }) {
  return (
    <div className="bg-white rounded-2xl shadow-xl border border-[var(--color-border)] p-5 w-full max-w-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-semibold text-[var(--color-text)]">Tour Pipeline</span>
        <span className="text-xs text-[var(--color-text-muted)]">3 active</span>
      </div>
      {/* Stages */}
      <div className="space-y-2">
        {PIPELINE_STAGES.map((stage, i) => (
          <div
            key={stage.label}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-500 ${
              i === activeStage
                ? 'bg-[var(--color-primary)]/10 ring-1 ring-[var(--color-primary)]/30 scale-[1.02]'
                : 'bg-gray-50'
            }`}
          >
            <div className={`w-2.5 h-2.5 rounded-full ${stage.color} ${i === activeStage ? 'animate-pulse' : ''}`} />
            <span className={`text-sm font-medium flex-1 ${i === activeStage ? 'text-[var(--color-primary-dark)]' : 'text-[var(--color-text-secondary)]'}`}>
              {stage.label}
            </span>
            <span className={`text-xs ${i === activeStage ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-muted)]'}`}>
              {i <= activeStage ? (i === activeStage ? '1' : i === 0 ? '2' : '1') : '0'}
            </span>
          </div>
        ))}
      </div>
      {/* Sample apartment card */}
      <div className="mt-4 p-3 rounded-lg bg-gradient-to-br from-emerald-50 to-white border border-emerald-100">
        <div className="flex items-start gap-3">
          <div className="w-12 h-12 rounded-lg bg-emerald-200/50 flex items-center justify-center text-lg flex-shrink-0">
            🏠
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--color-text)] truncate">The Meridian at Bryn Mawr</p>
            <p className="text-xs text-[var(--color-text-secondary)]">$1,850/mo &middot; 1 bd &middot; 1 ba</p>
            <div className="flex items-center gap-1.5 mt-1">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 text-emerald-700">
                92% match
              </span>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-purple-100 text-purple-700">
                {PIPELINE_STAGES[activeStage].label}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────── Favorites Mockup ──────────────────────── */

function FavoritesMockup() {
  const apartments = [
    { name: 'The Willows at Ardmore', price: '$1,650/mo', beds: 'Studio', match: 88 },
    { name: 'Haverford Court', price: '$2,100/mo', beds: '2 bd', match: 95 },
    { name: 'Lancaster Walk', price: '$1,900/mo', beds: '1 bd', match: 91 },
  ];
  return (
    <div className="bg-white rounded-2xl shadow-xl border border-[var(--color-border)] p-5 max-w-sm w-full">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-semibold text-[var(--color-text)]">Your Favorites</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-rose-100 text-rose-600 font-medium">3 saved</span>
      </div>
      <div className="space-y-3">
        {apartments.map((apt) => (
          <div key={apt.name} className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition">
            <div className="text-rose-500 flex-shrink-0">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 01-.383-.218 25.18 25.18 0 01-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0112 5.052 5.5 5.5 0 0116.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 01-4.244 3.17 15.247 15.247 0 01-.383.219l-.022.012-.007.004-.003.001a.752.752 0 01-.704 0l-.003-.001z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[var(--color-text)] truncate">{apt.name}</p>
              <p className="text-xs text-[var(--color-text-secondary)]">{apt.price} &middot; {apt.beds}</p>
            </div>
            <span className="text-xs font-semibold text-[var(--color-primary)]">{apt.match}%</span>
          </div>
        ))}
      </div>
      <button className="w-full mt-4 py-2.5 rounded-lg bg-[var(--color-primary)] text-white text-sm font-semibold hover:bg-[var(--color-primary-light)] transition">
        Start Touring Selected
      </button>
    </div>
  );
}

/* ─────────────────── Compare Mockup ──────────────────────── */

function CompareMockup() {
  return (
    <div className="bg-white rounded-2xl shadow-xl border border-[var(--color-border)] p-5 max-w-sm w-full">
      {/* Winner card */}
      <div className="p-3 rounded-lg bg-gradient-to-br from-emerald-50 to-amber-50 border border-emerald-200 mb-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-amber-500 text-lg">&#9733;</span>
          <span className="text-sm font-bold text-[var(--color-text)]">Winner: Haverford Court</span>
        </div>
        <p className="text-xs text-[var(--color-text-secondary)]">Best overall value with largest space and top amenities for the price.</p>
      </div>
      {/* Scores */}
      <div className="space-y-2.5">
        {[
          { cat: 'Value', a: 82, b: 91 },
          { cat: 'Space', a: 75, b: 88 },
          { cat: 'Amenities', a: 90, b: 85 },
          { cat: 'Location', a: 88, b: 79 },
        ].map((row) => (
          <div key={row.cat} className="flex items-center gap-3">
            <span className="text-xs text-[var(--color-text-secondary)] w-16">{row.cat}</span>
            <div className="flex-1 flex items-center gap-2">
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-blue-400 rounded-full" style={{ width: `${row.a}%` }} />
              </div>
              <span className="text-xs font-medium text-blue-600 w-7 text-right">{row.a}</span>
            </div>
            <div className="flex-1 flex items-center gap-2">
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${row.b}%` }} />
              </div>
              <span className="text-xs font-medium text-emerald-600 w-7 text-right">{row.b}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-center gap-6 mt-4 pt-3 border-t border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-blue-400" />
          <span className="text-xs text-[var(--color-text-secondary)]">The Willows</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-emerald-500" />
          <span className="text-xs text-[var(--color-text-secondary)]">Haverford Court</span>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────── MAIN PAGE ──────────────────────── */

export default function LandingPage() {
  const [scrolled, setScrolled] = useState(false);
  const [activeStage, setActiveStage] = useState(0);
  const heroRef = useRef<HTMLDivElement>(null);

  /* Hide standard layout header & bottom nav */
  useEffect(() => {
    const header = document.querySelector('header');
    const bottomNav = document.querySelector('nav.fixed.bottom-0');
    header?.classList.add('hidden');
    bottomNav?.classList.add('hidden');
    return () => {
      header?.classList.remove('hidden');
      bottomNav?.classList.remove('hidden');
    };
  }, []);

  /* Scroll detection for nav */
  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  /* Pipeline stage cycling */
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveStage((prev) => (prev + 1) % PIPELINE_STAGES.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const scrollToWaitlist = useCallback(() => {
    document.getElementById('final-cta')?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-bg)] font-[var(--font-dm-sans)]">
      {/* ─── NAV ─── */}
      <nav
        className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${
          scrolled
            ? 'bg-white/90 backdrop-blur-md shadow-sm border-b border-[var(--color-border)]'
            : 'bg-transparent'
        }`}
      >
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <span className="text-2xl font-bold tracking-tight text-[var(--color-primary)]">snugd</span>
          <div className="hidden md:flex items-center gap-8">
            <a href="#features" className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition">
              Features
            </a>
            <a href="#how-it-works" className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition">
              How It Works
            </a>
            <a href="#pricing" className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition">
              Pricing
            </a>
            <button
              onClick={scrollToWaitlist}
              className="px-5 py-2 rounded-xl bg-[var(--color-primary)] text-white text-sm font-semibold hover:bg-[var(--color-primary-light)] transition"
            >
              Get Early Access
            </button>
          </div>
          {/* Mobile nav button */}
          <button
            onClick={scrollToWaitlist}
            className="md:hidden px-4 py-2 rounded-xl bg-[var(--color-primary)] text-white text-sm font-semibold hover:bg-[var(--color-primary-light)] transition"
          >
            Get Early Access
          </button>
        </div>
      </nav>

      {/* ─── HERO ─── */}
      <section ref={heroRef} className="pt-28 pb-16 md:pt-36 md:pb-24">
        <div className="max-w-6xl mx-auto px-6 grid md:grid-cols-2 gap-12 items-center">
          {/* Left */}
          <div>
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-700 text-xs font-semibold mb-6">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              MVP live &mdash; accepting early users
            </span>
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-[var(--color-text)] leading-tight tracking-tight mb-6">
              Stop apartment hunting with{' '}
              <span className="text-[var(--color-primary)]">scattered notes.</span>
            </h1>
            <p className="text-lg text-[var(--color-text-secondary)] leading-relaxed mb-8 max-w-lg">
              Snugd is your AI co-pilot for apartment hunting. Search, score, tour, and
              decide&nbsp;&mdash; all in one pipeline. No more spreadsheets, lost emails, or
              forgotten pros and cons.
            </p>
            <WaitlistForm compact />
            <p className="text-xs text-[var(--color-text-muted)] mt-3">
              Free tier available &middot; No credit card required
            </p>
          </div>
          {/* Right */}
          <div className="flex justify-center md:justify-end">
            <PipelineMockup activeStage={activeStage} />
          </div>
        </div>
      </section>

      {/* ─── STATS BAR ─── */}
      <section className="bg-[var(--color-primary-dark)] py-8">
        <div className="max-w-6xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-6">
          {STATS.map((s) => (
            <div key={s.label} className="text-center">
              <p className="text-2xl md:text-3xl font-bold text-white">{s.value}</p>
              <p className="text-sm text-emerald-200 mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ─── FEATURES ─── */}
      <section id="features" className="py-20 md:py-28">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold text-[var(--color-text)] mb-4">
              Everything you need to find home
            </h2>
            <p className="text-[var(--color-text-secondary)] max-w-2xl mx-auto">
              Six AI-powered tools that replace spreadsheets, email drafts, scattered notes, and gut feelings.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="group p-6 rounded-2xl bg-white border border-[var(--color-border)] hover:border-[var(--color-primary)]/30 hover:shadow-lg transition-all duration-300"
              >
                <div className="w-12 h-12 rounded-xl bg-emerald-50 text-[var(--color-primary)] flex items-center justify-center mb-4 group-hover:bg-emerald-100 transition">
                  {f.icon}
                </div>
                <h3 className="text-lg font-semibold text-[var(--color-text)] mb-2">{f.title}</h3>
                <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── FAVORITES FLOW ─── */}
      <section className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-6 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <span className="inline-flex items-center px-3 py-1 rounded-full bg-rose-100 text-rose-600 text-xs font-semibold mb-4">
              Favorites Flow
            </span>
            <h2 className="text-3xl md:text-4xl font-bold text-[var(--color-text)] mb-4">
              Heart it. Tour it. Decide.
            </h2>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-6">
              Every apartment you heart goes into your favorites. When you are ready, move them into
              the touring pipeline with one click. Each listing tracks its own stage&nbsp;&mdash; from
              initial interest through to your final decision.
            </p>
            <ul className="space-y-3">
              {['Heart apartments as you browse', 'Batch-move favorites to touring pipeline', 'Track each apartment through 5 stages'].map((item) => (
                <li key={item} className="flex items-center gap-3 text-sm text-[var(--color-text)]">
                  <svg className="w-5 h-5 text-[var(--color-primary)] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex justify-center">
            <FavoritesMockup />
          </div>
        </div>
      </section>

      {/* ─── AI COMPARE ─── */}
      <section className="py-20">
        <div className="max-w-6xl mx-auto px-6 grid md:grid-cols-2 gap-12 items-center">
          <div className="flex justify-center order-2 md:order-1">
            <CompareMockup />
          </div>
          <div className="order-1 md:order-2">
            <span className="inline-flex items-center px-3 py-1 rounded-full bg-blue-100 text-blue-600 text-xs font-semibold mb-4">
              AI Compare
            </span>
            <h2 className="text-3xl md:text-4xl font-bold text-[var(--color-text)] mb-4">
              Let AI pick the winner
            </h2>
            <p className="text-[var(--color-text-secondary)] leading-relaxed mb-6">
              Select 2-3 apartments and get an instant head-to-head analysis. Claude AI scores each
              across Value, Space, Amenities, and Location&nbsp;&mdash; then picks a winner with detailed reasoning.
            </p>
            <ul className="space-y-3">
              {['Category-by-category scoring', 'Personalized to your priorities', 'Winner with detailed reasoning'].map((item) => (
                <li key={item} className="flex items-center gap-3 text-sm text-[var(--color-text)]">
                  <svg className="w-5 h-5 text-[var(--color-primary)] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ─── HOW IT WORKS ─── */}
      <section id="how-it-works" className="py-20 md:py-28 bg-[var(--color-primary-dark)]">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              How it works
            </h2>
            <p className="text-emerald-200 max-w-2xl mx-auto">
              Five stages from discovery to decision. The AI handles the busywork.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-6">
            {HOW_IT_WORKS.map((step, i) => (
              <div key={step.step} className="relative">
                <div className="p-5 rounded-2xl bg-white/10 backdrop-blur-sm border border-white/10 hover:bg-white/15 transition h-full">
                  <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center mb-4">
                    <span className="text-white font-bold">{step.step}</span>
                  </div>
                  <h3 className="text-white font-semibold mb-2">{step.title}</h3>
                  <p className="text-emerald-200 text-sm leading-relaxed">{step.desc}</p>
                </div>
                {/* Connector arrow (hidden on last item and mobile) */}
                {i < HOW_IT_WORKS.length - 1 && (
                  <div className="hidden lg:block absolute top-1/2 -right-3 -translate-y-1/2 text-white/30">
                    <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── PRICING ─── */}
      <section id="pricing" className="py-20 md:py-28">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold text-[var(--color-text)] mb-4">
              Simple, transparent pricing
            </h2>
            <p className="text-[var(--color-text-secondary)] max-w-2xl mx-auto">
              Start free. Upgrade when you are ready for the full AI experience.
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-8 max-w-3xl mx-auto">
            {/* Free */}
            <div className="p-8 rounded-2xl bg-white border border-[var(--color-border)] flex flex-col">
              <h3 className="text-lg font-semibold text-[var(--color-text)] mb-1">Free</h3>
              <p className="text-3xl font-bold text-[var(--color-text)] mb-1">$0 <span className="text-base font-normal text-[var(--color-text-muted)]">/mo</span></p>
              <p className="text-sm text-[var(--color-text-secondary)] mb-6">Great for getting started</p>
              <ul className="space-y-3 mb-8 flex-1">
                {FREE_FEATURES.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm text-[var(--color-text)]">
                    <svg className="w-5 h-5 text-[var(--color-primary)] flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                    {f}
                  </li>
                ))}
              </ul>
              <a
                href="/"
                className="block text-center py-3 rounded-xl border-2 border-[var(--color-primary)] text-[var(--color-primary)] font-semibold hover:bg-[var(--color-primary)] hover:text-white transition"
              >
                Get Started Free
              </a>
            </div>
            {/* Pro */}
            <div className="p-8 rounded-2xl bg-white border-2 border-[var(--color-primary)] shadow-lg flex flex-col relative">
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-0.5 rounded-full bg-[var(--color-primary)] text-white text-xs font-semibold">
                Most Popular
              </span>
              <h3 className="text-lg font-semibold text-[var(--color-text)] mb-1">Pro</h3>
              <p className="text-3xl font-bold text-[var(--color-text)] mb-1">$12 <span className="text-base font-normal text-[var(--color-text-muted)]">/mo</span></p>
              <p className="text-sm text-[var(--color-text-secondary)] mb-6">Full AI-powered experience</p>
              <ul className="space-y-3 mb-8 flex-1">
                {PRO_FEATURES.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm text-[var(--color-text)]">
                    <svg className="w-5 h-5 text-[var(--color-primary)] flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                    {f}
                  </li>
                ))}
              </ul>
              <a
                href="/"
                className="block text-center py-3 rounded-xl bg-[var(--color-primary)] text-white font-semibold hover:bg-[var(--color-primary-light)] transition"
              >
                Start with Invite Code
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ─── TECH CREDIBILITY ─── */}
      <section className="py-10 bg-white border-y border-[var(--color-border)]">
        <div className="max-w-6xl mx-auto px-6">
          <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
            <span className="text-sm text-[var(--color-text-muted)]">Built with</span>
            {TECH_STACK.map((tech) => (
              <span key={tech} className="text-sm font-medium text-[var(--color-text-secondary)]">
                {tech}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ─── TESTIMONIAL ─── */}
      <section className="py-20">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <svg className="w-10 h-10 text-[var(--color-primary)]/20 mx-auto mb-6" fill="currentColor" viewBox="0 0 24 24">
            <path d="M4.583 17.321C3.553 16.227 3 15 3 13.011c0-3.5 2.457-6.637 6.03-8.188l.893 1.378c-3.335 1.804-3.987 4.145-4.247 5.621.537-.278 1.24-.375 1.929-.311 1.804.167 3.226 1.648 3.226 3.489a3.5 3.5 0 01-3.5 3.5c-1.073 0-2.099-.49-2.748-1.179zm10 0C13.553 16.227 13 15 13 13.011c0-3.5 2.457-6.637 6.03-8.188l.893 1.378c-3.335 1.804-3.987 4.145-4.247 5.621.537-.278 1.24-.375 1.929-.311 1.804.167 3.226 1.648 3.226 3.489a3.5 3.5 0 01-3.5 3.5c-1.073 0-2.099-.49-2.748-1.179z" />
          </svg>
          <blockquote className="text-xl md:text-2xl text-[var(--color-text)] leading-relaxed mb-6">
            &ldquo;I used to have a Google Sheet with 40 tabs and still forgot what I liked about half the places.
            Snugd replaced all of that in one afternoon. The AI scoring is scarily accurate.&rdquo;
          </blockquote>
          <div>
            <p className="font-semibold text-[var(--color-text)]">Sarah K.</p>
            <p className="text-sm text-[var(--color-text-secondary)]">Early beta tester &middot; Found her apartment in 2 weeks</p>
          </div>
        </div>
      </section>

      {/* ─── FINAL CTA ─── */}
      <section id="final-cta" className="py-20 md:py-28 bg-[var(--color-primary-dark)]">
        <div className="max-w-2xl mx-auto px-6 text-center">
          <div className="w-16 h-16 rounded-full bg-white/10 flex items-center justify-center mx-auto mb-8">
            <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 01-.383-.218 25.18 25.18 0 01-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0112 5.052 5.5 5.5 0 0116.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 01-4.244 3.17 15.247 15.247 0 01-.383.219l-.022.012-.007.004-.003.001a.752.752 0 01-.704 0l-.003-.001z" />
            </svg>
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Your next apartment is out there.
          </h2>
          <p className="text-xl text-emerald-200 mb-10">
            Get Snugd.
          </p>
          <div className="max-w-md mx-auto">
            <WaitlistForm compact />
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer className="py-8 bg-[var(--color-primary-dark)] border-t border-white/10">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="text-lg font-bold text-white tracking-tight">snugd</span>
          <p className="text-sm text-emerald-200">
            &copy; {new Date().getFullYear()} Snugd. All rights reserved.
          </p>
          <a href="mailto:hello@snugd.app" className="text-sm text-emerald-200 hover:text-white transition">
            hello@snugd.app
          </a>
        </div>
      </footer>
    </div>
  );
}
