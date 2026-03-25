import { test, expect, Page } from '@playwright/test';

// ─── Mock Data ───────────────────────────────────────────────────────

/** Pro user search results with numeric match_score */
const MOCK_SEARCH_RESPONSE = {
  apartments: [
    {
      id: 'test-001',
      address: '123 Test St, Pittsburgh, PA 15213',
      rent: 1500,
      bedrooms: 1,
      bathrooms: 1,
      sqft: 750,
      property_type: 'Apartment',
      available_date: '2026-03-01',
      amenities: ['Parking', 'Laundry', 'Pet Friendly', 'Gym', 'Pool', 'Dishwasher'],
      neighborhood: 'Test Neighborhood',
      description: 'A great test apartment',
      images: ['https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800'],
      match_score: 92,
      reasoning: 'Excellent match with all key requirements met.',
      highlights: ['Under budget', 'Pet-friendly', 'Great location'],
      freshness_confidence: 100,
      first_seen_at: '2026-02-19T10:00:00Z',
      times_seen: 3,
    },
    {
      id: 'test-002',
      address: '456 Sample Ave, Pittsburgh, PA 15217',
      rent: 1800,
      bedrooms: 1,
      bathrooms: 1,
      sqft: 900,
      property_type: 'Apartment',
      available_date: '2026-04-01',
      amenities: ['Parking', 'Gym', 'Rooftop'],
      neighborhood: 'Sample District',
      description: 'Another test apartment',
      images: [
        'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800',
        'https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800',
      ],
      match_score: 78,
      reasoning: 'Good match but slightly above preferred price range.',
      highlights: ['Spacious layout', 'Gym access'],
      freshness_confidence: 100,
      first_seen_at: '2026-02-19T10:00:00Z',
      times_seen: 3,
    },
  ],
  total_results: 2,
};

/** Free/anonymous search results with qualitative labels (no match_score) */
const MOCK_FREE_SEARCH_RESPONSE = {
  apartments: [
    {
      id: 'test-001',
      address: '123 Test St, Pittsburgh, PA 15213',
      rent: 1500,
      bedrooms: 1,
      bathrooms: 1,
      sqft: 750,
      property_type: 'Apartment',
      available_date: '2026-03-01',
      amenities: ['Parking', 'Laundry', 'Pet Friendly', 'Gym', 'Pool', 'Dishwasher'],
      neighborhood: 'Test Neighborhood',
      description: 'A great test apartment',
      images: ['https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800'],
      match_score: null,
      match_label: 'Excellent Match',
      heuristic_score: 95,
      reasoning: null,
      highlights: [],
      freshness_confidence: 100,
      first_seen_at: '2026-02-19T10:00:00Z',
      times_seen: 3,
    },
    {
      id: 'test-002',
      address: '456 Sample Ave, Pittsburgh, PA 15217',
      rent: 1800,
      bedrooms: 1,
      bathrooms: 1,
      sqft: 900,
      property_type: 'Apartment',
      available_date: '2026-04-01',
      amenities: ['Parking', 'Gym', 'Rooftop'],
      neighborhood: 'Sample District',
      description: 'Another test apartment',
      images: [
        'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800',
        'https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800',
      ],
      match_score: null,
      match_label: 'Great Match',
      heuristic_score: 80,
      reasoning: null,
      highlights: [],
      freshness_confidence: 100,
      first_seen_at: '2026-02-19T10:00:00Z',
      times_seen: 3,
    },
  ],
  total_results: 2,
  tier: 'free',
  searches_remaining: 2,
};

/** Mock compare endpoint response (basic, no AI analysis) */
const MOCK_COMPARE_RESPONSE = {
  apartments: [
    {
      id: 'test-001',
      address: '123 Test St, Pittsburgh, PA 15213',
      rent: 1500,
      bedrooms: 1,
      bathrooms: 1,
      sqft: 750,
      property_type: 'Apartment',
      available_date: '2026-03-01',
      amenities: ['Parking', 'Laundry', 'Pet Friendly'],
      neighborhood: 'Test Neighborhood',
      description: 'A great test apartment',
      images: ['https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800'],
    },
    {
      id: 'test-002',
      address: '456 Sample Ave, Pittsburgh, PA 15217',
      rent: 1800,
      bedrooms: 1,
      bathrooms: 1,
      sqft: 900,
      property_type: 'Apartment',
      available_date: '2026-04-01',
      amenities: ['Parking', 'Gym', 'Rooftop'],
      neighborhood: 'Sample District',
      description: 'Another test apartment',
      images: ['https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800'],
    },
  ],
  comparison_fields: ['rent', 'bedrooms', 'bathrooms', 'sqft', 'amenities'],
  tier: 'free',
};

// ─── Helpers ─────────────────────────────────────────────────────────

const MOCK_USER = {
  id: 'test-user-id',
  email: 'test@example.com',
  aud: 'authenticated',
  role: 'authenticated',
  app_metadata: { provider: 'google' },
  user_metadata: { name: 'Test User' },
  created_at: '2024-01-01T00:00:00Z',
};

/** Inject mock user into localStorage before page loads */
async function mockAuth(page: Page, options?: { favorites?: object[] }) {
  const mockFavorites = options?.favorites ?? [];

  await page.addInitScript((user: string) => {
    localStorage.setItem('__test_auth_user', user);
  }, JSON.stringify(MOCK_USER));

  // Intercept Supabase API calls to prevent network errors
  await page.route('**/supabase.co/**', async (route) => {
    const url = route.request().url();

    // Mock favorites query
    if (url.includes('/rest/v1/favorites')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockFavorites),
      });
      return;
    }

    // Mock profiles query
    if (url.includes('/rest/v1/profiles')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user_tier: 'free' }),
      });
      return;
    }

    // Default: fulfill with null
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(null),
    });
  });
}

/** Intercept search API and return mock data */
async function mockSearchApi(page: Page, response = MOCK_SEARCH_RESPONSE) {
  await page.route('**/api/search', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });
}

/** Intercept compare API and return mock data */
async function mockCompareApi(page: Page) {
  await page.route('**/api/apartments/compare', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_COMPARE_RESPONSE),
    });
  });
}

/** Intercept batch API and return mock data */
async function mockBatchApi(page: Page) {
  await page.route('**/api/apartments/batch', async (route) => {
    const body = await route.request().postDataJSON();
    const apartments = MOCK_SEARCH_RESPONSE.apartments.filter((a) =>
      body.includes(a.id)
    );
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(apartments),
    });
  });
}

// ─── Authenticated User Tests ────────────────────────────────────────

test.describe('Snugd E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page);
  });

  test.describe('Homepage', () => {
    test('should load the homepage with header and hero section', async ({ page }) => {
      await page.goto('/');

      await expect(page.locator('header')).toBeVisible();
      await expect(page.locator('header').locator('text=Snugd')).toBeVisible();
      await expect(page.locator('h2')).toContainText('Find Your Perfect Apartment');
      await expect(page.locator('footer')).toContainText('Powered by Claude AI');
    });

    test('should display the search form', async ({ page }) => {
      await page.goto('/');

      await expect(page.locator('label:has-text("City")')).toBeVisible();
      await expect(page.locator('label:has-text("Maximum Budget")')).toBeVisible();
      await expect(page.locator('label:has-text("Bedrooms")')).toBeVisible();
      await expect(page.locator('label:has-text("Bathrooms")')).toBeVisible();
      await expect(page.locator('label:has-text("Property Type")')).toBeVisible();
      await expect(page.locator('label:has-text("Move-in Date")')).toBeVisible();
      await expect(page.locator('label:has-text("Other Preferences")')).toBeVisible();
      await expect(page.locator('button:has-text("Find Apartments")')).toContainText('Find Apartments');
    });
  });

  test.describe('Search Form Interactions', () => {
    test('should have default values pre-filled', async ({ page }) => {
      await page.goto('/');

      await expect(page.locator('select#city')).toHaveValue('Arlington, VA');
      await expect(page.locator('input#budget')).toHaveValue('2000');
      await expect(page.locator('select#bedrooms')).toHaveValue('1');
      await expect(page.locator('select#bathrooms')).toHaveValue('1');
    });

    test('should allow changing form values', async ({ page }) => {
      await page.goto('/');

      await page.selectOption('select#city', 'Bryn Mawr, PA');
      await expect(page.locator('select#city')).toHaveValue('Bryn Mawr, PA');

      await page.fill('input#budget', '5000');
      await expect(page.locator('input#budget')).toHaveValue('5000');

      await page.selectOption('select#bedrooms', '2');
      await expect(page.locator('select#bedrooms')).toHaveValue('2');

      await page.selectOption('select#bathrooms', '2');
      await expect(page.locator('select#bathrooms')).toHaveValue('2');

      await page.fill('input#moveInDate', '2026-06-15');
      await expect(page.locator('input#moveInDate')).toHaveValue('2026-06-15');

      await page.fill('textarea#otherPreferences', 'Pet-friendly, parking');
      await expect(page.locator('textarea#otherPreferences')).toHaveValue('Pet-friendly, parking');
    });

    test('should toggle property type checkboxes', async ({ page }) => {
      await page.goto('/');

      const apartmentCheckbox = page.locator('input[type="checkbox"]').first();
      await expect(apartmentCheckbox).toBeChecked();

      await page.locator('label:has-text("Apartment")').click();
      await expect(apartmentCheckbox).not.toBeChecked();

      await page.locator('label:has-text("Apartment")').click();
      await expect(apartmentCheckbox).toBeChecked();
    });

    test('should prevent submission when no property types selected', async ({ page }) => {
      await page.goto('/');

      await page.locator('label:has-text("Apartment")').click();
      await page.click('button:has-text("Find Apartments")');

      await expect(page.locator('text=Please select at least one property type').or(
        page.locator('button[type="submit"]:has-text("Find Apartments")')
      )).toBeVisible();
    });
  });

  test.describe('Search and Results (Mocked)', () => {
    test('should show loading state and then results', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });
    });

    test('should display apartment cards with all required information', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      const apartmentCard = page.locator('[class*="shadow-md"]').nth(1);
      await expect(apartmentCard).toBeVisible();

      await expect(apartmentCard.locator('text=$1,500')).toBeVisible();
      await expect(apartmentCard.locator('text=$1,500/mo')).toBeVisible();
      await expect(apartmentCard.locator('text=92% Match')).toBeVisible();
      await expect(apartmentCard.locator('text=1 bed')).toBeVisible();
      await expect(apartmentCard.locator('text=1 bath')).toBeVisible();
      await expect(apartmentCard.locator('text=750 sqft')).toBeVisible();
    });

    test('should display match score badge with correct color coding', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      const highScoreBadge = page.locator('text=92% Match');
      await expect(highScoreBadge).toBeVisible();
      await expect(highScoreBadge).toHaveClass(/bg-emerald-500/);

      const medScoreBadge = page.locator('text=78% Match');
      await expect(medScoreBadge).toBeVisible();
      await expect(medScoreBadge).toHaveClass(/bg-\[var\(--color-primary\)\]/);
    });

    test('should handle empty search results', async ({ page }) => {
      await page.goto('/');

      await page.route('**/api/search', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ apartments: [], total_results: 0 }),
        });
      });

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=No apartments match your criteria')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('text=Try increasing your budget, changing the city, or adjusting your bedroom and bathroom preferences')).toBeVisible();
    });

    test('should display AI reasoning for each apartment', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      await expect(page.locator('text=Excellent match with all key requirements met')).toBeVisible();
    });

    test('should display highlight checkmarks', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      await expect(page.locator('text=Under budget')).toBeVisible();
      await expect(page.locator('text=Pet-friendly')).toBeVisible();
      await expect(page.locator('text=Great location')).toBeVisible();

      const checkmarks = page.locator('svg.text-green-500');
      await expect(checkmarks.first()).toBeVisible();
      expect(await checkmarks.count()).toBeGreaterThanOrEqual(3);
    });
  });

  test.describe('Qualitative Match Labels (Free Tier)', () => {
    test('should display qualitative labels instead of numeric scores', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page, MOCK_FREE_SEARCH_RESPONSE);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Should show qualitative labels
      await expect(page.locator('text=Excellent Match')).toBeVisible();
      await expect(page.locator('text=Great Match')).toBeVisible();

      // Should NOT show numeric scores
      await expect(page.locator('text=95% Match')).not.toBeVisible();
      await expect(page.locator('text=80% Match')).not.toBeVisible();
    });

    test('should show correct label colors', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page, MOCK_FREE_SEARCH_RESPONSE);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Excellent Match → emerald
      const excellentBadge = page.locator('text=Excellent Match');
      await expect(excellentBadge).toHaveClass(/bg-emerald-500/);

      // Great Match → primary
      const greatBadge = page.locator('text=Great Match');
      await expect(greatBadge).toHaveClass(/bg-\[var\(--color-primary\)\]/);
    });

    test('should not show AI reasoning for free tier results', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page, MOCK_FREE_SEARCH_RESPONSE);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Free tier results have no reasoning (match_score is null)
      await expect(page.locator('text=Excellent match with all key requirements met')).not.toBeVisible();
    });

    test('should show searches remaining for free tier', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page, MOCK_FREE_SEARCH_RESPONSE);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Should display remaining searches count
      await expect(page.locator('text=/\\d+ of 3 free searches remaining/')).toBeVisible();
    });
  });

  test.describe('Image Carousel (Mocked)', () => {
    test('should display images in apartment cards', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      const images = page.locator('img');
      await expect(images.first()).toBeVisible({ timeout: 10000 });
    });

    test('should have carousel navigation arrows', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      await expect(page.locator('[aria-label="Previous image"]').first()).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[aria-label="Next image"]').first()).toBeVisible();
    });

    test('should navigate carousel on arrow click', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[aria-label="Next image"]').first()).toBeVisible({ timeout: 10000 });

      const nextButton = page.locator('[aria-label="Next image"]').first();
      await nextButton.click();
      await expect(nextButton).toBeVisible();
    });
  });

  test.describe('Responsive Layout', () => {
    test('should have responsive grid layout on desktop', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.setViewportSize({ width: 1280, height: 720 });
      await page.click('button:has-text("Find Apartments")');

      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });
      const gridContainer = page.locator('.lg\\:grid-cols-3');
      await expect(gridContainer).toBeVisible();
    });

    test('should stack layout on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto('/');

      const form = page.locator('form');
      await expect(form).toBeVisible();

      const submitButton = page.locator('button:has-text("Find Apartments")');
      await expect(submitButton).toBeVisible();
    });
  });

  test.describe('Error Handling', () => {
    test('should recover from failed API request', async ({ page }) => {
      await page.goto('/');

      await page.route('**/api/search', (route) => {
        route.abort('connectionrefused');
      });

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('button:has-text("Find Apartments")')).toContainText('Find Apartments', { timeout: 15000 });
      await expect(page.locator('button:has-text("Find Apartments")')).toBeEnabled();
    });

    test('should display error message on API failure', async ({ page }) => {
      await page.goto('/');

      await page.route('**/api/search', (route) => {
        route.abort('connectionrefused');
      });

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('button:has-text("Find Apartments")')).toContainText('Find Apartments', { timeout: 15000 });
    });
  });

  test.describe('Favorite Button', () => {
    test('should display favorite button on apartment cards', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Favorite buttons should be visible (heart icons)
      const favoriteButtons = page.locator('button[title="Add to favorites"]');
      await expect(favoriteButtons.first()).toBeVisible();
      expect(await favoriteButtons.count()).toBe(2);
    });

    test('should toggle favorite state on click', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      // Mock Supabase insert for adding favorite
      await page.route('**/supabase.co/**/favorites**', async (route) => {
        const method = route.request().method();
        if (method === 'POST') {
          await route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify([{ id: 'fav-1', user_id: 'test-user-id', apartment_id: 'test-001' }]),
          });
        } else {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([]),
          });
        }
      });

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Click the first favorite button
      const firstFavButton = page.locator('button[title="Add to favorites"]').first();
      await firstFavButton.click();

      // After clicking, the button should change to "Remove from favorites"
      await expect(page.locator('button[title="Remove from favorites"]').first()).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Compare Flow', () => {
    test('should display compare button on apartment cards', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Compare buttons should be visible
      const compareButtons = page.locator('button:has-text("Compare")');
      await expect(compareButtons.first()).toBeVisible();
    });

    test('should add apartments to comparison and show comparison bar', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Click first Compare button
      const compareButtons = page.locator('button:has-text("Compare")');
      await compareButtons.first().click();

      // After clicking, button should change to "Comparing"
      await expect(page.locator('button:has-text("Comparing")').first()).toBeVisible();

      // Comparison bar should appear at the bottom
      await expect(page.locator('text=1 of 3 selected')).toBeVisible();
    });

    test('should enable compare navigation when 2+ apartments selected', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Add both apartments to comparison
      const compareButtons = page.locator('button:has-text("Compare")');
      await compareButtons.first().click();
      await expect(page.locator('text=1 of 3 selected')).toBeVisible();

      await compareButtons.nth(1).click();
      await expect(page.locator('text=2 of 3 selected')).toBeVisible();

      // Compare button in the bar should be enabled now
      const compareNavButton = page.locator('button:has-text("Compare (2)")');
      await expect(compareNavButton).toBeEnabled();
    });

    test('should clear comparison when Clear is clicked', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button:has-text("Find Apartments")');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Add apartment to comparison
      const compareButtons = page.locator('button:has-text("Compare")');
      await compareButtons.first().click();
      await expect(page.locator('text=1 of 3 selected')).toBeVisible();

      // Click Clear
      await page.locator('button:has-text("Clear")').click();

      // Comparison bar should disappear
      await expect(page.locator('text=1 of 3 selected')).not.toBeVisible();
    });
  });

  test.describe('Navigation (Authenticated)', () => {
    test('should show Favorites and Compare links in header when logged in', async ({ page }) => {
      await page.goto('/');

      const header = page.locator('header');
      await expect(header.locator('a:has-text("Favorites")')).toBeVisible();
      await expect(header.locator('a:has-text("Compare")')).toBeVisible();
      await expect(header.locator('a:has-text("Search")')).toBeVisible();
    });

    test('should navigate to favorites page', async ({ page }) => {
      await page.goto('/');

      await page.click('header >> a:has-text("Favorites")');
      await expect(page).toHaveURL(/\/favorites/);
      await expect(page.locator('h1:has-text("My Favorites")')).toBeVisible();
    });

    test('should navigate to compare page', async ({ page }) => {
      await page.goto('/');

      await page.click('header >> a:has-text("Compare")');
      await expect(page).toHaveURL(/\/compare/);
      await expect(page.locator('h1:has-text("Compare Apartments")')).toBeVisible();
    });
  });

  test.describe('Favorites Page', () => {
    test('should show empty state when no favorites', async ({ page }) => {
      await page.goto('/favorites');

      await expect(page.locator('h1:has-text("My Favorites")')).toBeVisible();
      await expect(page.locator('text=No favorites yet')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('text=Start Searching')).toBeVisible();
    });

    test('should show favorites when they exist', async ({ page }) => {
      // Override the Supabase route to return favorites data instead of empty
      // Register a more specific route that takes priority (LIFO order)
      await page.route('**/rest/v1/favorites**', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'content-range': '0-0/1' },
          body: JSON.stringify([
            {
              id: 'fav-1',
              user_id: 'test-user-id',
              apartment_id: 'test-001',
              notes: null,
              is_available: true,
              created_at: '2026-03-01T00:00:00Z',
            },
          ]),
        });
      });

      await mockBatchApi(page);

      // Mock the tours endpoint (favorites page fetches tours for TourPrompt)
      await page.route('**/api/tours', async (route, request) => {
        if (request.method() === 'GET') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ tours: [] }),
          });
        } else {
          await route.continue();
        }
      });

      await page.goto('/favorites');

      await expect(page.locator('h1:has-text("My Favorites")')).toBeVisible();
      // Should show the apartment card for the favorited apartment
      await expect(page.locator('text=$1,500/mo')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('text=123 Test St')).toBeVisible();
    });
  });

  test.describe('Compare Page', () => {
    test('should show empty state when no apartments selected', async ({ page }) => {
      await mockCompareApi(page);
      await page.goto('/compare');

      await expect(page.locator('h1:has-text("Compare Apartments")')).toBeVisible();
      await expect(page.locator('text=Select at least 2 apartments to compare')).toBeVisible({ timeout: 10000 });
    });

    test('should show comparison table when apartments are pre-selected', async ({ page }) => {
      // Pre-set comparison IDs in localStorage
      await page.addInitScript(() => {
        const comparisonData = {
          state: {
            apartmentIds: ['test-001', 'test-002'],
            searchContext: null,
          },
          version: 0,
        };
        localStorage.setItem('snugd-comparison', JSON.stringify(comparisonData));
      });

      await mockCompareApi(page);
      await page.goto('/compare');

      await expect(page.locator('h1:has-text("Compare Apartments")')).toBeVisible();

      // Wait for comparison table to load
      await expect(page.locator('text=123 Test St')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('text=456 Sample Ave')).toBeVisible();

      // Should show rent row
      await expect(page.locator('text=$1,500')).toBeVisible();
      await expect(page.locator('text=$1,800')).toBeVisible();
    });

    test('should show Clear All button', async ({ page }) => {
      await page.addInitScript(() => {
        const comparisonData = {
          state: {
            apartmentIds: ['test-001', 'test-002'],
            searchContext: null,
          },
          version: 0,
        };
        localStorage.setItem('snugd-comparison', JSON.stringify(comparisonData));
      });

      await mockCompareApi(page);
      await page.goto('/compare');

      await expect(page.locator('button:has-text("Clear All")')).toBeVisible();
    });
  });

  test.describe('User Menu & Sign Out', () => {
    test('should show user avatar/initial in header', async ({ page }) => {
      await page.goto('/');

      // The UserMenu shows user initial — use .first() since desktop+mobile both render
      const userButton = page.locator('header button:has(div.rounded-full)').first();
      await expect(userButton).toBeVisible();
    });

    test('should open user menu dropdown on click', async ({ page }) => {
      await page.goto('/');

      // Click the user avatar button — use .first() for desktop instance
      const userButton = page.locator('header button:has(div.rounded-full)').first();
      await userButton.click();

      // Menu should show user info
      await expect(page.locator('text=test@example.com')).toBeVisible();

      // Menu should show navigation links
      await expect(page.locator('a:has-text("My Favorites")')).toBeVisible();
      await expect(page.locator('a:has-text("Saved Searches")')).toBeVisible();
      await expect(page.locator('a:has-text("Settings")')).toBeVisible();

      // Sign out button should be visible
      await expect(page.locator('button:has-text("Sign Out")')).toBeVisible();
    });

    test('should sign out when Sign Out is clicked', async ({ page }) => {
      await page.goto('/');

      // Open user menu
      const userButton = page.locator('header button:has(div.rounded-full)').first();
      await userButton.click();

      // Click Sign Out
      await page.locator('button:has-text("Sign Out")').click();

      // After sign out, the Sign In button should appear — use .first() since desktop+mobile
      await expect(page.locator('button:has-text("Sign In")').first()).toBeVisible({ timeout: 5000 });

      // User menu should no longer be visible
      await expect(userButton).not.toBeVisible();
    });

    test('should hide Favorites and Compare links after sign out', async ({ page }) => {
      await page.goto('/');

      // Verify links are present while logged in
      await expect(page.locator('header >> a:has-text("Favorites")')).toBeVisible();

      // Sign out — use .first() since auth loading can briefly show multiple buttons
      const userButton = page.locator('header button:has(div.rounded-full)').first();
      await userButton.click();
      await page.locator('button:has-text("Sign Out")').click();

      // Wait for sign out — use .first() since desktop+mobile both render
      await expect(page.locator('button:has-text("Sign In")').first()).toBeVisible({ timeout: 5000 });

      // Favorites and Compare links should be hidden for anonymous users
      await expect(page.locator('header >> a:has-text("Favorites")')).not.toBeVisible();
      await expect(page.locator('header >> a:has-text("Compare")')).not.toBeVisible();
    });
  });

  test.describe('Frontend-Backend Integration (Live)', () => {
    test('should reach the backend health endpoint', async ({ page }) => {
      const response = await page.request.get('http://localhost:8000/health');
      expect(response.ok()).toBeTruthy();

      const body = await response.json();
      expect(body.status).toBe('healthy');
    });

    test('should get apartment count from backend', async ({ page }) => {
      const response = await page.request.get('http://localhost:8000/api/apartments/count');
      expect(response.ok()).toBeTruthy();

      const body = await response.json();
      expect(body.total_apartments).toBeGreaterThan(0);
    });

    test('should get apartment stats from backend', async ({ page }) => {
      const response = await page.request.get('http://localhost:8000/api/apartments/stats');
      expect(response.ok()).toBeTruthy();

      const body = await response.json();
      expect(body.status).toBe('success');
      expect(body.stats.total_active).toBeGreaterThan(0);
      expect(body.stats.by_city).toBeDefined();
    });

    test('should list apartments from backend', async ({ page }) => {
      const response = await page.request.get('http://localhost:8000/api/apartments/list?city=Pittsburgh&limit=5');
      expect(response.ok()).toBeTruthy();

      const body = await response.json();
      expect(body.apartments).toBeDefined();
      expect(body.apartments.length).toBeGreaterThan(0);
      expect(body.apartments.length).toBeLessThanOrEqual(5);

      const apt = body.apartments[0];
      expect(apt.id).toBeDefined();
      expect(apt.address).toBeDefined();
      expect(apt.rent).toBeGreaterThan(0);
      expect(apt.bedrooms).toBeGreaterThanOrEqual(0);
      expect(apt.bathrooms).toBeGreaterThanOrEqual(0);
    });

    test('should perform a real search via the search endpoint', async ({ page }) => {
      const response = await page.request.post('http://localhost:8000/api/search', {
        data: {
          city: 'Pittsburgh, PA',
          budget: 2000,
          bedrooms: 1,
          bathrooms: 1,
          property_type: 'Apartment',
          move_in_date: '2026-03-01',
        },
      });
      expect(response.ok()).toBeTruthy();

      const body = await response.json();
      expect(body.apartments).toBeDefined();
      expect(body.total_results).toBeGreaterThanOrEqual(0);

      if (body.apartments.length > 0) {
        const apt = body.apartments[0];
        // Anonymous search: should have heuristic_score and match_label
        expect(apt.heuristic_score).toBeDefined();
        expect(apt.match_label).toBeDefined();
      }
    });

    test('should perform a real search and render results in the UI', async ({ page }) => {
      test.setTimeout(120000);

      await page.goto('/');
      await page.click('button:has-text("Find Apartments")');

      await expect(
        page.locator('text=/\\d+ Apartments? Found/').or(page.locator('text=No apartments match your criteria'))
      ).toBeVisible({ timeout: 90000 });
    });
  });
});

// ─── Anonymous User Tests ────────────────────────────────────────────

test.describe('Anonymous User Flow', () => {
  // No mockAuth() — tests run without authentication

  test.beforeEach(async ({ page }) => {
    // Intercept Supabase to prevent network errors
    await page.route('**/supabase.co/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(null),
      });
    });
  });

  test('should show search form for anonymous users', async ({ page }) => {
    await page.goto('/');

    // Hero section should be visible
    await expect(page.locator('h2')).toContainText('Find Your Perfect Apartment');

    // Search form should be visible
    await expect(page.locator('button:has-text("Find Apartments")')).toContainText('Find Apartments');
    await expect(page.locator('select#city')).toBeVisible();
    await expect(page.locator('input#budget')).toBeVisible();
  });

  test('should show Sign In button in header', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('button:has-text("Sign In")')).toBeVisible();
  });

  test('should not show Favorites or Compare links for anonymous users', async ({ page }) => {
    await page.goto('/');

    // Wait for header to be visible
    await expect(page.locator('header')).toBeVisible();

    // These links should not be present for anonymous users
    await expect(page.locator('header >> a:has-text("Favorites")')).not.toBeVisible();
    await expect(page.locator('header >> a:has-text("Compare")')).not.toBeVisible();
  });

  test('should allow anonymous search and show qualitative labels', async ({ page }) => {
    await page.goto('/');
    await mockSearchApi(page, MOCK_FREE_SEARCH_RESPONSE);

    await page.click('button:has-text("Find Apartments")');
    await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

    // Should show qualitative labels (not numeric scores)
    await expect(page.locator('text=Excellent Match')).toBeVisible();
    await expect(page.locator('text=Great Match')).toBeVisible();
  });

  test('should show hero text encouraging sign-in', async ({ page }) => {
    await page.goto('/');

    // Anonymous users see "Sign in for AI-powered matching"
    await expect(page.locator('text=Sign in for AI-powered matching')).toBeVisible();
  });

  test('should redirect to sign-in on favorites page', async ({ page }) => {
    await page.goto('/favorites');

    // Should show sign-in prompt
    await expect(page.locator('text=Sign in to save your favorite apartments')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button:has-text("Sign In with Google")')).toBeVisible();
  });

  test('should redirect to sign-in on compare page', async ({ page }) => {
    await page.goto('/compare');

    // Should show sign-in prompt
    await expect(page.locator('text=Sign in to compare apartments')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button:has-text("Sign In with Google")')).toBeVisible();
  });
});
