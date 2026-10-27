import { test, expect } from '@playwright/test'

// The front door (2026-10-26): `/` is the landing page for visitors and a
// redirect to /search for signed-in users. Invite codes are saved from the
// URL and redeemed after sign-in.

test.describe('Front door', () => {
  test('visitor sees the landing page and can start searching without signing in', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Stop apartment hunting/i })).toBeVisible()
    await expect(page.getByText('Open Snugd Beta')).toHaveCount(0)

    await page.getByRole('link', { name: 'Start searching →' }).click()
    await expect(page).toHaveURL(/\/search$/)
  })

  test('?code= is saved for redemption after sign-in and shown to the visitor', async ({ page }) => {
    await page.goto('/?code=beta-linkedin')
    await expect(page.getByText(/You're invited via LinkedIn/)).toBeVisible()
    await expect(page.getByText('BETA-LINKEDIN')).toBeVisible()
    expect(await page.evaluate(() => localStorage.getItem('snugd-pending-invite'))).toBe('BETA-LINKEDIN')
  })

  test('old /landing links keep their invite code', async ({ page }) => {
    await page.goto('/landing?code=BETA-REDDIT')
    await expect(page).toHaveURL(/\/\?code=BETA-REDDIT$/)
    await expect(page.getByText(/You're invited via Reddit/)).toBeVisible()
  })

  test('signed-in user is sent straight to search', async ({ page }) => {
    await page.addInitScript((user: string) => {
      localStorage.setItem('__test_auth_user', user)
    }, JSON.stringify({ id: 'landing-test-user', email: 'landing@example.com' }))
    await page.route('**/placeholder.supabase.co/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: 'null' }))

    await page.goto('/')
    await expect(page).toHaveURL(/\/search$/)
  })

  test('saved invite is redeemed once the user is signed in', async ({ page }) => {
    const redeemed: string[] = []
    await page.route('**/api/invite/redeem', async route => {
      redeemed.push(route.request().postDataJSON().code)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, message: 'Code applied.' }) })
    })
    await page.route('**/placeholder.supabase.co/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: 'null' }))
    await page.addInitScript((user: string) => {
      localStorage.setItem('__test_auth_user', user)
      localStorage.setItem('snugd-pending-invite', 'BETA-PNC')
    }, JSON.stringify({ id: 'landing-test-user', email: 'landing@example.com' }))

    await page.goto('/search')
    await expect.poll(() => redeemed).toEqual(['BETA-PNC'])
  })

  test('privacy policy and terms are linked from the footer', async ({ page }) => {
    await page.goto('/')
    await page.locator('footer').getByRole('link', { name: 'Privacy' }).click()
    await expect(page).toHaveURL(/\/privacy$/, { timeout: 30_000 })
    await expect(page.getByRole('heading', { name: 'Privacy Policy', level: 1 })).toBeVisible()
    await expect(page.getByRole('link', { name: 'privacy@snugd.ai' }).first()).toBeVisible()

    await page.goto('/')
    await page.locator('footer').getByRole('link', { name: 'Terms' }).click()
    await expect(page).toHaveURL(/\/terms$/, { timeout: 30_000 })
    await expect(page.getByRole('heading', { name: 'Terms of Service', level: 1 })).toBeVisible()
  })

  test('settings deletes the account after a second confirmation', async ({ page }) => {
    let deletes = 0
    await page.route('**/api/account', async route => {
      if (route.request().method() === 'DELETE') deletes++
      await route.fulfill({ status: 204, body: '' })
    })
    await page.route('**/placeholder.supabase.co/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: 'null' }))
    // Signed in on /settings only: after deletion the app navigates to /, and
    // an init script that re-adds the mock user there would undo the sign-out.
    await page.addInitScript((user: string) => {
      if (location.pathname === '/settings') localStorage.setItem('__test_auth_user', user)
      else localStorage.removeItem('__test_auth_user')
    }, JSON.stringify({ id: 'delete-test-user', email: 'delete@example.com' }))

    await page.goto('/settings')
    await page.getByRole('button', { name: 'Delete my account' }).click()
    await expect(page.getByText('Delete your Snugd account?')).toBeVisible()
    expect(deletes).toBe(0)  // first click only asks

    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByText('Delete your Snugd account?')).toHaveCount(0)

    await page.getByRole('button', { name: 'Delete my account' }).click()
    await page.getByRole('button', { name: 'Delete permanently' }).click()
    await expect(page).toHaveURL(/account=deleted/, { timeout: 30_000 })
    expect(deletes).toBe(1)
    await expect(page.getByText('Your account and everything in it have been deleted.')).toBeVisible()
  })

  test('a failed deletion keeps the user on settings with the error', async ({ page }) => {
    await page.route('**/api/account', route =>
      route.fulfill({ status: 500, contentType: 'application/json',
        body: JSON.stringify({ detail: "Couldn't delete your files. Your account is still there; please try again." }) }))
    await page.route('**/placeholder.supabase.co/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: 'null' }))
    await page.addInitScript((user: string) => {
      localStorage.setItem('__test_auth_user', user)
    }, JSON.stringify({ id: 'delete-test-user', email: 'delete@example.com' }))

    await page.goto('/settings')
    await page.getByRole('button', { name: 'Delete my account' }).click()
    await page.getByRole('button', { name: 'Delete permanently' }).click()
    await expect(page.getByText(/Your account is still there/)).toBeVisible()
    await expect(page).toHaveURL(/\/settings$/)
  })
})
