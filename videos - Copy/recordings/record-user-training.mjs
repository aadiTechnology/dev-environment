/**
 * Records four user-training videos against the local Control Plane and CRM.
 * Reads the development password only to type it into a masked field.
 * Does not print the password, and does not create or edit tenant data.
 */
import { spawn } from 'node:child_process'
import crypto from 'node:crypto'
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { performance } from 'node:perf_hooks'
import { fileURLToPath } from 'node:url'

const require = createRequire(
  'C:/Users/lenovo/AadiTech/Product/AadiProduct/MultiTenant/Aadi-MultiTenant-Platform/frontend/package.json',
)
const { chromium } = require('playwright')

const root = path.resolve('C:/Users/lenovo/AadiTech/Product/AadiProduct')
const outDir = path.join(root, 'dev-environment/videos/recordings')
const workDir = path.join(outDir, '.work')
const frameDir = path.join(outDir, 'verification')
const speechScript = path.join(workDir, 'speak.ps1')
const controlPlane = 'http://localhost:5173'
const crmOrigin = 'http://localhost:5174'
const tenantId = '32b4b86c-0103-463e-89c1-f951b3ff9a7c'
const email = 'crm.admin@example.test'
const password = loadPassword()

const only = process.argv[2] ?? ''

function loadPassword() {
  const file = path.join(root, 'dev-environment/config/dev.local.env')
  const text = fs.readFileSync(file, 'utf8')
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith('IDENTITY_PASSWORD=')) continue
    let value = line.slice('IDENTITY_PASSWORD='.length).trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    if (!value) break
    return value
  }
  throw new Error('IDENTITY_PASSWORD is missing from the gitignored local env file.')
}

function redact(error) {
  const message = error instanceof Error ? error.stack ?? error.message : String(error)
  return message.split(password).join('[redacted]')
}

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { windowsHide: true })
    let stderr = ''
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve(stderr)
      else reject(new Error(`${command} exited ${code}: ${stderr.slice(0, 500)}`))
    })
  })
}

function ensureSpeechScript() {
  fs.mkdirSync(workDir, { recursive: true })
  fs.writeFileSync(
    speechScript,
    `
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($env:SPEAK_TEXT, [System.Text.Encoding]::UTF8)
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 0
$synth.SelectVoice('Microsoft Zira Desktop')
$synth.SetOutputToWaveFile($env:SPEAK_WAV)
$synth.Speak($text)
$synth.Dispose()
`.trim(),
    'utf8',
  )
}

async function synthesize(narration) {
  const id = crypto.createHash('sha256').update(narration).digest('hex').slice(0, 16)
  const wav = path.join(workDir, `${id}.wav`)
  if (!fs.existsSync(wav) || fs.statSync(wav).size < 1000) {
    const textFile = path.join(workDir, `${id}.txt`)
    fs.writeFileSync(textFile, narration, 'utf8')
    await new Promise((resolve, reject) => {
      const child = spawn(
        'powershell.exe',
        ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', speechScript],
        {
          windowsHide: true,
          env: { ...process.env, SPEAK_TEXT: textFile, SPEAK_WAV: wav },
        },
      )
      let stderr = ''
      child.stderr.on('data', (chunk) => {
        stderr += chunk.toString()
      })
      child.on('error', reject)
      child.on('close', (code) => {
        if (code === 0) resolve()
        else reject(new Error(`Speech failed (${code}): ${stderr.slice(0, 400)}`))
      })
    })
  }
  return wav
}

async function probeDuration(file) {
  const child = spawn(
    'ffprobe',
    ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file],
    { windowsHide: true },
  )
  let stdout = ''
  child.stdout.on('data', (chunk) => {
    stdout += chunk.toString()
  })
  const code = await new Promise((resolve) => child.on('close', resolve))
  if (code !== 0) throw new Error(`ffprobe failed for ${path.basename(file)}`)
  const seconds = Number(stdout.trim())
  if (!Number.isFinite(seconds) || seconds <= 0) throw new Error(`No duration for ${path.basename(file)}`)
  return seconds
}

async function click(locator) {
  await locator.waitFor({ state: 'visible' })
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox()
  if (box) {
    await locator.page().mouse.move(box.x + Math.min(28, box.width / 2), box.y + Math.min(18, box.height / 2))
    await locator.page().waitForTimeout(200)
  }
  await locator.click()
}

async function glide(locator) {
  await locator.waitFor({ state: 'visible' })
  await locator.scrollIntoViewIfNeeded()
  await locator.page().waitForTimeout(450)
}

async function assertMasked(page) {
  const field = page.locator('input[name="password"], input[type="password"]').first()
  await field.waitFor({ state: 'visible' })
  const type = await field.getAttribute('type')
  if (type !== 'password') throw new Error('The password field is not masked.')
  return field
}

async function assertNoSecret(page) {
  const text = await page.locator('body').innerText()
  if (text.includes(password)) throw new Error('Sensitive text is visible in the page.')
}

function watchWrites(context, bucket) {
  context.on('request', (request) => {
    const method = request.method()
    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return
    let pathname = 'unparsed'
    try {
      pathname = new URL(request.url()).pathname
    } catch {
      pathname = 'unparsed'
    }
    const allowed =
      pathname.endsWith('/api/v1/auth/login') ||
      pathname.endsWith('/api/v1/auth/logout') ||
      pathname.endsWith('/api/v1/auth/renew')
    if (!allowed) bucket.push(`${method} ${pathname}`)
  })
}

async function signInControlPlane(page) {
  await page.goto(`${controlPlane}/login`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: 'Sign in' }).waitFor()
  await page.getByLabel('Email').fill(email)
  const field = await assertMasked(page)
  await field.fill(password)
  await page.waitForTimeout(700)
  await click(page.getByRole('button', { name: 'Sign in', exact: true }))
  await page.getByRole('heading', { name: 'Control Plane web application' }).waitFor()
  await page.getByRole('heading', { name: 'Tenant context' }).waitFor()
}

async function signOutControlPlane(page) {
  await click(page.getByRole('button', { name: /Account menu for/ }))
  await click(page.getByRole('button', { name: 'Sign out', exact: true }))
  await page.getByRole('heading', { name: 'Sign in' }).waitFor()
}

async function signInCrm(page, nextPath) {
  await page.goto(`${crmOrigin}${nextPath}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: 'CRM', exact: true }).waitFor()
  await page.getByLabel('Email').fill(email)
  const field = await assertMasked(page)
  await field.fill(password)
  await page.waitForTimeout(700)
  await click(page.getByRole('button', { name: 'Sign in', exact: true }))
  await page.getByText('CRM is available in this organization.').waitFor()
}

async function openCrmFromControlPlaneSession(page) {
  await page.goto(`${crmOrigin}/tenants/${tenantId}`, { waitUntil: 'domcontentloaded' })
  await page.getByText('CRM is available in this organization.').waitFor()
  await page.getByRole('heading', { name: 'Overview', exact: true }).waitFor()
}

function crmNav(page, name) {
  return page.locator('#workspace-nav a').filter({ hasText: new RegExp(`^${name}$`) })
}

function canvasLine(page, text) {
  return page.locator('.field-list p').filter({ hasText: text }).first()
}

async function openPublishedForm(page, projectName, onCanvas) {
  await click(crmNav(page, 'Forms'))
  await page.getByRole('heading', { name: 'Forms' }).waitFor()
  await click(page.getByRole('link', { name: new RegExp(`^${projectName}\\b`) }).first())
  await page.getByRole('heading', { name: new RegExp(`${projectName} forms`) }).waitFor()
  await click(page.getByRole('link', { name: /fields/ }).first())
  await page.getByRole('heading', { name: projectName, exact: true }).waitFor()
  await glide(page.getByRole('heading', { name: 'Form canvas' }))
  await glide(canvasLine(page, 'Contact / Record Name'))
  if (onCanvas) await onCanvas(page)
  await click(page.getByRole('link', { name: /Render version/ }).first())
  await page.getByRole('heading', { name: 'Published form' }).waitFor()
  await glide(page.locator('label').filter({ hasText: 'Contact / Record Name' }).first())
  await glide(page.locator('label').filter({ hasText: 'Notes' }).first())
}

async function openRecord(page, projectName, recordName, total, beforeOpen) {
  await click(crmNav(page, 'Records'))
  await page.getByRole('heading', { name: 'Records', exact: true }).waitFor()
  await click(page.getByRole('link', { name: new RegExp(`^${projectName}\\b`) }).first())
  await page.getByRole('heading', { name: new RegExp(`Records \\(${total}\\)`) }).waitFor()
  if (beforeOpen) await beforeOpen(page)
  await glide(page.getByText(recordName).first())
  await click(page.getByRole('row', { name: new RegExp(recordName) }).getByRole('link').first())
  await page.getByText(recordName).first().waitFor()
}

const videos = [
  {
    id: '01',
    file: '01-tenant-onboarding-and-crm-access',
    title: 'Open the development tenant and confirm CRM access',
    objective:
      'A learner can see the existing Aadi CRM Development tenant, walk the onboarding steps without creating anything, and confirm that CRM is available.',
    limitations: [
      'The onboarding page can create a tenant, product, feature, plan, or subscription. This recording does not submit those forms.',
      'Step six can load a signed entitlement. The signature is not loaded or shown.',
      'The Control Plane page that says CRM is available only checks access. It does not open the CRM workspace.',
      'On localhost, CRM accepts the Control Plane session. Signing out closes that shared session. localhost and 127.0.0.1 still do not share a session.',
      'The word organization on these screens is the tenant. There is no separate organization record.',
    ],
    scenes: [
      {
        narration:
          'This lesson uses the tenant that is already set up, Aadi CRM Development. We will look at product onboarding and CRM access. We will not create a tenant, a product, a plan, or a subscription. Sign in to the Control Plane. The password stays hidden.',
        run: signInControlPlane,
      },
      {
        narration:
          'The Control Plane home shows Aadi CRM Development under tenant context. On these screens, the word organization means this tenant. The product does not keep a separate organization record.',
        run: async (page) => {
          await glide(page.getByRole('heading', { name: 'Tenant context' }))
          await glide(page.getByRole('link', { name: 'Open product onboarding' }))
        },
      },
      {
        narration:
          'Open product onboarding. This page is for a platform administrator. It has seven steps. Step one lists tenants that already exist.',
        run: async (page) => {
          await click(page.getByRole('link', { name: 'Open product onboarding' }))
          await page.getByRole('heading', { name: 'Product onboarding' }).waitFor()
          await page.getByRole('heading', { name: '1. Tenant' }).waitFor()
          await glide(page.getByRole('button', { name: /Aadi CRM Development/ }))
        },
      },
      {
        narration:
          'Select Aadi CRM Development. The page says that no new tenant was created. The create form is still on the page. Leave it empty.',
        run: async (page) => {
          await click(page.getByRole('button', { name: /Aadi CRM Development/ }))
          await page.getByText('Existing tenant selected. No new tenant was created.').waitFor()
          await glide(page.getByRole('button', { name: 'Create tenant', exact: true }))
          await glide(page.getByText('Existing tenant selected. No new tenant was created.'))
        },
      },
      {
        narration:
          'Go to the product step. Select the CRM product that is already registered. The page says the existing product was selected. No second product is registered.',
        run: async (page) => {
          await click(page.getByRole('button', { name: '2. Product' }))
          await page.getByRole('heading', { name: '2. Product' }).waitFor()
          await click(page.getByRole('button', { name: /crm.{0,3}platform/i }))
          await page.getByText('Existing product selected. No duplicate was registered.').waitFor()
        },
      },
      {
        narration:
          'The features step shows declared feature keys and the commercial feature catalogue. These are catalog definitions. A commercial feature is not the same as a tenant entitlement. We do not save any feature changes.',
        run: async (page) => {
          await click(page.getByRole('button', { name: '3. Features' }))
          await page.getByRole('heading', { name: '3. Features' }).waitFor()
          await glide(page.getByRole('heading', { name: 'Declared feature keys' }))
          await glide(page.getByRole('heading', { name: 'Commercial feature catalogue' }))
          await page.getByText('lead_management').first().waitFor()
          await glide(page.getByText('project_management').first())
          await glide(page.getByText('records').first())
        },
      },
      {
        narration:
          'The plan step shows the CRM Development plan. A plan has no price and no billing cycle. Select the existing plan. The create plan form stays empty, and we do not save plan features.',
        run: async (page) => {
          await click(page.getByRole('button', { name: '4. Plan' }))
          await page.getByRole('heading', { name: '4. Plan' }).waitFor()
          const plan = page.getByRole('button', { name: /crm-development/i })
          await click(plan)
          await page.getByRole('heading', { name: 'Plan features and limits' }).waitFor()
          await glide(page.getByRole('button', { name: 'Save plan features' }))
        },
      },
      {
        narration:
          'The subscription step shows the open subscription for this tenant and CRM. Assigning another subscription is blocked. The status control is on the page. We do not change it.',
        run: async (page) => {
          await click(page.getByRole('button', { name: '5. Subscription' }))
          await page.getByRole('heading', { name: '5. Subscription' }).waitFor()
          await page.getByText('Assigning again is blocked.').waitFor()
          await glide(page.getByText('Assigning again is blocked.'))
        },
      },
      {
        narration:
          'The entitlements step can load a signed result from the platform. That result includes a signature, so this recording does not press Load entitlements. Entitlements are calculated from the active subscription. They are not stored in their own table.',
        run: async (page) => {
          await click(page.getByRole('button', { name: '6. Entitlements' }))
          await page.getByRole('heading', { name: '6. Entitlements' }).waitFor()
          await glide(page.getByRole('button', { name: 'Load entitlements' }))
          await page.getByText('An entitlement result proves').waitFor()
        },
      },
      {
        narration:
          'The review names the selected tenant, product, and plan. Entitlements stay unloaded, so no signature is on screen.',
        run: async (page) => {
          await click(page.getByRole('button', { name: '7. Review' }))
          await page.getByRole('heading', { name: '7. Review' }).waitFor()
          await page.getByText('Entitlements have not been loaded.').first().waitFor()
          await glide(page.getByText('Aadi CRM Development').first())
        },
      },
      {
        narration:
          'Open the tenant. The status is active. This page says that creating a tenant does not create an account. We do not add an account.',
        run: async (page) => {
          await click(page.getByRole('link', { name: 'Open tenant', exact: true }))
          await page.getByRole('heading', { name: 'Aadi CRM Development' }).waitFor()
          await page.getByText('active', { exact: true }).first().waitFor()
          await glide(page.getByText('Creating a tenant does not create an account'))
        },
      },
      {
        narration:
          'The same page shows the CRM product already assigned to this tenant. We do not press Assign a product.',
        run: async (page) => {
          await glide(page.getByRole('button', { name: 'Assign a product' }))
          await page.getByText(/CRM/).first().waitFor()
        },
      },
      {
        narration:
          'Open CRM from the Control Plane. The page says CRM is available, and it names the organization Aadi CRM Development. This page only checks access. It is not the CRM workspace.',
        run: async (page) => {
          await click(page.getByRole('link', { name: 'Open CRM', exact: true }))
          await page.getByRole('heading', { name: 'CRM is available' }).waitFor()
          await page.getByText('Aadi CRM Development').first().waitFor()
        },
      },
      {
        narration:
          'Open the CRM application. On localhost, this browser is already signed in, so CRM does not ask again. The overview says CRM is available in this organization.',
        run: openCrmFromControlPlaneSession,
      },
    ],
  },
  {
    id: '02',
    file: '02-user-access-and-sign-in',
    title: 'Sign in and review user access',
    objective:
      'A learner can sign in to the Control Plane and to CRM, see the development user and role, and sign out of each application.',
    limitations: [
      'Creating a new global account is not available. An existing account can be added by email. This recording does not add or remove anyone.',
      'Role assignment controls are on the users page. This recording does not assign or remove a role.',
      'Control Plane sign-out is inside the account menu.',
      'On localhost, CRM and the Control Plane share the sign-in session. Signing out of the Control Plane closes that session, so CRM asks for the password again. localhost and 127.0.0.1 do not share a session.',
    ],
    scenes: [
      {
        narration:
          'This lesson shows sign-in and user access for the development account. We do not create an account, and we do not change a role. The Control Plane sign-in page asks for an email and a password. The password box hides every character.',
        run: async (page) => {
          await page.goto(`${controlPlane}/login`, { waitUntil: 'domcontentloaded' })
          await page.getByRole('heading', { name: 'Sign in' }).waitFor()
          await assertMasked(page)
        },
      },
      {
        narration:
          'Sign in as crm.admin@example.test. After sign-in, that email appears at the top of the page.',
        run: async (page) => {
          await page.getByLabel('Email').fill(email)
          const field = await assertMasked(page)
          await field.fill(password)
          await page.waitForTimeout(800)
          await click(page.getByRole('button', { name: 'Sign in', exact: true }))
          await page.getByRole('heading', { name: 'Control Plane web application' }).waitFor()
          await page.getByRole('button', { name: /Account menu for crm\.admin@example\.test/ }).waitFor()
        },
      },
      {
        narration:
          'Open Aadi CRM Development. The tenant administrator section says you can assign an existing account and a tenant role. Creating a new global account is not available.',
        run: async (page) => {
          await glide(page.getByRole('heading', { name: 'Tenant context' }))
          await click(page.getByRole('link', { name: 'Open tenant', exact: true }))
          await page.getByRole('heading', { name: 'Aadi CRM Development' }).waitFor()
          await glide(page.getByRole('heading', { name: 'Tenant administrator' }))
          await glide(page.getByText('creating a new global account is not available', { exact: false }))
        },
      },
      {
        narration:
          'Open View users. The development account is already a member. The note says creating a new global account is not available. The form adds an existing account by email. Leave that form blank. We do not press Add to tenant, and we do not remove anyone.',
        run: async (page) => {
          await click(page.getByRole('link', { name: 'View users' }))
          await page.getByRole('heading', { name: 'Users' }).waitFor()
          await glide(page.getByText(email).first())
          await glide(page.getByText('Creating a new global account is not available.'))
        },
      },
      {
        narration:
          'Press View access. This reads the permissions already on the role. It does not change them. The development role can read leads and manage projects.',
        run: async (page) => {
          await click(page.getByRole('button', { name: `View access for ${email}` }))
          await page.getByRole('heading', { name: 'Role permissions' }).waitFor()
          await glide(page.getByText('crm.lead_management.read').first())
          await glide(page.getByText('crm.project_management.manage').first())
        },
      },
      {
        narration:
          'Open View roles. The CRM Development role is listed. We do not rename it, assign it, or remove it.',
        run: async (page) => {
          await page.goto(`${controlPlane}/tenants/${tenantId}`, { waitUntil: 'domcontentloaded' })
          await page.getByRole('heading', { name: 'Aadi CRM Development' }).waitFor()
          await click(page.getByRole('link', { name: 'View roles' }))
          await page.getByRole('heading', { name: 'Roles' }).waitFor()
          await glide(page.getByText('CRM Development').first())
          await glide(page.getByText('crm_development').first())
        },
      },
      {
        narration:
          'Open the account menu, then sign out. The sign-in page comes back, and the Control Plane session is closed.',
        run: signOutControlPlane,
      },
      {
        narration:
          'After signing out, open CRM. The shared localhost session is closed, so CRM asks for the email and password again. Use the same email. The password stays hidden.',
        run: async (page) => {
          await page.goto(`${crmOrigin}/`, { waitUntil: 'domcontentloaded' })
          await page.getByRole('heading', { name: 'CRM', exact: true }).waitFor()
          await page.getByLabel('Email').fill(email)
          const field = await assertMasked(page)
          await field.fill(password)
          await page.waitForTimeout(800)
          await click(page.getByRole('button', { name: 'Sign in', exact: true }))
          await page.getByRole('heading', { name: 'Organizations' }).waitFor()
        },
      },
      {
        narration:
          'CRM lists the tenant as an organization. Choose Aadi CRM Development. The workspace shows the signed-in email. Leads and Projects are available for this sign-in.',
        run: async (page) => {
          await click(page.getByRole('link', { name: 'Aadi CRM Development' }))
          await page.getByText('CRM is available in this organization.').waitFor()
          await page.getByText(email).first().waitFor()
          await glide(crmNav(page, 'Leads'))
          await glide(crmNav(page, 'Projects'))
        },
      },
      {
        narration:
          'Sign out of CRM as well. Each application closes its own session. The CRM sign-in page returns.',
        run: async (page) => {
          await click(page.getByRole('button', { name: 'Sign out', exact: true }))
          await page.getByRole('heading', { name: 'CRM', exact: true }).waitFor()
        },
      },
    ],
  },
  {
    id: '03',
    file: '03-working-with-four-crm-projects',
    title: 'Work with Preschool, Paneerwala, Space View, and Hiring',
    objective:
      'A learner can open the four CRM projects, read each published form, and open one sample record in each project.',
    limitations: [
      'The form builder can edit, move, or remove fields. This recording opens the published form and does not press those buttons.',
      'Records can be edited or archived from the record page. This recording only reads them.',
      'Sample people and phone numbers are fictional. Notes are marked as seed data.',
      'No project, form, or record is created.',
    ],
    scenes: [
      {
        narration:
          'This lesson opens the four CRM projects: Preschool, Paneerwala, Space View, and Hiring. The sample people and phone numbers are fictional. We will not create a project, edit a form, or change a record. Sign in to CRM. The password stays hidden.',
        run: (page) => signInCrm(page, `/tenants/${tenantId}/projects`),
      },
      {
        narration:
          'All four projects are active. Preschool is for school enquiries. Paneerwala is for paneer orders. Space View is for interior and space planning. Hiring is for candidates.',
        run: async (page) => {
          await click(crmNav(page, 'Projects'))
          await page.getByRole('heading', { name: 'Projects', exact: true }).waitFor()
          for (const name of ['Hiring', 'Paneerwala', 'Preschool', 'Space View']) {
            await glide(page.getByRole('link', { name: new RegExp(`^${name}\\b`) }).first())
          }
        },
      },
      {
        narration:
          'Open Preschool. The description says Expected Value is the opportunity amount. The project is active.',
        run: async (page) => {
          await click(page.getByRole('link', { name: /^Preschool\b/ }).first())
          await page.getByRole('heading', { name: 'Preschool', exact: true }).waitFor()
          await page.getByRole('paragraph').filter({ hasText: 'Expected Value is the opportunity amount.' }).first().waitFor()
        },
      },
      {
        narration:
          'Open the Preschool form. The form builder lists the fields and shows buttons to edit or remove a field. We do not press them. Then open the published form. Every project starts with the same ten fields: Contact or Record Name, Contact Person, Phone Number, Lead Source, Status, Priority, Last Contact Date, Next Follow-up Date, Expected Value, and Notes. Phone Number uses the mobile field. Preschool then adds Number of Students, Number of Branches, and Product of Interest.',
        run: async (page) => {
          await openPublishedForm(page, 'Preschool', async (current) => {
            await glide(canvasLine(current, 'Number of Students'))
            await glide(canvasLine(current, 'Product of Interest'))
            await glide(canvasLine(current, 'Preschool ERP'))
          })
        },
      },
      {
        narration:
          'Preschool has four records. Riverside Tiny Steps came from the import file. Open Northside Learning Circle. The status is New, and the product of interest is Preschool ERP. We do not edit or archive the record.',
        run: async (page) => {
          await openRecord(page, 'Preschool', 'Northside Learning Circle', 4, async (current) => {
            await glide(current.getByText('Riverside Tiny Steps', { exact: true }))
          })
          await glide(page.getByText('Status', { exact: true }).first())
          await page.getByText('New', { exact: true }).first().waitFor()
          await glide(page.getByText('Preschool ERP').first())
        },
      },
      {
        narration:
          'Open Paneerwala. Expected Value is the opportunity. Order Amount is a separate field for the order. The published form adds Product or Variant, Quantity, Order Amount, and Payment Status. The variants are Fresh Paneer, Malai Paneer, and Other.',
        run: async (page) => {
          await click(crmNav(page, 'Projects'))
          await click(page.getByRole('link', { name: /^Paneerwala\b/ }).first())
          await page.getByRole('paragraph').filter({ hasText: 'Order Amount is the order.' }).first().waitFor()
          await openPublishedForm(page, 'Paneerwala', async (current) => {
            await glide(canvasLine(current, 'Product / Variant'))
            await glide(canvasLine(current, 'Order Amount'))
            await glide(canvasLine(current, 'Fresh Paneer, Malai Paneer, Other'))
          })
        },
      },
      {
        narration:
          'Paneerwala has three records. Open Evening Tiffin Co. The status is In Progress, the variant is Malai Paneer, and Order Amount is separate from Expected Value.',
        run: async (page) => {
          await openRecord(page, 'Paneerwala', 'Evening Tiffin Co', 3)
          await glide(page.getByText('In Progress').first())
          await glide(page.getByText('Malai Paneer').first())
          await glide(page.getByText('Order Amount', { exact: true }).first())
          await glide(page.getByText('Expected Value', { exact: true }).first())
        },
      },
      {
        narration:
          'Open Space View. The extra fields are Service Type, Service Location, and Requirement Details. The service types are Interior Design, Space Planning, and Other.',
        run: async (page) => {
          await click(crmNav(page, 'Projects'))
          await click(page.getByRole('link', { name: /^Space View\b/ }).first())
          await page.getByRole('paragraph').filter({ hasText: 'interior and space-planning' }).first().waitFor()
          await openPublishedForm(page, 'Space View', async (current) => {
            await glide(canvasLine(current, 'Service Type'))
            await glide(canvasLine(current, 'Requirement Details'))
            await glide(canvasLine(current, 'Interior Design, Space Planning, Other'))
          })
        },
      },
      {
        narration:
          'Space View has three records. Open Maple Street Apartment. The service type is Interior Design, and the service location is Pune.',
        run: async (page) => {
          await openRecord(page, 'Space View', 'Maple Street Apartment', 3)
          await glide(page.getByText('Interior Design').first())
          await glide(page.getByText('Pune').first())
        },
      },
      {
        narration:
          'Open Hiring. Status, Recruitment Stage, and Recruitment Outcome are three different fields. Positions include Sales Resource, Accountant, Accounting and Sales, and Interior Designer.',
        run: async (page) => {
          await click(crmNav(page, 'Projects'))
          await click(page.getByRole('link', { name: /^Hiring\b/ }).first())
          await page.getByRole('paragraph').filter({ hasText: 'Recruitment Outcome is the hiring result.' }).first().waitFor()
          await openPublishedForm(page, 'Hiring', async (current) => {
            await glide(canvasLine(current, 'Position Applied For'))
            await glide(canvasLine(current, 'Recruitment Stage'))
            await glide(canvasLine(current, 'Recruitment Outcome'))
            await glide(canvasLine(current, 'Sales Resource, Accountant, Accounting & Sales, Interior Designer'))
          })
        },
      },
      {
        narration:
          'Hiring has three records. Open Tara Menon. The status is Converted, the recruitment stage is Hired, and the recruitment outcome is Hired. Those three values answer different questions. The four projects and their sample records stay as they were.',
        run: async (page) => {
          await openRecord(page, 'Hiring', 'Tara Menon', 3)
          await glide(page.getByText('Converted').first())
          await glide(page.getByText('Recruitment Stage', { exact: true }).first())
          await glide(page.getByText('Hired').first())
          await glide(page.getByText('Recruitment Outcome', { exact: true }).first())
        },
      },
    ],
  },
  {
    id: '04',
    file: '04-dashboard-and-lead-tracking',
    title: 'Use project KPIs, follow-ups, and record status',
    objective:
      'A learner can see what this CRM uses instead of a dashboard, and how a lead is tracked through record status and follow-up queues.',
    narrateAfter: true,
    limitations: [
      'There is no page named Dashboard. The overview only confirms that CRM is available.',
      'Project KPIs for Preschool returns an error: the request could not be completed. Retry does not load the counts. The recording does not invent numbers.',
      'A successful KPI report would say that record status is not counted. That sentence stays hidden while the report is failing.',
      'The Leads page is empty. It does not list Preschool, Paneerwala, Space View, or Hiring records.',
      'Follow-up queues use India Standard Time. The today queue can be empty.',
      'The date fields remain on the failed KPI page. This recording does not apply a new period, because the report fails before it can show counts.',
    ],
    scenes: [
      {
        narration:
          'This lesson looks for a dashboard and for lead tracking. There is no page named Dashboard. The overview only says that CRM is available. Reporting is on Project KPIs. The Leads page does not list project records. Sign in to CRM. The password stays hidden.',
        run: (page) => signInCrm(page, `/tenants/${tenantId}`),
      },
      {
        narration:
          'Open Project KPIs and choose Preschool. The report does not load. The page says the request could not be completed. Press Retry. The same message comes back. The records are not changed.',
        run: async (page) => {
          await click(crmNav(page, 'KPIs'))
          await page.getByRole('heading', { name: 'Project KPIs' }).waitFor()
          await click(page.getByRole('link', { name: /^Preschool\b/ }).first())
          await page.getByText('The request could not be completed.').waitFor()
          await click(page.getByRole('button', { name: 'Retry' }))
          await page.getByText('The request could not be completed.').waitFor()
        },
      },
      {
        narration:
          'The page still says that record dates use the UTC calendar day, and that follow-up dates use India Standard Time. It does not show a count of active records. Lead status is read from the record itself, after the follow-up queues.',
        run: async (page) => {
          await glide(page.getByText('Record dates use the UTC calendar day.'))
          await glide(page.getByText('The request could not be completed.'))
        },
      },
      {
        narration:
          'Open Leads. The screen says that no leads are open in this shell. This is the real Leads page. It does not show the Preschool, Paneerwala, Space View, or Hiring records.',
        run: async (page) => {
          await click(crmNav(page, 'Leads'))
          await page.getByRole('heading', { name: 'Leads', exact: true }).waitFor()
          await page.getByText('No leads are open in this shell.').waitFor()
        },
      },
      {
        narration:
          'Open Follow-ups and choose Preschool. Queues use India Standard Time, and a follow-up is in one queue only. The page opens on today. On this date, no follow-up is due today.',
        run: async (page) => {
          await click(crmNav(page, 'Follow-ups'))
          await page.getByRole('heading', { name: 'Follow-ups', exact: true }).waitFor()
          await click(page.getByRole('link', { name: /^Preschool\b/ }).first())
          await page.getByRole('heading', { name: 'Follow-ups due today' }).waitFor()
          await page.getByText('No follow-ups are due today.').waitFor()
        },
      },
      {
        narration:
          'Open the overdue queue. These follow-ups were due before today. Hillview Kids Campus is in this list. Its sample call was due on the first of October.',
        run: async (page) => {
          await click(page.getByRole('navigation', { name: 'Follow-up queues' }).getByRole('link', { name: 'Overdue' }))
          await page.getByRole('heading', { name: 'Overdue follow-ups' }).waitFor()
          await glide(page.getByText('Hillview Kids Campus', { exact: true }))
        },
      },
      {
        narration:
          'Open the upcoming queue. These follow-ups are due after today. Northside Learning Circle has a follow-up in November.',
        run: async (page) => {
          await click(page.getByRole('navigation', { name: 'Follow-up queues' }).getByRole('link', { name: 'Upcoming' }))
          await page.getByRole('heading', { name: 'Upcoming follow-ups' }).waitFor()
          await glide(page.getByText('Northside Learning Circle', { exact: true }))
        },
      },
      {
        narration:
          'Open the Preschool record for Northside Learning Circle. Status, the next follow-up date, and the follow-up queues are how this CRM tracks a lead. There is no separate lead pipeline beyond those fields. We do not edit the record.',
        run: async (page) => {
          await click(page.getByRole('row', { name: /Northside Learning Circle/ }).getByRole('link').first())
          await page.getByText('Northside Learning Circle').first().waitFor()
          await glide(page.getByText('Status', { exact: true }).first())
          await glide(page.getByText('Next Follow-up Date', { exact: true }).first())
          await page.getByText('New', { exact: true }).first().waitFor()
        },
      },
    ],
  },
]

function writeScript(spec, duration) {
  const minutes = Math.max(1, Math.round(duration / 60))
  const lines = [
    `# ${spec.title}`,
    '',
    '**Audience:** A person learning the Aadi Control Plane and Aadi CRM.',
    '',
    `**Duration:** About ${minutes} minute${minutes === 1 ? '' : 's'} (${duration.toFixed(1)} seconds in the file).`,
    '',
    `**Video file:** \`dev-environment/videos/recordings/${spec.file}.mp4\``,
    '',
    '**Learning objective:** ' + spec.objective,
    '',
    '## What the recording shows',
    '',
    ...spec.scenes.map((scene, index) => `${index + 1}. ${scene.narration}`),
    '',
    '## UI limitations',
    '',
    ...spec.limitations.map((item) => `- ${item}`),
    '',
    '## How this file was recorded',
    '',
    'Chromium opened the local Control Plane at http://localhost:5173 and CRM at http://localhost:5174. Playwright recorded the browser viewport while the script clicked, typed, and scrolled. Narration was spoken by the Windows voice Microsoft Zira Desktop and mixed into the MP4. The development password was typed only into a masked password field.',
    '',
    'The screenshots in `dev-environment/evidence/browser/` were not used as frames in this video.',
    '',
    'No tenant, user, subscription, project, form, record, or follow-up was created or edited.',
    '',
  ]
  fs.writeFileSync(path.join(outDir, `${spec.file}.md`), lines.join('\n'), 'utf8')
}

async function mux(webm, cues, destination) {
  const videoSeconds = await probeDuration(webm)
  const last = cues[cues.length - 1]
  const audioEnd = last.start + last.seconds + 0.4
  const total = Math.max(videoSeconds, audioEnd)
  const extra = Math.max(0, audioEnd - videoSeconds)
  const filter = []
  const inputs = ['-y', '-i', webm]
  cues.forEach((cue, index) => {
    inputs.push('-i', cue.wav)
    const delay = Math.round(Math.max(0, cue.start) * 1000)
    filter.push(`[${index + 1}:a]adelay=${delay}|${delay},apad=pad_dur=0.2,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a${index}]`)
  })
  const mixInputs = cues.map((_, index) => `[a${index}]`).join('')
  filter.push(
    `${mixInputs}amix=inputs=${cues.length}:duration=longest:dropout_transition=0:normalize=0,atrim=0:${total.toFixed(3)},asetpts=PTS-STARTPTS[aout]`,
  )
  const videoFilter = extra > 0.05 ? `tpad=stop_mode=clone:stop_duration=${extra.toFixed(3)}` : 'null'
  filter.push(`[0:v]${videoFilter},format=yuv420p[vout]`)
  await run('ffmpeg', [
    ...inputs,
    '-filter_complex',
    filter.join(';'),
    '-map',
    '[vout]',
    '-map',
    '[aout]',
    '-c:v',
    'libx264',
    '-preset',
    'veryfast',
    '-crf',
    '20',
    '-c:a',
    'aac',
    '-b:a',
    '128k',
    '-movflags',
    '+faststart',
    destination,
  ])
  return probeDuration(destination)
}

async function extractFrames(file, cues, id) {
  fs.mkdirSync(frameDir, { recursive: true })
  const picks = [cues[0], cues[Math.floor(cues.length / 2)], cues[cues.length - 1]]
  const written = []
  for (let index = 0; index < picks.length; index += 1) {
    const at = Math.max(0.4, picks[index].start + Math.min(1.2, picks[index].seconds / 2))
    const frame = path.join(frameDir, `${id}-${index + 1}.jpg`)
    await run('ffmpeg', [
      '-y',
      '-ss',
      at.toFixed(2),
      '-i',
      file,
      '-frames:v',
      '1',
      '-q:v',
      '3',
      frame,
    ])
    written.push({ at, frame })
  }
  return written
}

async function recordOne(browser, spec) {
  console.log(`Recording ${spec.file}`)
  const prepared = []
  for (const scene of spec.scenes) {
    const wav = await synthesize(scene.narration)
    const seconds = await probeDuration(wav)
    prepared.push({ ...scene, wav, seconds })
  }
  const writes = []
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    locale: 'en-US',
    timezoneId: 'Asia/Kolkata',
    colorScheme: 'light',
    reducedMotion: 'no-preference',
    recordVideo: { dir: workDir, size: { width: 1600, height: 900 } },
  })
  watchWrites(context, writes)
  const page = await context.newPage()
  page.setDefaultTimeout(25000)
  page.setDefaultNavigationTimeout(30000)
  const t0 = performance.now()
  const cues = []
  const video = page.video()
  try {
    for (let index = 0; index < prepared.length; index += 1) {
      const scene = prepared[index]
      if (writes.length > 0) {
        throw new Error(`Unexpected write before scene ${index + 1}: ${writes.join('; ')}`)
      }
      console.log(`  scene ${index + 1}/${prepared.length}`)
      if (spec.narrateAfter) await scene.run(page)
      const start = (performance.now() - t0) / 1000
      cues.push({ start, seconds: scene.seconds, narration: scene.narration, wav: scene.wav })
      if (!spec.narrateAfter) await scene.run(page)
      await assertNoSecret(page)
      if (writes.length > 0) {
        throw new Error(`Unexpected write in scene ${index + 1}: ${writes.join('; ')}`)
      }
      const elapsed = (performance.now() - t0) / 1000 - start
      const remain = spec.narrateAfter
        ? scene.seconds + 0.8
        : Math.max(scene.seconds + 0.45 - elapsed, 3)
      await page.waitForTimeout(remain * 1000)
    }
    await page.waitForTimeout(600)
  } catch (error) {
    const shot = path.join(frameDir, `${spec.id}-failure.jpg`)
    fs.mkdirSync(frameDir, { recursive: true })
    await page.screenshot({ path: shot, fullPage: false }).catch(() => {})
    throw error
  } finally {
    await context.close()
  }
  const webm = await video.path()
  const destination = path.join(outDir, `${spec.file}.mp4`)
  const duration = await mux(webm, cues, destination)
  fs.rmSync(webm, { force: true })
  writeScript(spec, duration)
  const frames = await extractFrames(destination, cues, spec.id)
  return {
    file: destination,
    duration,
    frames,
    scenes: cues.length,
    writes,
  }
}

async function main() {
  ensureSpeechScript()
  fs.mkdirSync(frameDir, { recursive: true })
  const selected = videos.filter((video) => !only || video.id === only || video.file === only)
  if (selected.length === 0) throw new Error(`No video matches ${only}`)
  const browser = await chromium.launch({ headless: true, slowMo: 60 })
  const results = []
  try {
    for (const spec of selected) {
      results.push(await recordOne(browser, spec))
    }
  } finally {
    await browser.close()
  }
  const summary = results.map((result) => ({
    file: path.relative(root, result.file).replaceAll('\\', '/'),
    durationSeconds: Number(result.duration.toFixed(1)),
    scenes: result.scenes,
    frames: result.frames.map((frame) => ({
      at: Number(frame.at.toFixed(2)),
      file: path.relative(root, frame.frame).replaceAll('\\', '/'),
    })),
    unexpectedWrites: result.writes,
  }))
  fs.writeFileSync(path.join(outDir, 'verification-summary.json'), JSON.stringify(summary, null, 2), 'utf8')
  console.log(JSON.stringify(summary, null, 2))
}

main().catch((error) => {
  console.error(redact(error))
  process.exit(1)
})
