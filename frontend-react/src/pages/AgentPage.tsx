import { useEffect, useMemo, useState } from 'react'
import { Bot, Play, Send, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import { Button, Card, EmptyState, PageHeader, ResultBanner, StatusPill } from '../components/ui'

interface AgentMessage {
  id: string
  role: string
  content: string
  meta: Record<string, unknown>
  created_at?: string | null
}

interface AgentAction {
  name: string
  description: string
  permission: string
  requires_confirmation: boolean
}

interface AgentAudit {
  id: string
  action_name: string
  permission: string
  requires_confirmation: boolean
  status: string
  input?: Record<string, unknown>
  result?: Record<string, unknown>
  error?: string | null
  created_at?: string | null
  confirmed_at?: string | null
}

function actionTone(permission: string): 'success' | 'warning' | 'neutral' {
  if (permission === 'read') return 'success'
  if (permission === 'high_risk') return 'warning'
  return 'neutral'
}

function parseJsonObject(text: string): Record<string, unknown> {
  if (!text.trim()) return {}
  const parsed = JSON.parse(text) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Action args must be a JSON object')
  }
  return parsed as Record<string, unknown>
}

function hasResult(meta: Record<string, unknown>): boolean {
  return Object.prototype.hasOwnProperty.call(meta, 'result')
}

export default function AgentPage() {
  const [sessionId, setSessionId] = useState<string>()
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [actions, setActions] = useState<AgentAction[]>([])
  const [audits, setAudits] = useState<AgentAudit[]>([])
  const [command, setCommand] = useState('')
  const [selectedAction, setSelectedAction] = useState('')
  const [actionArgs, setActionArgs] = useState('{}')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getAgentActions().then(r => {
      setActions(r.actions)
      if (r.actions[0]) setSelectedAction(r.actions[0].name)
    }).catch(e => setError(e instanceof Error ? e.message : 'Failed to load agent actions'))
  }, [])

  const selected = useMemo(
    () => actions.find(action => action.name === selectedAction),
    [actions, selectedAction],
  )

  function mergeAudit(action: Record<string, unknown> | null) {
    if (!action || typeof action.id !== 'string') return
    const audit = action as unknown as AgentAudit
    setAudits(prev => [audit, ...prev.filter(item => item.id !== audit.id)].slice(0, 25))
  }

  async function submitCommand(e: React.FormEvent) {
    e.preventDefault()
    const text = command.trim()
    if (!text) return
    setLoading(true)
    setError('')
    try {
      const res = await api.sendAgentCommand({ message: text, session_id: sessionId })
      setSessionId(res.session_id)
      setMessages(prev => [...prev, { id: `local-${Date.now()}`, role: 'user', content: text, meta: {} }, res.message])
      mergeAudit(res.action)
      setCommand('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Agent command failed')
    } finally {
      setLoading(false)
    }
  }

  async function runAction(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedAction) return
    setLoading(true)
    setError('')
    try {
      const res = await api.executeAgentAction({
        session_id: sessionId,
        action_name: selectedAction,
        action_args: parseJsonObject(actionArgs),
      })
      setSessionId(res.session_id)
      setMessages(prev => [...prev, res.message])
      mergeAudit(res.action)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Agent action failed')
    } finally {
      setLoading(false)
    }
  }

  async function confirmAudit(id: string) {
    setLoading(true)
    setError('')
    try {
      const res = await api.confirmAgentAction(id)
      setMessages(prev => [...prev, res.message])
      mergeAudit(res.action)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Confirm failed')
    } finally {
      setLoading(false)
    }
  }

  async function cancelAudit(id: string) {
    setLoading(true)
    setError('')
    try {
      const res = await api.cancelAgentAction(id)
      mergeAudit(res.action)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Cancel failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader
        title="Operational Agent"
        description="Run BackVora actions through an audited, whitelisted agent surface"
        actions={<StatusPill tone="success"><ShieldCheck className="w-3 h-3" /> Audited actions only</StatusPill>}
      />

      {error && <ResultBanner tone="error" onDismiss={() => setError('')}>{error}</ResultBanner>}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-5">
        <Card className="min-h-[560px] flex flex-col">
          <div className="flex-1 p-4 space-y-3 overflow-y-auto">
            {messages.length === 0 ? (
              <EmptyState
                icon={Bot}
                title="No agent messages yet"
                hint="Try: search domains porn, show domain example.com, classify domain example.com, summarize campaign CamHours."
              />
            ) : messages.map(message => (
              <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[82%] rounded-lg px-3 py-2 text-sm ${
                  message.role === 'user'
                    ? 'bg-pink-600 text-white'
                    : 'bg-gray-900 border border-gray-700 text-gray-200'
                }`}>
                  <div className="whitespace-pre-wrap break-words">{message.content}</div>
                  {hasResult(message.meta) && (
                    <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-black/30 p-2 text-xs text-gray-300">
                      {JSON.stringify(message.meta.result, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>

          <form onSubmit={submitCommand} className="border-t border-gray-700 p-3 flex gap-2">
            <input
              value={command}
              onChange={e => setCommand(e.target.value)}
              placeholder="Tell the agent what to do..."
              className="flex-1 min-w-0 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-500"
            />
            <Button type="submit" variant="primary" disabled={loading || !command.trim()} icon={Send}>
              Send
            </Button>
          </form>
        </Card>

        <div className="space-y-5">
          <Card className="p-4">
            <h2 className="text-sm font-semibold mb-3">Run Explicit Action</h2>
            <form onSubmit={runAction} className="space-y-3">
              <select
                value={selectedAction}
                onChange={e => setSelectedAction(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-pink-500"
              >
                {actions.map(action => <option key={action.name} value={action.name}>{action.name}</option>)}
              </select>
              {selected && (
                <div className="text-xs text-gray-400 space-y-2">
                  <p>{selected.description}</p>
                  <StatusPill tone={actionTone(selected.permission)}>{selected.permission}</StatusPill>
                </div>
              )}
              <textarea
                value={actionArgs}
                onChange={e => setActionArgs(e.target.value)}
                rows={8}
                spellCheck={false}
                className="w-full font-mono bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-pink-500"
              />
              <Button type="submit" variant="primary" disabled={loading || !selectedAction} icon={Play}>
                Run
              </Button>
            </form>
          </Card>

          <Card className="p-4">
            <h2 className="text-sm font-semibold mb-3">Recent Audit</h2>
            {audits.length === 0 ? (
              <div className="text-xs text-gray-500">No action attempts in this session.</div>
            ) : (
              <div className="space-y-2">
                {audits.map(audit => (
                  <div key={audit.id} className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-mono text-gray-200">{audit.action_name}</span>
                      <StatusPill tone={audit.status === 'failed' || audit.status === 'rejected' ? 'danger' : audit.status === 'pending' ? 'warning' : 'success'}>
                        {audit.status}
                      </StatusPill>
                    </div>
                    {audit.error && <div className="mt-1 text-xs text-red-300">{audit.error}</div>}
                    {audit.status === 'pending' && (
                      <div className="mt-2 flex gap-2">
                        <Button size="sm" variant="primary" disabled={loading} onClick={() => confirmAudit(audit.id)}>Confirm</Button>
                        <Button size="sm" disabled={loading} onClick={() => cancelAudit(audit.id)}>Cancel</Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card className="p-4">
            <h2 className="text-sm font-semibold mb-3">Available Actions</h2>
            <div className="space-y-2">
              {actions.map(action => (
                <button
                  key={action.name}
                  type="button"
                  onClick={() => setSelectedAction(action.name)}
                  className="w-full text-left rounded-md border border-gray-700 bg-gray-900 px-3 py-2 hover:border-gray-600"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-mono text-gray-200">{action.name}</span>
                    <StatusPill tone={actionTone(action.permission)}>{action.permission}</StatusPill>
                  </div>
                  <div className="mt-1 text-xs text-gray-500">{action.description}</div>
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
