'use client';

import { useState } from 'react';
import SearchForm from '@/components/SearchForm';
import ApartmentCard from '@/components/ApartmentCard';
import { ApartmentWithScore } from '@/types/apartment';
import { useAuth } from '@/contexts/AuthContext';

export default function Home() {
  // State for search results
  const [results, setResults] = useState<ApartmentWithScore[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const { user, loading: authLoading, signInWithGoogle } = useAuth();

  // Handle search results
  const handleResults = (apartments: ApartmentWithScore[]) => {
    setResults(apartments);
    setHasSearched(true);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-pulse text-center">
          <div className="h-8 w-48 bg-gray-200 rounded mb-4 mx-auto"></div>
          <div className="h-4 w-32 bg-gray-200 rounded mx-auto"></div>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center p-8">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">Find Your Perfect Apartment</h2>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto mb-8">
            Sign in to search apartments with AI-powered matching.
          </p>
          <button
            onClick={signInWithGoogle}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            Sign In with Google
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Hero Section - only show before first search */}
        {!hasSearched && (
          <div className="text-center mb-8">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Find Your Perfect Apartment
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
              Tell us what you&apos;re looking for, and our AI will find the best matches
              based on your preferences, budget, and needs.
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
              <SearchForm
                onResults={handleResults}
                onLoading={setIsLoading}
                onError={setError}
              />
            </div>
          </div>

          {/* Results Section */}
          {hasSearched && (
            <div className="lg:col-span-2">
              {/* Error Message */}
              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
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
              )}

              {/* Loading State */}
              {isLoading && (
                <div className="flex flex-col items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
                  <p className="text-gray-600">Finding your perfect apartments...</p>
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
                  <div className="grid gap-6 md:grid-cols-2">
                    {results.map((apartment) => (
                      <ApartmentCard key={apartment.id} apartment={apartment} />
                    ))}
                  </div>
                </div>
              )}

              {/* No Results */}
              {!isLoading && !error && hasSearched && results.length === 0 && (
                <div className="text-center py-12">
                  <svg
                    className="h-16 w-16 text-gray-300 mx-auto mb-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                  </svg>
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    No apartments found
                  </h3>
                  <p className="text-gray-600">
                    Try adjusting your search criteria or increasing your budget.
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
