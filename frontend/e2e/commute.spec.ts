import { test, expect, Page } from '@playwright/test'

const MOCK_USER = {
  id: 'test-user-commute',
  email: 'commute@test.com',
  user_metadata: { name: 'Commute Tester' },
}

/** Inject mock auth + stub Supabase, mirroring homescout.spec.ts. */
async function mockAuth(page: Page) {
  await page.addInitScript((user: string) => {
    localStorage.setItem('__test_auth_user', user)
  }, JSON.stringify(MOCK_USER))

  await page.route('**/supabase.co/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/rest/v1/profiles')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user_tier: 'free' }),
      })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(null) })
  })
}

test.describe('Commute calculator — settings', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page)
  })

  test('renders saved commute addresses', async ({ page }) => {
    await page.route('**/api/user/locations', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            locations: [
              {
                id: 'loc-1',
                location_type: 'work',
                label: 'Office',
                address: '123 Market St, San Francisco',
                latitude: 37.79,
                longitude: -122.4,
              },
            ],
          }),
        })
      } else {
        await route.fallback()
      }
    })

    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Commute Addresses' })).toBeVisible()
    await expect(page.getByText('Office')).toBeVisible()
    await expect(page.getByText('123 Market St, San Francisco')).toBeVisible()
  })

  test('shows empty state when no addresses are saved', async ({ page }) => {
    await page.route('**/api/user/locations', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ locations: [] }),
        })
      } else {
        await route.fallback()
      }
    })

    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Commute Addresses' })).toBeVisible()
    await expect(page.getByText('No addresses saved yet.')).toBeVisible()
  })
})
