import { test, expect, Page } from '@playwright/test'

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_TOUR = {
  id: 'tour-001',
  apartment_id: 'test-001',
  stage: 'interested' as const,
  inquiry_email_draft: null,
  outreach_sent_at: null,
  scheduled_date: null,
  scheduled_time: null,
  tour_rating: null,
  toured_at: null,
  notes: [],
  photos: [],
  tags: [],
  decision: null,
  decision_reason: null,
  created_at: '2026-03-15T00:00:00+00:00',
  updated_at: '2026-03-15T00:00:00+00:00',
}

const MOCK_APARTMENT = {
  id: 'test-001',
  address: '123 Test St, Pittsburgh, PA 15213',
  rent: 1500,
  bedrooms: 1,
  bathrooms: 1,
  sqft: 750,
  property_type: 'Apartment',
  available_date: '2026-03-01',
  amenities: ['Parking', 'Laundry'],
  neighborhood: 'Test Neighborhood',
  description: 'A great test apartment',
  images: [],
}

const MOCK_SUGGESTIONS = {
  suggestions: [
    { tag: 'Great light', sentiment: 'pro', count: 0 },
    { tag: 'Spacious', sentiment: 'pro', count: 0 },
    { tag: 'Small kitchen', sentiment: 'con', count: 0 },
  ],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Mock Supabase auth so tests bypass the sign-in gate.
 * Same pattern as snugd.spec.ts.
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
  }

  await page.addInitScript((user: string) => {
    localStorage.setItem('__test_auth_user', user)
  }, JSON.stringify(mockUser))

  await page.route('**/placeholder.supabase.co/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(null),
    })
  })
}

/**
 * Mock all tour-related API endpoints.
 */
async function mockTourApis(
  page: Page,
  options?: {
    tours?: Record<string, unknown>[]
    tour?: Record<string, unknown>
    apartment?: Record<string, unknown>
  },
) {
  const tours = options?.tours ?? [MOCK_TOUR]
  const tour = options?.tour ?? MOCK_TOUR
  const apartment = options?.apartment ?? MOCK_APARTMENT

  // List tours
  await page.route('**/api/tours', async (route, request) => {
    if (request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ tours }),
      })
    } else if (request.method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ tour }),
      })
    } else {
      await route.continue()
    }
  })

  // Single tour (GET / PATCH / DELETE) — but NOT sub-resources like /notes, /photos, /tags
  await page.route('**/api/tours/tour-*', async (route, request) => {
    const url = request.url()
    if (
      url.includes('/notes') ||
      url.includes('/photos') ||
      url.includes('/tags')
    ) {
      await route.continue()
      return
    }

    if (request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ tour }),
      })
    } else if (request.method() === 'PATCH') {
      const body = JSON.parse(request.postData() || '{}')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ tour: { ...tour, ...body } }),
      })
    } else if (request.method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'deleted' }),
      })
    } else {
      await route.continue()
    }
  })

  // Notes
  await page.route('**/api/tours/*/notes**', async (route, request) => {
    if (request.method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          note: {
            id: 'note-new',
            content: 'Test note',
            source: 'typed',
            transcription_status: 'complete',
            created_at: new Date().toISOString(),
          },
        }),
      })
    } else if (request.method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'deleted' }),
      })
    } else {
      await route.continue()
    }
  })

  // Tag suggestions
  await page.route('**/api/tours/tags/suggestions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_SUGGESTIONS),
    })
  })

  // Tags (add / remove)
  await page.route('**/api/tours/*/tags**', async (route, request) => {
    if (request.method() === 'POST') {
      const body = JSON.parse(request.postData() || '{}')
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ tag: { id: 'tag-new', ...body } }),
      })
    } else if (request.method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'deleted' }),
      })
    } else {
      await route.continue()
    }
  })

  // Apartment batch (used by both tour list and tour detail)
  await page.route('**/api/apartments/batch', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([apartment]),
    })
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Tour Pipeline E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page)
  })

  test('tour dashboard loads with tours', async ({ page }) => {
    await mockTourApis(page)
    await page.goto('/tours')

    // Should show "My Tours" heading
    await expect(page.locator('h1:has-text("My Tours")')).toBeVisible()
    // Should show the mock tour's apartment address (partial match)
    await expect(page.locator('text=123 Test St').first()).toBeVisible({ timeout: 10000 })
  })

  test('tour dashboard shows empty state when no tours', async ({ page }) => {
    await mockTourApis(page, { tours: [] })
    await page.goto('/tours')

    // Empty state message
    await expect(
      page.locator('text=started touring').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  test('favorites page shows Start Touring button', async ({ page }) => {
    // Mock favorites from Supabase
    await page.route('**/placeholder.supabase.co/**/favorites*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: [
            {
              id: 'fav-1',
              apartment_id: 'test-001',
              user_id: 'test-user-id',
              is_available: true,
            },
          ],
        }),
      })
    })

    // Mock the apartment batch for the favorite
    await page.route('**/api/apartments/batch', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([MOCK_APARTMENT]),
      })
    })

    // Mock tour list (to check which are already touring)
    await mockTourApis(page, { tours: [] })

    await page.goto('/favorites')

    // Should show "Start Touring" button
    await expect(
      page.locator('text=Start Touring').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  test('tour detail page loads with tabs', async ({ page }) => {
    await mockTourApis(page)
    await page.goto('/tours/tour-001')

    // Should show the three tab buttons (info, capture, email)
    await expect(page.locator('button:has-text("info")').first()).toBeVisible({ timeout: 10000 })
    await expect(page.locator('button:has-text("capture")').first()).toBeVisible()
    await expect(page.locator('button:has-text("email")').first()).toBeVisible()
  })

  test('tour detail shows apartment info on Info tab', async ({ page }) => {
    await mockTourApis(page)
    await page.goto('/tours/tour-001')

    // Info tab should show apartment details
    await expect(page.locator('text=123 Test St').first()).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=$1,500').first()).toBeVisible()
  })

  test('capture tab shows rating and tag sections', async ({ page }) => {
    const toured = { ...MOCK_TOUR, stage: 'toured' as const, tour_rating: 4 }
    await mockTourApis(page, { tour: toured })
    await page.goto('/tours/tour-001')

    // Click Capture tab
    await page.locator('button:has-text("capture")').first().click()

    // Should show rating section heading
    await expect(page.locator('text=Rating').first()).toBeVisible({ timeout: 10000 })
    // Should show tags section heading
    await expect(page.locator('text=Quick Tags').first()).toBeVisible()
  })

  test('add typed note on capture tab', async ({ page }) => {
    await mockTourApis(page)
    await page.goto('/tours/tour-001')

    // Click Capture tab
    await page.locator('button:has-text("capture")').first().click()
    await expect(page.locator('text=Notes').first()).toBeVisible({ timeout: 10000 })

    // Find notes textarea and type a note
    const noteInput = page.locator('textarea[placeholder*="note"]')
    await noteInput.fill('Nice kitchen and bathroom')

    // The Add button should be enabled
    const addBtn = page.locator('button:has-text("Add")').first()
    await expect(addBtn).toBeEnabled()

    // Click add — the mocked POST /notes endpoint will respond with success
    await addBtn.click()
  })

  test('bottom nav is visible on mobile viewport', async ({ page }) => {
    await mockTourApis(page)

    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/tours')

    // The BottomNav renders as <nav class="fixed bottom-0 ...  md:hidden ...">
    // On mobile (< md breakpoint) it should be visible.
    const nav = page.locator('nav.fixed').filter({ hasText: 'Tours' })
    await expect(nav).toBeVisible({ timeout: 10000 })
  })
})
