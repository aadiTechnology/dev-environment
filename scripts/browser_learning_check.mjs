// Sign in through the local browser and check the four CRM forms.
// The password is read from IDENTITY_PASSWORD and is never printed.
import { createRequire } from 'node:module'
import { mkdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const devRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const workspace = join(devRoot, '..')
const evidence = join(devRoot, 'evidence', 'browser')
const password = process.env.IDENTITY_PASSWORD || ''

function redact(value) {
  const text = String(value)
  return password ? text.split(password).join('<redacted>') : text
}

function say(key, value) {
  console.log(`${key}=${redact(value)}`)
}

function fail(message) {
  say('FAILED', message)
  process.exit(1)
}

if (!password) {
  say('FAILED', 'IDENTITY_PASSWORD is not set')
  process.exit(1)
}

const require = createRequire(
  join(workspace, 'MultiTenant', 'Aadi-MultiTenant-Platform', 'frontend', 'package.json'),
)

let chromium
try {
  ;({ chromium } = require('@playwright/test'))
} catch (error) {
  say('browser', 'unavailable')
  say('FAILED', error instanceof Error ? error.name : 'playwright-missing')
  process.exit(2)
}

const state = JSON.parse(readFileSync(join(devRoot, 'config', 'seed-state.json'), 'utf8'))
const catalog = JSON.parse(readFileSync(join(devRoot, 'seeds', 'crm_seed.json'), 'utf8'))
const tenantId = state.tenant_id
if (!tenantId) {
  fail('seed state has no tenant')
}

mkdirSync(evidence, { recursive: true })

async function signIn(page) {
  await page.getByLabel('Email').fill('crm.admin@example.test')
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

const browser = await chromium.launch({ headless: true }).catch((error) => {
  say('browser', 'unavailable')
  const message = error instanceof Error ? error.message.split('\n')[0] : 'browser-launch-failed'
  say('browser_error', message.slice(0, 180))
  process.exit(2)
})

try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } })
  page.setDefaultTimeout(20000)
  await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded' })
  await signIn(page)
  await page.getByText('Aadi CRM Development').first().waitFor()
  await page.screenshot({ path: join(evidence, 'control-plane-home.png'), fullPage: true })
  say('control_plane_home', 'visible')

  await page.goto(`http://localhost:5173/tenants/${tenantId}/products/crm`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: 'CRM is available' }).waitFor()
  await page.getByText('Aadi CRM Development').first().waitFor()
  await page.screenshot({ path: join(evidence, 'control-plane-crm-product.png'), fullPage: true })
  say('crm_product_page', 'visible')

  await page.goto(`http://localhost:5174/tenants/${tenantId}/projects`, { waitUntil: 'domcontentloaded' })
  if (await page.getByLabel('Email').isVisible().catch(() => false)) {
    await signIn(page)
  }
  for (const name of ['Preschool', 'Paneerwala', 'Space View', 'Hiring']) {
    await page.getByText(name, { exact: true }).first().waitFor()
    say('project_visible', name)
  }
  await page.screenshot({ path: join(evidence, 'crm-projects.png'), fullPage: true })

  const projects = await page.evaluate(async (id) => {
    const response = await fetch(`http://localhost:8001/api/v1/tenants/${id}/projects`, { credentials: 'include' })
    if (!response.ok) {
      return { ok: false, status: response.status, items: [] }
    }
    const body = await response.json()
    return { ok: true, status: response.status, items: body.items || [] }
  }, tenantId)
  if (!projects.ok) {
    fail(`CRM projects request returned ${projects.status}`)
  }
  say('crm_projects_api', projects.status)

  for (const project of catalog.projects) {
    const found = projects.items.find((item) => item.code === project.code)
    if (!found) {
      fail(`missing project ${project.code}`)
    }
    const forms = await page.evaluate(async ({ id, projectId }) => {
      const response = await fetch(
        `http://localhost:8001/api/v1/tenants/${id}/projects/${projectId}/forms`,
        { credentials: 'include' },
      )
      if (!response.ok) {
        return { ok: false, status: response.status, items: [] }
      }
      const body = await response.json()
      return { ok: true, status: response.status, items: body.items || [] }
    }, { id: tenantId, projectId: found.id })
    const form = forms.items.find((item) => item.name === project.form_name)
    if (!forms.ok || !form) {
      fail(`missing form ${project.form_name}`)
    }
    await page.goto(
      `http://localhost:5174/tenants/${tenantId}/forms/${found.id}/${form.id}`,
      { waitUntil: 'domcontentloaded' },
    )
    const expected = [...catalog.common_fields, ...project.extra_fields].map((field) => field.label)
    await page.getByText(expected[0], { exact: true }).first().waitFor()
    const strong = (await page.locator('strong').allTextContents()).map((value) => value.trim())
    let position = 0
    for (const label of strong) {
      if (label === expected[position]) {
        position += 1
      }
    }
    const match = position === expected.length
    say(`form_${project.code}`, match ? 'match' : 'mismatch')
    if (!match) {
      fail(`${project.name} form labels were not in order`)
    }
    const canvas = page.getByRole('heading', { name: 'Form canvas' })
    await canvas.scrollIntoViewIfNeeded()
    await page.screenshot({ path: join(evidence, `form-${project.code}.png`), fullPage: true })
  }
  say('RESULT', 'ok')
} catch (error) {
  if (error && typeof error === 'object' && 'code' in error) {
    throw error
  }
  fail(error instanceof Error ? error.message.split('\n')[0].slice(0, 180) : 'browser-check-failed')
} finally {
  await browser.close()
}
