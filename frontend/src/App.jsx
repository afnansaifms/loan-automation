import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  createApplication, getApplication, deleteApplication, listApplications,
  uploadStatement, processStatement, getLatestStatement,
  uploadDocument, processDocument, listDocuments, verifyApplication,
} from './api'

/* ---------- helpers ---------- */

const inr = (n) =>
  n == null ? '—' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(n)
const num = (n) => (n == null ? '—' : new Intl.NumberFormat('en-IN').format(n))
const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
const prettify = (s) => (s || '').replace(/_/g, ' ')
const shortDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
const safeParse = (s) => {
  try { return JSON.parse(s) } catch { return {} }
}

const METRICS = {
  average_balance: { label: 'Average balance', fmt: inr },
  total_credits: { label: 'Total money in', fmt: inr },
  total_debits: { label: 'Total money out', fmt: inr },
  avg_monthly_salary: { label: 'Average monthly salary', fmt: inr },
  salary_credit_count: { label: 'Salary credits found', fmt: num },
  emi_to_income_ratio: { label: 'EMI to income', fmt: pct },
  income_stability_cv: { label: 'Income volatility', fmt: (v) => (v == null ? '—' : v.toFixed(2)) },
}

const GREEN = ['#F0FDF4', '#15803D', '#BBF7D0']
const AMBER = ['#FFFBEB', '#B45309', '#FDE68A']
const RED = ['#FEF2F2', '#B91C1C', '#FECACA']
const BLUE = ['#EFF6FF', '#1D4ED8', '#BFDBFE']
const NEUTRAL = ['#F8FAFC', '#64748B', '#E2E8F0']
const BADGES = {
  approve: GREEN, pass: GREEN, manual_review: AMBER, reject: RED, fail: RED,
  processed: BLUE, insufficient_data: NEUTRAL, intake: NEUTRAL,
}
const DECISION_LABEL = { approve: 'Approve', manual_review: 'Needs review', reject: 'Reject' }
const DOC_LABEL = { salary_slip: 'Salary slip', itr: 'ITR', form16: 'Form 16', kyc: 'KYC document', unknown: 'Unrecognized document' }
const CATEGORY_COLORS = {
  salary: '#15803D', emi: '#B45309', rent: '#B45309', utilities: '#0E7490', investment: '#1D4ED8',
  merchant_spend: '#7C3AED', transfer: '#64748B', cash_withdrawal: '#B91C1C', other: '#94A3B8',
}
const catColor = (c) => CATEGORY_COLORS[c] || CATEGORY_COLORS.other
const CHECK_LABEL = {
  pan_consistency: 'PAN consistency',
  name_consistency: 'Name consistency',
  salary_vs_bank_credits: 'Salary vs bank credits',
}
const cleanReason = (s) => (s || '').replace(/[\[\]']/g, '').replace(/_/g, ' ')

/* ---------- small building blocks ---------- */

function Badge({ value, label }) {
  const [bg, fg, border] = BADGES[value] || NEUTRAL
  return (
    <span
      style={{ background: bg, color: fg, border: `1px solid ${border}` }}
      className="px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap"
    >
      {label || DECISION_LABEL[value] || prettify(value) || '—'}
    </span>
  )
}

function Card({ title, subtitle, action, children }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-6">
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">{title}</h3>
            {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </div>
  )
}

const Notice = ({ children }) => <p className="text-sm text-red-600 mt-3">{children}</p>

const PrimaryButton = ({ children, ...props }) => (
  <button
    {...props}
    className="bg-slate-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-slate-700 disabled:opacity-40 whitespace-nowrap"
  >
    {children}
  </button>
)

function UploadRow({ inputKey, hasFile, busy, onPick, onRun, idleLabel, busyLabel }) {
  return (
    <div className="flex items-center gap-3">
      <input
        key={inputKey}
        type="file"
        accept="application/pdf"
        onChange={(e) => onPick(e.target.files[0] || null)}
        className="text-sm text-slate-600 flex-1 min-w-0"
      />
      <PrimaryButton onClick={onRun} disabled={!hasFile || busy}>
        {busy ? busyLabel : idleLabel}
      </PrimaryButton>
    </div>
  )
}

function RiskBar({ score }) {
  if (score == null) return null
  const color = score < 30 ? '#15803D' : score < 60 ? '#B45309' : '#B91C1C'
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-40 rounded-full bg-slate-100 overflow-hidden">
        <div style={{ width: `${Math.min(score, 100)}%`, background: color }} className="h-full" />
      </div>
      <span className="text-sm font-semibold text-slate-900">{score}</span>
      <span className="text-xs text-slate-400">out of 100, lower is safer</span>
    </div>
  )
}

/* ---------- statement tab ---------- */

function sumBy(transactions, field) {
  const totals = {}
  transactions.forEach((t) => {
    if (t[field]) {
      const c = t.category || 'other'
      totals[c] = (totals[c] || 0) + t[field]
    }
  })
  return Object.entries(totals).sort((a, b) => b[1] - a[1])
}

function BarList({ title, entries }) {
  const max = entries.length ? entries[0][1] : 1
  return (
    <div>
      <div className="text-xs font-medium text-slate-500 mb-3">{title}</div>
      {entries.length === 0 ? (
        <p className="text-sm text-slate-400">None</p>
      ) : (
        <div className="space-y-3">
          {entries.map(([cat, total]) => (
            <div key={cat}>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-slate-700 capitalize">{prettify(cat)}</span>
                <span className="text-slate-500">{inr(total)}</span>
              </div>
              <div className="h-1.5 rounded-full bg-slate-100">
                <div style={{ width: `${(total / max) * 100}%`, background: catColor(cat) }} className="h-full rounded-full" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AssessmentCard({ data }) {
  return (
    <Card title="Assessment" subtitle={`${num(data.transaction_count)} transactions analysed from ${data.filename}`}>
      <div className="flex flex-wrap items-center gap-4 mb-4">
        <Badge value={data.eligibility_flag} />
        <RiskBar score={data.risk_score} />
      </div>
      {data.reasons?.length > 0 && (
        <ul className="text-sm text-slate-600 space-y-1 list-disc list-inside mb-5">
          {data.reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Object.entries(METRICS).map(([key, meta]) => (
          <div key={key} className="bg-slate-50 rounded-md p-3">
            <div className="text-[11px] text-slate-500 mb-1">{meta.label}</div>
            <div className="text-base font-semibold text-slate-900">{meta.fmt(data.metrics?.[key])}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function ReconciliationCard({ rec }) {
  const hasStated = rec && rec.stated_total_credits != null && rec.stated_total_debits != null
  return (
    <Card
      title="Reconciliation"
      subtitle="Our totals checked against the totals printed on the bank's own statement."
      action={
        hasStated ? (
          rec.matches_statement
            ? <Badge value="pass" label="Matches the statement" />
            : <Badge value="manual_review" label="Does not match" />
        ) : null
      }
    >
      {!hasStated ? (
        <p className="text-sm text-slate-400">This statement does not print summary totals to check against.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-400 text-left">
              <th className="py-1 font-normal"></th>
              <th className="py-1 font-normal text-right">Statement says</th>
              <th className="py-1 font-normal text-right">We computed</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Total credits', rec.stated_total_credits, rec.computed_total_credits],
              ['Total debits', rec.stated_total_debits, rec.computed_total_debits],
            ].map(([label, stated, computed]) => (
              <tr key={label} className="border-t border-slate-100">
                <td className="py-2 text-slate-700">{label}</td>
                <td className="py-2 text-right text-slate-900">{inr(stated)}</td>
                <td className="py-2 text-right text-slate-900">{inr(computed)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}

const PAGE_SIZE = 15

function TransactionsTable({ transactions }) {
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('all')
  const [page, setPage] = useState(0)

  const cats = useMemo(() => [...new Set(transactions.map((t) => t.category || 'other'))].sort(), [transactions])
  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase()
    return transactions.filter(
      (t) =>
        (cat === 'all' || (t.category || 'other') === cat) &&
        (!term || (t.description || '').toLowerCase().includes(term) || (t.date || '').toLowerCase().includes(term)),
    )
  }, [transactions, q, cat])

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const current = Math.min(page, pages - 1)
  const slice = filtered.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE)

  return (
    <Card title="Transactions" subtitle={`${num(filtered.length)} of ${num(transactions.length)} shown`}>
      <div className="flex flex-wrap gap-2 mb-4">
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(0) }}
          placeholder="Search description or date"
          className="flex-1 min-w-[200px] border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
        />
        <select
          value={cat}
          onChange={(e) => { setCat(e.target.value); setPage(0) }}
          className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          <option value="all">All categories</option>
          {cats.map((c) => <option key={c} value={c}>{prettify(c)}</option>)}
        </select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-400 text-left">
              <th className="py-2 pr-3 font-normal whitespace-nowrap">Date</th>
              <th className="py-2 pr-3 font-normal">Description</th>
              <th className="py-2 pr-3 font-normal">Category</th>
              <th className="py-2 pr-3 font-normal text-right">Debit</th>
              <th className="py-2 pr-3 font-normal text-right">Credit</th>
              <th className="py-2 font-normal text-right">Balance</th>
            </tr>
          </thead>
          <tbody>
            {slice.map((t, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="py-2 pr-3 text-slate-500 whitespace-nowrap">{t.date}</td>
                <td className="py-2 pr-3 text-slate-800 max-w-[260px] truncate" title={t.description}>{t.description}</td>
                <td className="py-2 pr-3 whitespace-nowrap">
                  <span className="inline-flex items-center gap-1.5 text-xs text-slate-600 capitalize">
                    <span style={{ background: catColor(t.category) }} className="w-2 h-2 rounded-full" />
                    {prettify(t.category || 'other')}
                  </span>
                </td>
                <td className="py-2 pr-3 text-right text-slate-900">{t.debit ? inr(t.debit) : ''}</td>
                <td className="py-2 pr-3 text-right text-green-700">{t.credit ? inr(t.credit) : ''}</td>
                <td className="py-2 text-right text-slate-600">{inr(t.balance)}</td>
              </tr>
            ))}
            {slice.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-slate-400">No transactions match.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm">
        <span className="text-slate-400">Page {current + 1} of {pages}</span>
        <div className="flex gap-2">
          <button onClick={() => setPage(current - 1)} disabled={current === 0}
            className="px-3 py-1.5 rounded-md border border-slate-300 text-slate-700 disabled:opacity-40">Previous</button>
          <button onClick={() => setPage(current + 1)} disabled={current >= pages - 1}
            className="px-3 py-1.5 rounded-md border border-slate-300 text-slate-700 disabled:opacity-40">Next</button>
        </div>
      </div>
    </Card>
  )
}

function StatementPanel({ applicationId, onChanged }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [file, setFile] = useState(null)
  const [inputKey, setInputKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const res = await getLatestStatement(applicationId)
      setData(res.data)
    } catch {
      setError('Could not load saved results.')
    } finally {
      setLoading(false)
    }
  }, [applicationId])

  useEffect(() => { load() }, [load])

  const run = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const up = await uploadStatement(applicationId, file)
      await processStatement(up.data.id)
      setFile(null)
      setInputKey((k) => k + 1)
      await load()
      onChanged()
    } catch {
      setError('Could not process this statement. Check that the backend is running.')
    } finally {
      setBusy(false)
    }
  }

  const transactions = data?.transactions || []
  return (
    <div className="space-y-6">
      <Card
        title="Bank statement"
        subtitle={data?.exists ? 'Saved results are shown below. Upload another PDF to replace them.' : 'Upload a PDF statement to extract and categorize its transactions.'}
      >
        <UploadRow inputKey={inputKey} hasFile={!!file} busy={busy} onPick={setFile} onRun={run}
          idleLabel="Process statement" busyLabel="Processing…" />
        {busy && <p className="text-xs text-slate-500 mt-2">Long statements can take a minute. Please keep this page open.</p>}
        {error && <Notice>{error}</Notice>}
      </Card>

      {loading && <p className="text-sm text-slate-400">Loading saved results…</p>}

      {data?.exists && (
        <>
          <AssessmentCard data={data} />
          <ReconciliationCard rec={data.reconciliation} />
          <Card title="Where the money went" subtitle="Totals by category, from the whole statement.">
            <div className="grid sm:grid-cols-2 gap-8">
              <BarList title="Money out" entries={sumBy(transactions, 'debit')} />
              <BarList title="Money in" entries={sumBy(transactions, 'credit')} />
            </div>
          </Card>
          <TransactionsTable transactions={transactions} />
        </>
      )}
    </div>
  )
}

/* ---------- documents tab ---------- */

function DocumentsPanel({ applicationId, onChanged }) {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [file, setFile] = useState(null)
  const [inputKey, setInputKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const res = await listDocuments(applicationId)
      setDocs(
        res.data
          .filter((d) => d.status === 'extracted')
          .map((d) => ({ ...d, fields: safeParse(d.extracted_fields) }))
          .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')),
      )
    } catch {
      setError('Could not load saved documents.')
    } finally {
      setLoading(false)
    }
  }, [applicationId])

  useEffect(() => { load() }, [load])

  const run = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const up = await uploadDocument(applicationId, file)
      await processDocument(up.data.id)
      setFile(null)
      setInputKey((k) => k + 1)
      await load()
      onChanged()
    } catch {
      setError('Could not process this document.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Loan documents" subtitle="Upload a salary slip, ITR, Form 16 or KYC document. Each is classified and its key fields extracted.">
        <UploadRow inputKey={inputKey} hasFile={!!file} busy={busy} onPick={setFile} onRun={run}
          idleLabel="Upload document" busyLabel="Processing…" />
        {error && <Notice>{error}</Notice>}
      </Card>

      {loading && <p className="text-sm text-slate-400">Loading saved documents…</p>}
      {!loading && docs.length === 0 && <p className="text-sm text-slate-400">No documents processed yet.</p>}

      {docs.map((d) => (
        <Card key={d.id} title={DOC_LABEL[d.doc_type] || 'Document'} subtitle={`${d.filename}  |  ${shortDate(d.created_at)}`}>
          {d.doc_type === 'unknown' || !d.doc_type ? (
            <p className="text-sm text-slate-500">This document type could not be identified, so no fields were extracted.</p>
          ) : (
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {Object.entries(d.fields).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[11px] text-slate-400 capitalize">{prettify(k)}</dt>
                  <dd className="text-sm text-slate-900 break-words">{v ?? '—'}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
      ))}
    </div>
  )
}

/* ---------- verification tab ---------- */

function VerifyPanel({ applicationId, version }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const run = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await verifyApplication(applicationId)
      setResult(res.data)
    } catch {
      setError('Verification could not run.')
    } finally {
      setLoading(false)
    }
  }, [applicationId])

  useEffect(() => { run() }, [run, version])

  const checks = result?.checks || []
  const count = (s) => checks.filter((c) => c.status === s).length

  return (
    <Card
      title="Cross-verification"
      subtitle="Documents and the bank statement are checked against each other for consistency."
      action={<PrimaryButton onClick={run} disabled={loading}>{loading ? 'Checking…' : 'Re-run'}</PrimaryButton>}
    >
      {error && <Notice>{error}</Notice>}
      {result && (
        <>
          <div className="flex flex-wrap gap-2 mb-4">
            <Badge value="pass" label={`${count('pass')} passed`} />
            <Badge value="fail" label={`${count('fail')} failed`} />
            <Badge value="insufficient_data" label={`${count('insufficient_data')} not enough data`} />
          </div>
          {!result.has_bank_statement && (
            <p className="text-sm text-slate-500 mb-3">No bank statement has been processed yet, so the salary check cannot run.</p>
          )}
          <div className="space-y-2">
            {checks.map((c, i) => (
              <div key={i} className="flex items-start gap-3 border border-slate-100 rounded-md p-3">
                <Badge value={c.status} label={prettify(c.status)} />
                <div>
                  <div className="text-sm font-medium text-slate-900">{CHECK_LABEL[c.check] || prettify(c.check)}</div>
                  <div className="text-sm text-slate-600">{cleanReason(c.reason)}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  )
}

/* ---------- review (one application) ---------- */

function ReviewView({ applicationId, applicantName, onBack }) {
  const [tab, setTab] = useState('statement')
  const [version, setVersion] = useState(0)
  const [info, setInfo] = useState(null)

  useEffect(() => {
    getApplication(applicationId).then((r) => setInfo(r.data)).catch(() => {})
  }, [applicationId, version])

  const changed = () => setVersion((v) => v + 1)
  const tabs = [
    { id: 'statement', label: 'Statement' },
    { id: 'documents', label: 'Documents' },
    { id: 'verify', label: 'Verification' },
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-800 mb-4">← Back to queue</button>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-1">
        <h1 className="text-2xl font-semibold text-slate-900">{applicantName || 'Unnamed applicant'}</h1>
        {info?.eligibility_flag && (
          <div className="flex items-center gap-2">
            <Badge value={info.eligibility_flag} />
            <span className="text-sm text-slate-500">Risk {info.risk_score ?? '—'}</span>
          </div>
        )}
      </div>
      <p className="text-xs text-slate-400 mb-6 font-mono">{applicationId}</p>

      <div className="flex gap-1 mb-6 border-b border-slate-200">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === t.id ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className={tab === 'statement' ? '' : 'hidden'}><StatementPanel applicationId={applicationId} onChanged={changed} /></div>
      <div className={tab === 'documents' ? '' : 'hidden'}><DocumentsPanel applicationId={applicationId} onChanged={changed} /></div>
      <div className={tab === 'verify' ? '' : 'hidden'}><VerifyPanel applicationId={applicationId} version={version} /></div>
    </div>
  )
}

/* ---------- dashboard ---------- */

function NewApplicationCard({ onCreated }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await createApplication(name.trim() || null)
      setName('')
      onCreated(res.data.id, res.data.applicant_name)
    } catch {
      setError('Could not create the application. Is the backend running?')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="New application" subtitle="Start a review by naming the applicant.">
      <div className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && create()}
          placeholder="Applicant name"
          className="flex-1 border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
        />
        <PrimaryButton onClick={create} disabled={busy}>Create</PrimaryButton>
      </div>
      {error && <Notice>{error}</Notice>}
    </Card>
  )
}

function StatCard({ label, value, color }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 px-5 py-4">
      <div style={{ color }} className="text-2xl font-semibold">{value}</div>
      <div className="text-xs text-slate-500 mt-1">{label}</div>
    </div>
  )
}

function DashboardView({ onOpen }) {
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')

  const load = useCallback(() => {
    setLoading(true)
    listApplications()
      .then((r) => { setApps(r.data); setError('') })
      .catch(() => setError('Could not load applications. Is the backend running?'))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const remove = async (e, app) => {
    e.stopPropagation()
    if (!window.confirm(`Delete "${app.applicant_name || 'Unnamed'}" and all of its data?`)) return
    try {
      await deleteApplication(app.id)
      load()
    } catch {
      setError('Delete failed.')
    }
  }

  const countOf = (f) => apps.filter((a) => a.eligibility_flag === f).length
  const unscored = apps.filter((a) => !a.eligibility_flag).length
  const filters = [
    ['all', 'All'], ['approve', 'Approve'], ['manual_review', 'Needs review'], ['reject', 'Reject'], ['unscored', 'Not scored'],
  ]
  const visible = apps.filter((a) => {
    const matchesFilter =
      filter === 'all' || (filter === 'unscored' ? !a.eligibility_flag : a.eligibility_flag === filter)
    return matchesFilter && (a.applicant_name || 'unnamed').toLowerCase().includes(q.trim().toLowerCase())
  })

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Applications" value={apps.length} color="#0F172A" />
        <StatCard label="Approve" value={countOf('approve')} color="#15803D" />
        <StatCard label="Needs review" value={countOf('manual_review')} color="#B45309" />
        <StatCard label="Not scored yet" value={unscored} color="#64748B" />
      </div>

      <NewApplicationCard onCreated={(id, name) => { load(); onOpen(id, name) }} />

      <Card title="Applications queue" subtitle="Select an applicant to review their documents.">
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name"
            className="border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
          />
          <div className="flex flex-wrap gap-1">
            {filters.map(([id, label]) => (
              <button
                key={id}
                onClick={() => setFilter(id)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium border ${
                  filter === id ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {error && <Notice>{error}</Notice>}
        {loading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : visible.length === 0 ? (
          <p className="text-sm text-slate-400">
            {apps.length === 0 ? 'No applications yet. Create one above to get started.' : 'No applications match your filters.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="text-slate-400 text-xs">
                  <th className="py-2 pr-4 font-normal">Applicant</th>
                  <th className="py-2 pr-4 font-normal">Decision</th>
                  <th className="py-2 pr-4 font-normal">Risk score</th>
                  <th className="py-2 pr-4 font-normal">Created</th>
                  <th className="py-2 font-normal"></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((app) => (
                  <tr
                    key={app.id}
                    onClick={() => onOpen(app.id, app.applicant_name)}
                    className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="py-3 pr-4 text-slate-900">
                      {app.applicant_name || <span className="text-slate-400">Unnamed</span>}
                    </td>
                    <td className="py-3 pr-4">
                      {app.eligibility_flag ? <Badge value={app.eligibility_flag} /> : <Badge value="intake" label="Not scored" />}
                    </td>
                    <td className="py-3 pr-4 text-slate-600">{app.risk_score ?? '—'}</td>
                    <td className="py-3 pr-4 text-slate-500 whitespace-nowrap">{shortDate(app.created_at)}</td>
                    <td className="py-3 text-right">
                      <button onClick={(e) => remove(e, app)} className="text-xs text-slate-400 hover:text-red-600">Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

/* ---------- app shell ---------- */

export default function App() {
  const [openApp, setOpenApp] = useState(null)

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-slate-900">Loan Automation Platform</h1>
          <span className="text-xs text-slate-400">AI-assisted statement and document review</span>
        </div>
      </header>
      <main className="px-4 py-8">
        {openApp ? (
          <ReviewView applicationId={openApp.id} applicantName={openApp.name} onBack={() => setOpenApp(null)} />
        ) : (
          <DashboardView onOpen={(id, name) => setOpenApp({ id, name })} />
        )}
      </main>
    </div>
  )
}