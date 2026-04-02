'use client';

import { useState, useEffect } from 'react';
import SearchForm from '@/components/SearchForm';
import ApartmentCard from '@/components/ApartmentCard';
import { ApartmentWithScore, SearchParams } from '@/types/apartment';
import { searchApartments, scoreBatch } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import UpgradePrompt from '@/components/UpgradePrompt';
import { InviteCodeBanner } from '@/components/InviteCodeBanner';

function loadSessionResults(): { results: ApartmentWithScore[]; remaining: number | null; currentPage: number; hasMore: boolean } {
  if (typeof window === 'undefined') return { results: [], remaining: null, currentPage: 1, hasMore: false };
  try {
    const raw = sessionStorage.getItem('snugd-search-results');
    if (raw) {
      const parsed = JSON.parse(raw);
      return { results: parsed.results || [], remaining: parsed.remaining ?? null, currentPage: parsed.currentPage || 1, hasMore: parsed.hasMore || false };
    }
  } catch { /* ignore */ }
  return { results: [], remaining: null, currentPage: 1, hasMore: false };
}

export default function Home() {
  // Restore search results from session so they persist across tab switches
  const [results, setResults] = useState<ApartmentWithScore[]>(() => loadSessionResults().results);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(() => loadSessionResults().results.length > 0);
  const [searchesRemaining, setSearchesRemaining] = useState<number | null>(() => loadSessionResults().remaining);
  const [rateLimited, setRateLimited] = useState(false);
  const [moveInDate, setMoveInDate] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(() => loadSessionResults().currentPage);
  const [hasMore, setHasMore] = useState(() => loadSessionResults().hasMore);
  const [loadingMore, setLoadingMore] = useState(false);
  const [aiLoadingIds, setAiLoadingIds] = useState<Set<string>>(new Set());
  const [lastSearchParams, setLastSearchParams] = useState<(SearchParams & { page?: number }) | null>(null);

  const { user, loading: authLoading, signInWithGoogle, tier, isPro } = useAuth();

  // Persist search results to sessionStorage
  useEffect(() => {
    if (results.length > 0) {
      sessionStorage.setItem('snugd-search-results', JSON.stringify({
        results, remaining: searchesRemaining, currentPage, hasMore
      }));
    }
  }, [results, searchesRemaining, currentPage, hasMore]);

  // Clear state on sign-out
  useEffect(() => {
    if (!user) {
      setResults([]);
      setHasSearched(false);
      setError(null);
      setRateLimited(false);
      setSearchesRemaining(null);
      setCurrentPage(1);
      setHasMore(false);
      setAiLoadingIds(new Set());
      setLastSearchParams(null);
      sessionStorage.removeItem('snugd-search-results');
    }
  }, [user]);

  // Trigger AI score backfill when new results arrive (Pro only)
  useEffect(() => {
    if (!isPro || results.length === 0 || aiLoadingIds.size === 0) return;

    const idsToScore = Array.from(aiLoadingIds);
    if (idsToScore.length === 0 || !lastSearchParams) return;

    scoreBatch(idsToScore, {
      city: lastSearchParams.city,
      budget: lastSearchParams.budget,
      bedrooms: lastSearchParams.bedrooms,
      bathrooms: lastSearchParams.bathrooms,
      property_type: lastSearchParams.property_type,
      move_in_date: lastSearchParams.move_in_date,
      other_preferences: lastSearchParams.other_preferences,
    }).then(({ scores }) => {
      if (scores.length > 0) {
        setResults(prev => prev.map(apt => {
          const score = scores.find(s => s.apartment_id === apt.id);
          return score ? { ...apt, match_score: score.match_score, reasoning: score.reasoning, highlights: score.highlights } : apt;
        }));
      }
      setAiLoadingIds(new Set());
    });
  }, [aiLoadingIds.size]); // eslint-disable-line react-hooks/exhaustive-deps

  // Handle search results
  const handleResults = (apartments: ApartmentWithScore[]) => {
    setResults(apartments);
    setHasSearched(true);
    setRateLimited(false);
    setCurrentPage(1);
    // Set AI loading for Pro users
    if (isPro) {
      setAiLoadingIds(new Set(apartments.map(a => a.id)));
    }
  };

  // Handle errors — detect rate limiting or daily limit
  const handleError = (err: string | null) => {
    setError(err);
    const lower = err?.toLowerCase() ?? '';
    setRateLimited(lower.includes('too many') || lower.includes('limit') || lower.includes('rate'));
  };

  // Handle search metadata (tier, remaining searches, pagination)
  const handleSearchMeta = (meta: { tier?: string; searches_remaining?: number | null; move_in_date?: string; has_more?: boolean; page?: number }) => {
    setSearchesRemaining(meta.searches_remaining ?? null);
    if (meta.move_in_date) setMoveInDate(meta.move_in_date);
    if (meta.has_more !== undefined) setHasMore(meta.has_more);
    if (meta.page !== undefined) setCurrentPage(meta.page);
  };

  // Load more results
  async function handleLoadMore() {
    if (!lastSearchParams || loadingMore) return;
    setLoadingMore(true);

    try {
      const nextPage = currentPage + 1;
      const response = await searchApartments({ ...lastSearchParams, page: nextPage });
      const newApts = response.apartments;
      setResults(prev => [...prev, ...newApts]);
      setCurrentPage(nextPage);
      setHasMore(response.has_more);

      // Set AI loading for new apartments (Pro only)
      if (isPro && newApts.length > 0) {
        setAiLoadingIds(new Set(newApts.map(a => a.id)));
      }
    } catch {
      setError('Failed to load more results');
    } finally {
      setLoadingMore(false);
    }
  }

  if (authLoading) {
    return (
      <div className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center">
        <div className="animate-pulse text-center">
          <div className="h-8 w-48 bg-gray-200 rounded mb-4 mx-auto"></div>
          <div className="h-4 w-32 bg-gray-200 rounded mx-auto"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <InviteCodeBanner />
        {/* Hero Section - only show before first search */}
        {!hasSearched && (
          <div className="text-center mb-8">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Find Your Perfect Apartment
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
              Tell us what you&apos;re looking for{user ? ', and our AI will find the best matches based on your preferences, budget, and needs' : '. Sign in for AI-powered matching'}.
            </p>
          </div>
        )}

        {/* Two-column layout on desktop */}
        <div className={`grid gap-8 ${hasSearched ? 'lg:grid-cols-3' : 'max-w-md mx-auto'}`}>
          {/* Search Form */}
          <div className={`${hasSearched ? 'lg:col-span-1' : ''}`}>
            <div className="bg-white rounded-lg shadow-md p-6 sticky top-8">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Search Apartments
              </h3>
              {!user ? (
                <div className="text-center py-6">
                  <p className="text-gray-600 mb-4">Sign in to search for apartments</p>
                  <button
                    onClick={signInWithGoogle}
                    className="w-full py-3 px-4 rounded-lg font-semibold text-white bg-[var(--color-primary)] hover:bg-[var(--color-primary-light)] transition"
                  >
                    Sign In with Google
                  </button>
                </div>
              ) : (
              <SearchForm
                onResults={handleResults}
                onLoading={setIsLoading}
                onError={handleError}
                onSearchMeta={handleSearchMeta}
                onSearchParams={(params) => setLastSearchParams(params)}
              />
              )}
              {tier === 'free' && searchesRemaining !== null && (
                <p className="text-sm text-gray-500 mt-3">
                  {searchesRemaining > 0
                    ? `${searchesRemaining} free searches remaining today`
                    : 'Daily search limit reached'}
                </p>
              )}
              {tier === 'free' && searchesRemaining === 0 && (
                <div className="mt-3">
                  <UpgradePrompt feature="unlimited searches" inline />
                </div>
              )}
              {/* Error shown below search form when no results yet */}
              {!hasSearched && error && (
                <div className="mt-4 space-y-3">
                  <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                    <div className="flex items-center gap-2">
                      <svg className="h-5 w-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <p className="text-red-700">{error}</p>
                    </div>
                  </div>
                  {rateLimited && !isPro && (
                    <UpgradePrompt feature="higher rate limits and unlimited searches" inline />
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Results Section */}
          {hasSearched && (
            <div className="lg:col-span-2">
              {/* Error Message */}
              {error && (
                <div className="space-y-3 mb-6">
                  <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                    <div className="flex items-center gap-2">
                      <svg
                        className="h-5 w-5 text-red-500"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                      <p className="text-red-700">{error}</p>
                    </div>
                  </div>
                  {rateLimited && !isPro && (
                    <UpgradePrompt feature="higher rate limits and unlimited searches" inline />
                  )}
                </div>
              )}

              {/* Loading State */}
              {isLoading && (
                <div className="grid gap-6 sm:grid-cols-2">
                  {[1, 2, 3, 4].map(i => (
                    <div key={i} className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] overflow-hidden animate-pulse">
                      <div className="aspect-[4/3] bg-gray-200" />
                      <div className="p-4 space-y-3">
                        <div className="h-6 bg-gray-200 rounded w-1/3" />
                        <div className="h-4 bg-gray-200 rounded w-2/3" />
                        <div className="flex gap-4">
                          <div className="h-4 bg-gray-200 rounded w-16" />
                          <div className="h-4 bg-gray-200 rounded w-16" />
                          <div className="h-4 bg-gray-200 rounded w-16" />
                        </div>
                        <div className="flex gap-1.5">
                          <div className="h-6 bg-gray-200 rounded-full w-16" />
                          <div className="h-6 bg-gray-200 rounded-full w-20" />
                          <div className="h-6 bg-gray-200 rounded-full w-14" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Results Grid */}
              {!isLoading && !error && results.length > 0 && (
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-semibold text-gray-900">
                      {results.length} Apartment{results.length !== 1 ? 's' : ''} Found
                    </h3>
                  </div>
                  <div className="grid gap-6 sm:grid-cols-2">
                    {results.map((apartment) => (
                      <ApartmentCard key={apartment.id} apartment={apartment} moveInDate={moveInDate ?? undefined} aiLoading={aiLoadingIds.has(apartment.id)} />
                    ))}
                  </div>

                  {/* Load More */}
                  {hasMore && (
                    <div className="flex justify-center mt-6">
                      <button
                        onClick={handleLoadMore}
                        disabled={loadingMore}
                        className="px-6 py-3 bg-[var(--color-primary)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-light)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        {loadingMore ? (
                          <>
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                            Loading...
                          </>
                        ) : (
                          'Load More'
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* No Results */}
              {!isLoading && !error && hasSearched && results.length === 0 && (
                <div className="text-center py-16">
                  <div className="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                    <svg className="h-8 w-8 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-medium text-[var(--color-text)] mb-2">
                    No apartments match your criteria
                  </h3>
                  <p className="text-[var(--color-text-secondary)] max-w-md mx-auto">
                    Try increasing your budget, changing the city, or adjusting your bedroom and bathroom preferences.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-white border-t mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-center text-sm text-gray-500">
            Powered by Claude AI &middot; Built with Next.js and FastAPI
          </p>
        </div>
      </footer>
    </div>
  );
}
