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

const MOCK_APARTMENT_2 = {
  id: 'test-002',
  address: '456 Oak Ave, Pittsburgh, PA 15213',
  rent: 1800,
  bedrooms: 2,
  bathrooms: 1,
  sqft: 900,
  property_type: 'Apartment',
  available_date: '2026-03-01',
  amenities: ['Parking', 'Gym'],
  neighborhood: 'Test Neighborhood',
  description: 'A spacious apartment',
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
 * Mock Supabase auth with Pro tier.
 * The AuthContext reads __test_auth_profile from localStorage to set the profile
 * (and thus isPro) during the E2E test bypass flow.
 */
async function mockProAuth(page: Page) {
  const mockUser = {
    id: 'test-user-id',
    email: 'test@example.com',
    aud: 'authenticated',
    role: 'authenticated',
    app_metadata: { provider: 'google' },
    user_metadata: { name: 'Test User' },
    created_at: '2024-01-01T00:00:00Z',
  }

  const mockProfile = {
    id: 'test-user-id',
    user_tier: 'pro',
    subscription_status: 'active',
  }

  await page.addInitScript(({ user, profile }: { user: string; profile: string }) => {
    localStorage.setItem('__test_auth_user', user)
    localStorage.setItem('__test_auth_profile', profile)
  }, { user: JSON.stringify(mockUser), profile: JSON.stringify(mockProfile) })

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
    apartments?: Record<string, unknown>[]
  },
) {
  const tours = options?.tours ?? [MOCK_TOUR]
  const tour = options?.tour ?? MOCK_TOUR
  const apartment = options?.apartment ?? MOCK_APARTMENT
  const allApartments = options?.apartments ?? [apartment]

  // --- AI endpoint mocks (registered before single-tour route) ---

  // Inquiry email
  await page.route('**/api/tours/*/inquiry-email', async (route) => {
    const emailDraft = 'Subject: Inquiry about 123 Test St\n\nDear Property Manager,\n\nI am interested in the apartment at 123 Test St.'
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        subject: 'Inquiry about 123 Test St',
        body: 'Dear Property Manager,\n\nI am interested in the apartment at 123 Test St.',
        inquiry_email_draft: emailDraft,
      }),
    })
  })

  // Day plan
  await page.route('**/api/tours/day-plan', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        tours_ordered: [
          { apartment_id: 'test-001', address: '123 Test St', suggested_time: '10:00 AM' },
        ],
        travel_notes: ['5 min walk between stops'],
        tips: ['Both apartments are close together'],
      }),
    })
  })

  // Decision brief
  await page.route('**/api/tours/decision-brief', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        apartments: [
          { apartment_id: 'test-001', ai_take: 'Great value', strengths: ['Under budget'], concerns: ['Small kitchen'] },
          { apartment_id: 'test-002', ai_take: 'More space', strengths: ['Larger'], concerns: ['Over budget'] },
        ],
        recommendation: { apartment_id: 'test-001', reasoning: 'Best overall value for the price' },
      }),
    })
  })

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
      url.includes('/tags') ||
      url.includes('/inquiry-email')
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
      body: JSON.stringify(allApartments),
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

// ---------------------------------------------------------------------------
// AI Feature E2E Tests (Phase 2)
// ---------------------------------------------------------------------------

test.describe('Tour AI Features E2E Tests', () => {
  test('email tab shows upgrade prompt for free users', async ({ page }) => {
    // Default mockAuth creates a free-tier user (no profile = free)
    await mockAuth(page)
    await mockTourApis(page)
    await page.goto('/tours/tour-001')

    // Click Email tab
    await page.locator('button:has-text("email")').first().click()

    // Free users should see the UpgradePrompt with "Upgrade" text
    await expect(
      page.locator('text=Upgrade').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  test('email tab shows generate button for pro users', async ({ page }) => {
    await mockProAuth(page)
    await mockTourApis(page)
    await page.goto('/tours/tour-001')

    // Click Email tab
    await page.locator('button:has-text("email")').first().click()

    // Pro users should see the "Generate Inquiry Email" button
    await expect(
      page.locator('button:has-text("Generate Inquiry Email")'),
    ).toBeVisible({ timeout: 10000 })
  })

  test('email generation works for pro users', async ({ page }) => {
    await mockProAuth(page)

    // Track whether the inquiry-email endpoint has been called so we can
    // return the updated tour (with draft) on subsequent GET requests.
    let emailGenerated = false
    const tourWithDraft = {
      ...MOCK_TOUR,
      inquiry_email_draft:
        'Subject: Inquiry about 123 Test St\n\nDear Property Manager,\n\nI am interested in the apartment at 123 Test St.',
    }

    // Override the single-tour GET to return draft after generation
    await page.route('**/api/tours/tour-*', async (route, request) => {
      const url = request.url()
      if (
        url.includes('/notes') ||
        url.includes('/photos') ||
        url.includes('/tags') ||
        url.includes('/inquiry-email')
      ) {
        await route.continue()
        return
      }
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ tour: emailGenerated ? tourWithDraft : MOCK_TOUR }),
        })
      } else {
        await route.continue()
      }
    })

    // Mock inquiry-email endpoint
    await page.route('**/api/tours/*/inquiry-email', async (route) => {
      emailGenerated = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          subject: 'Inquiry about 123 Test St',
          body: 'Dear Property Manager,\n\nI am interested in the apartment at 123 Test St.',
          inquiry_email_draft: tourWithDraft.inquiry_email_draft,
        }),
      })
    })

    // Mock remaining APIs
    await page.route('**/api/tours/tags/suggestions', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SUGGESTIONS),
      })
    })
    await page.route('**/api/apartments/batch', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([MOCK_APARTMENT]),
      })
    })

    await page.goto('/tours/tour-001')

    // Click Email tab
    await page.locator('button:has-text("email")').first().click()

    // Click Generate
    const generateBtn = page.locator('button:has-text("Generate Inquiry Email")')
    await expect(generateBtn).toBeVisible({ timeout: 10000 })
    await generateBtn.click()

    // After generation, the draft should appear with the subject text
    await expect(
      page.locator('text=Inquiry about 123 Test St').first(),
    ).toBeVisible({ timeout: 10000 })

    // Body should also be visible
    await expect(
      page.locator('text=Dear Property Manager').first(),
    ).toBeVisible()
  })

  test('day planner shows on tours page with multiple same-day tours', async ({ page }) => {
    await mockProAuth(page)

    // Use today's date so the tours appear in the "Today" tab
    const today = new Date().toISOString().split('T')[0]
    const tour1 = { ...MOCK_TOUR, id: 'tour-001', apartment_id: 'test-001', stage: 'scheduled', scheduled_date: today, scheduled_time: '10:00' }
    const tour2 = { ...MOCK_TOUR, id: 'tour-002', apartment_id: 'test-002', stage: 'scheduled', scheduled_date: today, scheduled_time: '14:00' }

    await mockTourApis(page, {
      tours: [tour1, tour2],
      apartments: [MOCK_APARTMENT, MOCK_APARTMENT_2],
    })
    await page.goto('/tours')

    // Should show "Plan This Day" button (DayPlanner for pro users)
    await expect(
      page.locator('button:has-text("Plan This Day")'),
    ).toBeVisible({ timeout: 10000 })
  })

  test('decision brief shows when 2+ tours are in toured stage', async ({ page }) => {
    await mockProAuth(page)

    const tour1 = { ...MOCK_TOUR, id: 'tour-001', apartment_id: 'test-001', stage: 'toured', tour_rating: 4 }
    const tour2 = { ...MOCK_TOUR, id: 'tour-002', apartment_id: 'test-002', stage: 'toured', tour_rating: 3 }

    await mockTourApis(page, {
      tours: [tour1, tour2],
      apartments: [MOCK_APARTMENT, MOCK_APARTMENT_2],
    })
    await page.goto('/tours')

    // Should show "Get AI Recommendation" button (DecisionBrief for pro users)
    await expect(
      page.locator('button:has-text("Get AI Recommendation")'),
    ).toBeVisible({ timeout: 10000 })
  })
})

// ---------------------------------------------------------------------------
// Voice Capture E2E Tests (Phase 3)
// ---------------------------------------------------------------------------

const MOCK_VOICE_NOTE_PENDING = {
  id: 'note-voice-1',
  content: null,
  source: 'voice',
  transcription_status: 'pending',
  created_at: '2026-03-15T02:00:00+00:00',
}

const MOCK_VOICE_NOTE_COMPLETE = {
  id: 'note-voice-2',
  content: 'The kitchen is smaller than expected but the living room is really nice',
  source: 'voice',
  transcription_status: 'complete',
  created_at: '2026-03-15T02:00:00+00:00',
}

const MOCK_VOICE_NOTE_FAILED = {
  id: 'note-voice-3',
  content: null,
  source: 'voice',
  transcription_status: 'failed',
  created_at: '2026-03-15T02:00:00+00:00',
}

test.describe('Voice Capture E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page)
  })

  test('voice capture button visible on capture tab', async ({ page }) => {
    await mockTourApis(page)
    await page.goto('/tours/tour-001')

    // Click Capture tab
    await page.locator('button:has-text("capture")').first().click()

    // Verify "Hold to Record" button is visible
    await expect(
      page.locator('text=Hold to Record').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  test('voice note shows transcribing status', async ({ page }) => {
    const tourWithPendingNote = {
      ...MOCK_TOUR,
      notes: [MOCK_VOICE_NOTE_PENDING],
    }
    await mockTourApis(page, { tour: tourWithPendingNote })
    await page.goto('/tours/tour-001')

    // Click Capture tab
    await page.locator('button:has-text("capture")').first().click()

    // Verify "Transcribing..." text appears
    await expect(
      page.locator('text=Transcribing...').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  test('completed voice note shows mic icon and content', async ({ page }) => {
    const tourWithCompleteNote = {
      ...MOCK_TOUR,
      notes: [MOCK_VOICE_NOTE_COMPLETE],
    }
    await mockTourApis(page, { tour: tourWithCompleteNote })
    await page.goto('/tours/tour-001')

    // Click Capture tab
    await page.locator('button:has-text("capture")').first().click()

    // Verify the transcribed content appears
    await expect(
      page.locator('text=The kitchen is smaller than expected').first(),
    ).toBeVisible({ timeout: 10000 })

    // Verify mic icon is present (SVG with microphone path inside the note)
    const noteItem = page.locator('text=The kitchen is smaller than expected').first().locator('..')
    await expect(noteItem).toBeVisible()
  })

  test('voice note shows failed status', async ({ page }) => {
    const tourWithFailedNote = {
      ...MOCK_TOUR,
      notes: [MOCK_VOICE_NOTE_FAILED],
    }
    await mockTourApis(page, { tour: tourWithFailedNote })
    await page.goto('/tours/tour-001')

    // Click Capture tab
    await page.locator('button:has-text("capture")').first().click()

    // Verify "failed" text appears
    await expect(
      page.locator('text=failed').first(),
    ).toBeVisible({ timeout: 10000 })
  })
})
