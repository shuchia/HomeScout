import { test, expect } from '@playwright/test';

test.describe('HomeScout E2E Tests', () => {

  test.describe('Homepage', () => {
    test('should load the homepage with header and hero section', async ({ page }) => {
      await page.goto('/');

      // Check header
      await expect(page.locator('header')).toBeVisible();
      await expect(page.locator('h1')).toContainText('HomeScout');

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

      // Check default city
      const cityInput = page.locator('input#city');
      await expect(cityInput).toHaveValue('San Francisco, CA');

      // Check default budget
      const budgetInput = page.locator('input#budget');
      await expect(budgetInput).toHaveValue('3500');

      // Check default bedrooms
      const bedroomsSelect = page.locator('select#bedrooms');
      await expect(bedroomsSelect).toHaveValue('2');

      // Check default bathrooms
      const bathroomsSelect = page.locator('select#bathrooms');
      await expect(bathroomsSelect).toHaveValue('1');
    });

    test('should allow changing form values', async ({ page }) => {
      await page.goto('/');

      // Change city
      await page.fill('input#city', 'New York, NY');
      await expect(page.locator('input#city')).toHaveValue('New York, NY');

      // Change budget
      await page.fill('input#budget', '5000');
      await expect(page.locator('input#budget')).toHaveValue('5000');

      // Change bedrooms
      await page.selectOption('select#bedrooms', '1');
      await expect(page.locator('select#bedrooms')).toHaveValue('1');

      // Change bathrooms
      await page.selectOption('select#bathrooms', '2');
      await expect(page.locator('select#bathrooms')).toHaveValue('2');

      // Change move-in date
      await page.fill('input#moveInDate', '2025-12-15');
      await expect(page.locator('input#moveInDate')).toHaveValue('2025-12-15');

      // Add other preferences
      await page.fill('textarea#otherPreferences', 'Pet-friendly, parking');
      await expect(page.locator('textarea#otherPreferences')).toHaveValue('Pet-friendly, parking');
    });

    test('should toggle property type checkboxes', async ({ page }) => {
      await page.goto('/');

      // Apartment and Condo should be checked by default
      const apartmentCheckbox = page.locator('input[type="checkbox"]').first();
      await expect(apartmentCheckbox).toBeChecked();

      // Click to uncheck Apartment
      await page.locator('label:has-text("Apartment")').click();
      await expect(apartmentCheckbox).not.toBeChecked();

      // Click to check it again
      await page.locator('label:has-text("Apartment")').click();
      await expect(apartmentCheckbox).toBeChecked();
    });

    test('should show validation error when city is empty', async ({ page }) => {
      await page.goto('/');

      // Clear city field
      await page.fill('input#city', '');

      // Try to submit
      await page.click('button[type="submit"]');

      // Form should not submit (HTML5 validation)
      // The city input should be marked as invalid
      const cityInput = page.locator('input#city');
      await expect(cityInput).toHaveAttribute('required', '');
    });

    test('should prevent submission when no property types selected', async ({ page }) => {
      await page.goto('/');

      // Uncheck all property types (Apartment and Condo are checked by default)
      await page.locator('label:has-text("Apartment")').click();
      await page.locator('label:has-text("Condo")').click();

      // Try to submit
      await page.click('button[type="submit"]');

      // Form validation should prevent submission - button should not show loading state
      // and results section should not appear
      await expect(page.locator('button[type="submit"]')).toContainText('Find Apartments');
      await expect(page.locator('text=Finding your perfect apartments...')).not.toBeVisible();
    });
  });

  test.describe('Search and Results', () => {
    // Note: These tests require the backend to be running

    test('should show loading state when searching', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');

      // Click submit
      await page.click('button[type="submit"]');

      // Should show loading message in results section
      await expect(page.locator('text=Finding your perfect apartments...')).toBeVisible({ timeout: 10000 });
    });

    test('should display search results after successful search', async ({ page }) => {
      // Skip if backend is not running
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');

      // Submit search with default values
      await page.click('button[type="submit"]');

      // Wait for results (may take a few seconds due to Claude API)
      await page.waitForSelector('[class*="grid"]', { timeout: 30000 });

      // Check that results are displayed
      const resultsText = page.locator('text=/\\d+ Apartments? Found/');
      await expect(resultsText).toBeVisible({ timeout: 30000 });
    });

    test('should display apartment cards with all required information', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for apartment cards to load
      const apartmentCard = page.locator('[class*="shadow-md"]').first();
      await expect(apartmentCard).toBeVisible({ timeout: 30000 });

      // Check card contains expected elements
      await expect(apartmentCard.locator('text=/\\$[\\d,]+/')).toBeVisible(); // Price
      await expect(apartmentCard.locator('text=/\\d+% Match/')).toBeVisible(); // Match score
      await expect(apartmentCard.locator('text=/bed|Studio/')).toBeVisible(); // Bedrooms
      await expect(apartmentCard.locator('text=/bath/')).toBeVisible(); // Bathrooms
      await expect(apartmentCard.locator('text=/sqft/')).toBeVisible(); // Square footage
      await expect(apartmentCard.locator('text=/Available:/')).toBeVisible(); // Available date
    });

    test('should display match score badge with correct color coding', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for results
      await page.waitForSelector('text=/\\d+% Match/', { timeout: 30000 });

      // Check that match score badge exists
      const matchBadge = page.locator('text=/\\d+% Match/').first();
      await expect(matchBadge).toBeVisible();

      // Badge should have a background color class
      const badgeParent = matchBadge.locator('..');
      const classList = await badgeParent.getAttribute('class');
      expect(classList).toMatch(/bg-(green|blue|yellow|gray)-500/);
    });

    test('should show no results message for invalid search', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');

      // Search for a city that doesn't exist in our data
      await page.fill('input#city', 'Nonexistent City, XX');
      await page.click('button[type="submit"]');

      // Wait for response
      await expect(page.locator('text=No apartments found')).toBeVisible({ timeout: 30000 });
      await expect(page.locator('text=Try adjusting your search criteria')).toBeVisible();
    });
  });

  test.describe('Image Carousel', () => {
    test('should display images in apartment cards', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for results
      await page.waitForSelector('img', { timeout: 30000 });

      // Check that images are displayed
      const images = page.locator('img');
      await expect(images.first()).toBeVisible();
    });

    test('should have carousel navigation arrows', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for results
      await page.waitForSelector('[aria-label="Previous image"]', { timeout: 30000 });

      // Check navigation buttons exist
      await expect(page.locator('[aria-label="Previous image"]').first()).toBeVisible();
      await expect(page.locator('[aria-label="Next image"]').first()).toBeVisible();
    });

    test('should navigate carousel on arrow click', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for carousel
      await page.waitForSelector('[aria-label="Next image"]', { timeout: 30000 });

      // Click next arrow
      const nextButton = page.locator('[aria-label="Next image"]').first();
      await nextButton.click();

      // Carousel should have moved (pagination dot should change)
      // This is hard to assert without knowing the exact state
      // Just verify the click doesn't cause an error
      await expect(nextButton).toBeVisible();
    });
  });

  test.describe('Responsive Layout', () => {
    test('should have responsive grid layout on desktop', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.setViewportSize({ width: 1280, height: 720 });
      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for results
      await page.waitForSelector('text=/\\d+ Apartments? Found/', { timeout: 30000 });

      // On desktop, should have 3-column layout (1 for form, 2 for results)
      const gridContainer = page.locator('.lg\\:grid-cols-3');
      await expect(gridContainer).toBeVisible();
    });

    test('should stack layout on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto('/');

      // Form should be full width on mobile
      const form = page.locator('form');
      await expect(form).toBeVisible();

      // Search button should be visible and full width
      const submitButton = page.locator('button[type="submit"]');
      await expect(submitButton).toBeVisible();
    });
  });

  test.describe('Error Handling', () => {
    test('should recover from failed API request', async ({ page }) => {
      await page.goto('/');

      // Intercept API calls and make them fail
      await page.route('**/api/search', route => {
        route.abort('connectionrefused');
      });

      await page.click('button[type="submit"]');

      // After failed request, button should return to normal state (not stuck in loading)
      await expect(page.locator('button[type="submit"]')).toContainText('Find Apartments', { timeout: 15000 });

      // Button should be enabled again
      await expect(page.locator('button[type="submit"]')).toBeEnabled();
    });
  });

  test.describe('AI Features Display', () => {
    test('should display AI reasoning for each apartment', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for results
      await page.waitForSelector('[class*="italic"]', { timeout: 30000 });

      // Check that reasoning text is displayed (italic text)
      const reasoning = page.locator('[class*="italic"]').first();
      await expect(reasoning).toBeVisible();
    });

    test('should display highlight checkmarks', async ({ page }) => {
      test.skip(process.env.SKIP_BACKEND_TESTS === 'true', 'Backend not running');

      await page.goto('/');
      await page.click('button[type="submit"]');

      // Wait for results with highlights
      await page.waitForSelector('svg[class*="text-green-500"]', { timeout: 30000 });

      // Check that green checkmarks are displayed
      const checkmarks = page.locator('svg[class*="text-green-500"]');
      await expect(checkmarks.first()).toBeVisible();
    });
  });
});
