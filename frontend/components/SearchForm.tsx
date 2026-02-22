'use client';

import { useState } from 'react';
import { SearchParams, ApartmentWithScore } from '@/types/apartment';
import { searchApartments, ApiError } from '@/lib/api';
import { useComparison } from '@/hooks/useComparison';

// Available cities (MVP - 3 PA cities)
const AVAILABLE_CITIES = [
  { value: 'Philadelphia, PA', label: 'Philadelphia, PA' },
  { value: 'Bryn Mawr, PA', label: 'Bryn Mawr, PA' },
  { value: 'Pittsburgh, PA', label: 'Pittsburgh, PA' },
];

// Property type options
const PROPERTY_TYPES = ['Apartment', 'Condo', 'Townhouse', 'Studio'];

// Bedroom options
const BEDROOM_OPTIONS = [
  { value: 0, label: 'Studio' },
  { value: 1, label: '1 BR' },
  { value: 2, label: '2 BR' },
  { value: 3, label: '3 BR' },
];

// Bathroom options
const BATHROOM_OPTIONS = [
  { value: 1, label: '1 Bath' },
  { value: 2, label: '2 Bath' },
  { value: 3, label: '3 Bath' },
];

interface SearchFormProps {
  onResults: (results: ApartmentWithScore[]) => void;
  onLoading: (loading: boolean) => void;
  onError: (error: string | null) => void;
  onSearchMeta?: (meta: { tier?: string; searches_remaining?: number | null }) => void;
}

export default function SearchForm({ onResults, onLoading, onError, onSearchMeta }: SearchFormProps) {
  // Form state
  const [city, setCity] = useState('Pittsburgh, PA');
  const [budget, setBudget] = useState(2000);
  const [bedrooms, setBedrooms] = useState(1);
  const [bathrooms, setBathrooms] = useState(1);
  const [selectedPropertyTypes, setSelectedPropertyTypes] = useState<string[]>(['Apartment']);
  const [moveInDate, setMoveInDate] = useState('2026-03-01');
  const [otherPreferences, setOtherPreferences] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { setSearchContext } = useComparison();

  // Handle property type checkbox toggle
  const handlePropertyTypeChange = (type: string) => {
    setSelectedPropertyTypes((prev) =>
      prev.includes(type)
        ? prev.filter((t) => t !== type)
        : [...prev, type]
    );
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!city.trim()) {
      onError('Please enter a city');
      return;
    }

    if (selectedPropertyTypes.length === 0) {
      onError('Please select at least one property type');
      return;
    }

    setIsSubmitting(true);
    onLoading(true);
    onError(null);

    try {
      const params: SearchParams = {
        city: city.trim(),
        budget,
        bedrooms,
        bathrooms,
        property_type: selectedPropertyTypes.join(', '),
        move_in_date: moveInDate,
        other_preferences: otherPreferences.trim() || undefined,
      };

      const response = await searchApartments(params);
      onResults(response.apartments);
      onSearchMeta?.({ tier: response.tier, searches_remaining: response.searches_remaining });

      // Save search context for comparison page
      setSearchContext({
        city: city.trim(),
        budget,
        bedrooms,
        bathrooms,
        property_type: selectedPropertyTypes.join(', '),
        move_in_date: moveInDate,
        other_preferences: otherPreferences.trim(),
      });
    } catch (error) {
      if (error instanceof ApiError) {
        onError(error.message);
      } else {
        onError('An unexpected error occurred');
      }
    } finally {
      setIsSubmitting(false);
      onLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* City Select */}
      <div>
        <label htmlFor="city" className="block text-sm font-medium text-gray-700 mb-1">
          City
        </label>
        <select
          id="city"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
          required
        >
          {AVAILABLE_CITIES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Budget Input */}
      <div>
        <label htmlFor="budget" className="block text-sm font-medium text-gray-700 mb-1">
          Maximum Budget ($/month)
        </label>
        <input
          type="number"
          id="budget"
          value={budget}
          onChange={(e) => setBudget(Number(e.target.value))}
          min={500}
          max={15000}
          step={100}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
          required
        />
      </div>

      {/* Bedrooms & Bathrooms Row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Bedrooms */}
        <div>
          <label htmlFor="bedrooms" className="block text-sm font-medium text-gray-700 mb-1">
            Bedrooms
          </label>
          <select
            id="bedrooms"
            value={bedrooms}
            onChange={(e) => setBedrooms(Number(e.target.value))}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
          >
            {BEDROOM_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Bathrooms */}
        <div>
          <label htmlFor="bathrooms" className="block text-sm font-medium text-gray-700 mb-1">
            Bathrooms
          </label>
          <select
            id="bathrooms"
            value={bathrooms}
            onChange={(e) => setBathrooms(Number(e.target.value))}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
          >
            {BATHROOM_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Property Type Checkboxes */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Property Type
        </label>
        <div className="grid grid-cols-2 gap-2">
          {PROPERTY_TYPES.map((type) => (
            <label
              key={type}
              className={`flex items-center p-3 border rounded-lg cursor-pointer transition ${
                selectedPropertyTypes.includes(type)
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-300 hover:border-gray-400'
              }`}
            >
              <input
                type="checkbox"
                checked={selectedPropertyTypes.includes(type)}
                onChange={() => handlePropertyTypeChange(type)}
                className="h-4 w-4 text-blue-600 rounded focus:ring-blue-500"
              />
              <span className="ml-2 text-sm">{type}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Move-in Date */}
      <div>
        <label htmlFor="moveInDate" className="block text-sm font-medium text-gray-700 mb-1">
          Move-in Date
        </label>
        <input
          type="date"
          id="moveInDate"
          value={moveInDate}
          onChange={(e) => setMoveInDate(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
          required
        />
      </div>

      {/* Other Preferences */}
      <div>
        <label htmlFor="otherPreferences" className="block text-sm font-medium text-gray-700 mb-1">
          Other Preferences (optional)
        </label>
        <textarea
          id="otherPreferences"
          value={otherPreferences}
          onChange={(e) => setOtherPreferences(e.target.value)}
          rows={3}
          placeholder="E.g., Must have in-unit washer/dryer, parking, pet-friendly for a small dog..."
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition resize-none"
        />
      </div>

      {/* Submit Button */}
      <button
        type="submit"
        disabled={isSubmitting}
        className={`w-full py-3 px-4 rounded-lg font-semibold text-white transition ${
          isSubmitting
            ? 'bg-blue-400 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-700 active:bg-blue-800'
        }`}
      >
        {isSubmitting ? (
          <span className="flex items-center justify-center">
            <svg
              className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            Searching...
          </span>
        ) : (
          'Find Apartments'
        )}
      </button>
    </form>
  );
}
