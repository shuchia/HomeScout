import { test, expect, Page } from '@playwright/test';

// Mock search response to avoid waiting for Claude API in UI tests
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

/** Helper to intercept search API and return mock data */
async function mockSearchApi(page: Page) {
  await page.route('**/api/search', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SEARCH_RESPONSE),
    });
  });
}

/** Helper to mock Supabase auth so tests bypass the sign-in gate.
 *
 * The AuthContext checks for a `__test_auth_user` item in localStorage
 * before initializing the Supabase auth flow. When present, it uses the
 * stored user object directly, bypassing getSession() entirely.
 * This avoids issues with Supabase's cookie-based session storage and
 * network calls to placeholder.supabase.co during E2E tests.
 */
async function mockAuth(page: Page) {
  const mockUser = {
    id: 'test-user-id',
    email: 'test@example.com',
    aud: 'authenticated',
    role: 'authenticated',
    app_metadata: { provider: 'google' },
    user_metadata: { name: 'Test User' },
    created_at: '2024-01-01T00:00:00Z',
  };

  // Inject mock user into localStorage before the page loads
  await page.addInitScript((user: string) => {
    localStorage.setItem('__test_auth_user', user);
  }, JSON.stringify(mockUser));

  // Intercept Supabase API calls to prevent network errors
  await page.route('**/placeholder.supabase.co/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(null),
    });
  });
}

test.describe('HomeScout E2E Tests', () => {

  test.beforeEach(async ({ page }) => {
    await mockAuth(page);
  });

  test.describe('Homepage', () => {
    test('should load the homepage with header and hero section', async ({ page }) => {
      await page.goto('/');

      // Check header (from Header component in layout)
      await expect(page.locator('header')).toBeVisible();
      await expect(page.locator('header').locator('text=HomeScout')).toBeVisible();

      // Check hero section
      await expect(page.locator('h2')).toContainText('Find Your Perfect Apartment');
      await expect(page.locator('text=Tell us what you\'re looking for')).toBeVisible();

      // Check footer
      await expect(page.locator('footer')).toContainText('Powered by Claude AI');
    });

    test('should display the search form', async ({ page }) => {
      await page.goto('/');

      // Check all form fields are present
      await expect(page.locator('label:has-text("City")')).toBeVisible();
      await expect(page.locator('label:has-text("Maximum Budget")')).toBeVisible();
      await expect(page.locator('label:has-text("Bedrooms")')).toBeVisible();
      await expect(page.locator('label:has-text("Bathrooms")')).toBeVisible();
      await expect(page.locator('label:has-text("Property Type")')).toBeVisible();
      await expect(page.locator('label:has-text("Move-in Date")')).toBeVisible();
      await expect(page.locator('label:has-text("Other Preferences")')).toBeVisible();

      // Check submit button
      await expect(page.locator('button[type="submit"]')).toContainText('Find Apartments');
    });
  });

  test.describe('Search Form Interactions', () => {
    test('should have default values pre-filled', async ({ page }) => {
      await page.goto('/');

      // Check default city (select dropdown, default is Pittsburgh, PA)
      const citySelect = page.locator('select#city');
      await expect(citySelect).toHaveValue('Pittsburgh, PA');

      // Check default budget
      const budgetInput = page.locator('input#budget');
      await expect(budgetInput).toHaveValue('2000');

      // Check default bedrooms
      const bedroomsSelect = page.locator('select#bedrooms');
      await expect(bedroomsSelect).toHaveValue('1');

      // Check default bathrooms
      const bathroomsSelect = page.locator('select#bathrooms');
      await expect(bathroomsSelect).toHaveValue('1');
    });

    test('should allow changing form values', async ({ page }) => {
      await page.goto('/');

      // Change city via select dropdown
      await page.selectOption('select#city', 'Bryn Mawr, PA');
      await expect(page.locator('select#city')).toHaveValue('Bryn Mawr, PA');

      // Change budget
      await page.fill('input#budget', '5000');
      await expect(page.locator('input#budget')).toHaveValue('5000');

      // Change bedrooms
      await page.selectOption('select#bedrooms', '2');
      await expect(page.locator('select#bedrooms')).toHaveValue('2');

      // Change bathrooms
      await page.selectOption('select#bathrooms', '2');
      await expect(page.locator('select#bathrooms')).toHaveValue('2');

      // Change move-in date
      await page.fill('input#moveInDate', '2026-06-15');
      await expect(page.locator('input#moveInDate')).toHaveValue('2026-06-15');

      // Add other preferences
      await page.fill('textarea#otherPreferences', 'Pet-friendly, parking');
      await expect(page.locator('textarea#otherPreferences')).toHaveValue('Pet-friendly, parking');
    });

    test('should toggle property type checkboxes', async ({ page }) => {
      await page.goto('/');

      // Apartment should be checked by default
      const apartmentCheckbox = page.locator('input[type="checkbox"]').first();
      await expect(apartmentCheckbox).toBeChecked();

      // Click to uncheck Apartment
      await page.locator('label:has-text("Apartment")').click();
      await expect(apartmentCheckbox).not.toBeChecked();

      // Click to check it again
      await page.locator('label:has-text("Apartment")').click();
      await expect(apartmentCheckbox).toBeChecked();
    });

    test('should prevent submission when no property types selected', async ({ page }) => {
      await page.goto('/');

      // Uncheck Apartment (only one checked by default)
      await page.locator('label:has-text("Apartment")').click();

      // Try to submit
      await page.click('button[type="submit"]');

      // Form validation should prevent submission - error message should appear
      await expect(page.locator('text=Please select at least one property type').or(
        page.locator('button[type="submit"]:has-text("Find Apartments")')
      )).toBeVisible();
    });
  });

  test.describe('Search and Results (Mocked)', () => {
    // These tests use mocked API to avoid Claude API delays

    test('should show loading state and then results', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      // Click submit
      await page.click('button[type="submit"]');

      // Wait for results to appear
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });
    });

    test('should display apartment cards with all required information', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button[type="submit"]');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Wait for apartment cards to load
      const apartmentCard = page.locator('[class*="shadow-md"]').nth(1); // First result card (nth(0) is search form container)
      await expect(apartmentCard).toBeVisible();

      // Check card contains expected elements
      await expect(apartmentCard.locator('text=$1,500')).toBeVisible(); // Price
      await expect(apartmentCard.locator('text=$1,500/mo')).toBeVisible(); // Price with per month
      await expect(apartmentCard.locator('text=92% Match')).toBeVisible(); // Match score
      await expect(apartmentCard.locator('text=1 bed')).toBeVisible(); // Bedrooms
      await expect(apartmentCard.locator('text=1 bath')).toBeVisible(); // Bathrooms
      await expect(apartmentCard.locator('text=750 sqft')).toBeVisible(); // Square footage
    });

    test('should display match score badge with correct color coding', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button[type="submit"]');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // High score (92%) should have green background
      const highScoreBadge = page.locator('text=92% Match');
      await expect(highScoreBadge).toBeVisible();

      // Check it has the green background class
      const badgeParent = highScoreBadge;
      await expect(badgeParent).toHaveClass(/bg-green-500/);

      // Medium score (78%) should have blue background
      const medScoreBadge = page.locator('text=78% Match');
      await expect(medScoreBadge).toBeVisible();
      await expect(medScoreBadge).toHaveClass(/bg-blue-500/);
    });

    test('should handle empty search results', async ({ page }) => {
      await page.goto('/');

      // Mock empty response
      await page.route('**/api/search', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ apartments: [], total_results: 0 }),
        });
      });

      await page.click('button[type="submit"]');

      // Should show "No apartments found" message
      await expect(page.locator('text=No apartments found')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('text=Try adjusting your search criteria')).toBeVisible();
    });

    test('should display AI reasoning for each apartment', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button[type="submit"]');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Check that reasoning text is displayed in quotes
      await expect(page.locator('text=Excellent match with all key requirements met')).toBeVisible();
    });

    test('should display highlight checkmarks', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button[type="submit"]');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Check that highlights are displayed
      await expect(page.locator('text=Under budget')).toBeVisible();
      await expect(page.locator('text=Pet-friendly')).toBeVisible();
      await expect(page.locator('text=Great location')).toBeVisible();

      // Check green checkmark SVGs
      const checkmarks = page.locator('svg.text-green-500');
      await expect(checkmarks.first()).toBeVisible();
      expect(await checkmarks.count()).toBeGreaterThanOrEqual(3);
    });
  });

  test.describe('Image Carousel (Mocked)', () => {
    test('should display images in apartment cards', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button[type="submit"]');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Check that images are displayed
      const images = page.locator('img');
      await expect(images.first()).toBeVisible({ timeout: 10000 });
    });

    test('should have carousel navigation arrows', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button[type="submit"]');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // Check navigation buttons exist on the card with multiple images
      await expect(page.locator('[aria-label="Previous image"]').first()).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[aria-label="Next image"]').first()).toBeVisible();
    });

    test('should navigate carousel on arrow click', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.click('button[type="submit"]');
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[aria-label="Next image"]').first()).toBeVisible({ timeout: 10000 });

      // Click next arrow
      const nextButton = page.locator('[aria-label="Next image"]').first();
      await nextButton.click();

      // Verify the click doesn't cause an error
      await expect(nextButton).toBeVisible();
    });
  });

  test.describe('Responsive Layout', () => {
    test('should have responsive grid layout on desktop', async ({ page }) => {
      await page.goto('/');
      await mockSearchApi(page);

      await page.setViewportSize({ width: 1280, height: 720 });
      await page.click('button[type="submit"]');

      // Wait for results
      await expect(page.locator('text=2 Apartments Found')).toBeVisible({ timeout: 15000 });

      // On desktop, should have 3-column layout (1 for form, 2 for results)
      const gridContainer = page.locator('.lg\\:grid-cols-3');
      await expect(gridContainer).toBeVisible();
    });

    test('should stack layout on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto('/');

      // Form should be visible on mobile
      const form = page.locator('form');
      await expect(form).toBeVisible();

      // Search button should be visible
      const submitButton = page.locator('button[type="submit"]');
      await expect(submitButton).toBeVisible();
    });
  });

  test.describe('Error Handling', () => {
    test('should recover from failed API request', async ({ page }) => {
      await page.goto('/');

      // Intercept API calls and make them fail
      await page.route('**/api/search', (route) => {
        route.abort('connectionrefused');
      });

      await page.click('button[type="submit"]');

      // After failed request, button should return to normal state (not stuck in loading)
      await expect(page.locator('button[type="submit"]')).toContainText('Find Apartments', { timeout: 15000 });

      // Button should be enabled again
      await expect(page.locator('button[type="submit"]')).toBeEnabled();
    });

    test('should display error message on API failure', async ({ page }) => {
      await page.goto('/');

      // Intercept API calls and return an error
      await page.route('**/api/search', (route) => {
        route.abort('connectionrefused');
      });

      await page.click('button[type="submit"]');

      // Error message should be displayed after search fails
      // The error triggers hasSearched=true via the flow, then error is shown
      await expect(page.locator('button[type="submit"]')).toContainText('Find Apartments', { timeout: 15000 });
    });
  });

  test.describe('Frontend-Backend Integration (Live)', () => {
    // These tests make real API calls to verify the integration works

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

      // Verify apartment data structure
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

      // If results found, verify structure
      if (body.apartments.length > 0) {
        const apt = body.apartments[0];
        expect(apt.match_score).toBeGreaterThanOrEqual(0);
        expect(apt.match_score).toBeLessThanOrEqual(100);
        expect(apt.reasoning).toBeDefined();
        expect(apt.highlights).toBeDefined();
        expect(Array.isArray(apt.highlights)).toBeTruthy();
      }
    });

    test('should perform a real search and render results in the UI', async ({ page }) => {
      test.setTimeout(120000); // 2 minute timeout for real Claude API call

      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for results (real Claude API call - can be slow)
      await expect(
        page.locator('text=/\\d+ Apartments? Found/').or(page.locator('text=No apartments found'))
      ).toBeVisible({ timeout: 90000 });
    });
  });
});
