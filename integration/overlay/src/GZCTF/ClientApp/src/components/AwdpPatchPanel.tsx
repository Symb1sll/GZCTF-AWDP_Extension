import { Alert, Button, FileInput, Stack, Text } from '@mantine/core'
import { useEffect, useState } from 'react'

type Patch = { id: string; createdAt: string; status: string; message: string }
type State = { enabled: boolean; fixScore?: number; submissions?: Patch[] }

export function AwdpPatchPanel({ gameId, challengeId }: { gameId: number; challengeId: number }) {
  const [state, setState] = useState<State>({ enabled: false })
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const url = `/api/Game/${gameId}/Challenges/${challengeId}/Patches`
  useEffect(() => {
    let closed = false
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    setState({ enabled: false })
    setFile(null)
    setError('')
    async function poll() {
      try {
        const response = await fetch(url, { credentials: 'same-origin', signal: controller.signal })
        if (!response.ok) throw new Error(`判题记录读取失败：HTTP ${response.status}`)
        const data: State = await response.json()
        if (!closed) { setState(data); setError('') }
      } catch (e) {
        if (!closed) setError(e instanceof Error ? e.message : '读取失败')
      } finally { if (!closed) timer = setTimeout(poll, 3000) }
    }
    void poll()
    return () => { closed = true; controller.abort(); clearTimeout(timer) }
  }, [url])
  if (!state.enabled) return null
  async function submit() {
    if (!file || busy) return
    if (file.size === 0 || file.size > 512 * 1024) { setError('补丁必须为1字节至512 KiB'); return }
    setBusy(true)
    setError('')
    try {
      const response = await fetch(url, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'text/x-diff', 'X-AWDP-Request': 'patch' }, body: file,
      })
      if (!response.ok) throw new Error(`提交失败：HTTP ${response.status}`)
      setFile(null)
    } catch (e) { setError(e instanceof Error ? e.message : '提交失败') }
    finally { setBusy(false) }
  }
  return <Stack p="md" gap="xs">
    <Text fw={700}>AWDP 补丁判题</Text>
    <Alert color="blue">修复通过获得 {state.fixScore ?? 100} 分，同题重复通过不重复加分。截止前提交的任务可在截止后完成判题。</Alert>
    <FileInput label="UTF-8 unified diff（最大512 KiB）" accept=".patch,.diff" value={file} onChange={setFile} />
    <Button loading={busy} disabled={!file} onClick={submit}>提交补丁</Button>
    {error && <Alert color="red">{error}</Alert>}
    {state.submissions?.map(x => <div key={x.id}>
      <Text size="sm">{x.status} · {x.createdAt}</Text>
      <Text size="xs">{x.id} — {x.message}</Text>
    </div>)}
  </Stack>
}
