import React, { useState } from 'react'
import { Modal, Input, Button, Badge } from '.'
import { useConnectionStore } from '../../stores/connectionStore'
import { useUIStore } from '../../stores/uiStore'

interface Props {
  isOpen: boolean
  onClose: () => void
}

export const MCPRegistrationModal: React.FC<Props> = ({ isOpen, onClose }) => {
  const { registerMCPServer } = useConnectionStore()
  const { addToast } = useUIStore()
  
  const [name, setName] = useState('')
  const [transport, setTransport] = useState<'streamable_http' | 'stdio'>('streamable_http')
  const [url, setUrl] = useState('')
  const [command, setCommand] = useState('')
  const [argsStr, setArgsStr] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return

    if (transport === 'streamable_http' && !url.trim()) return
    if (transport === 'stdio' && !command.trim()) return

    setIsSubmitting(true)
    try {
      const payload: any = {
        name: name.trim(),
        transport,
      }

      if (transport === 'streamable_http') {
        payload.url = url.trim()
      } else {
        payload.command = command.trim()
        payload.args = argsStr.trim() ? argsStr.trim().split(/\s+/) : []
      }

      await registerMCPServer(payload)
      addToast({
        type: 'success',
        title: 'MCP Server Registered',
        message: `Connected to ${name.trim()} and discovered tools.`,
      })
      setName('')
      setUrl('')
      setCommand('')
      setArgsStr('')
      onClose()
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Registration Failed',
        message: err.message || 'Failed to register and verify MCP server.',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Register MCP Server">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-slate-600">
          Connect a Model Context Protocol (MCP) server to dynamically discover tools, resources, and domain capabilities.
        </p>

        {/* Transport Type Selector */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Transport</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setTransport('streamable_http')}
              className={`p-3 text-left border rounded-lg transition-all ${
                transport === 'streamable_http'
                  ? 'border-indigo-600 bg-indigo-50/50 text-indigo-950 font-medium'
                  : 'border-slate-200 hover:border-slate-300 text-slate-700'
              }`}
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="text-sm">Streamable HTTP / SSE</span>
                <Badge label="HTTP" color="indigo" size="sm" />
              </div>
              <p className="text-xs text-slate-500">FastAPI, Express, or remote endpoints</p>
            </button>

            <button
              type="button"
              onClick={() => setTransport('stdio')}
              className={`p-3 text-left border rounded-lg transition-all ${
                transport === 'stdio'
                  ? 'border-indigo-600 bg-indigo-50/50 text-indigo-950 font-medium'
                  : 'border-slate-200 hover:border-slate-300 text-slate-700'
              }`}
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="text-sm">Local Process (stdio)</span>
                <Badge label="CLI" color="slate" size="sm" />
              </div>
              <p className="text-xs text-slate-500">Python scripts, Node, or CLI tools</p>
            </button>
          </div>
        </div>

        {/* Server Name */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Server Name</label>
          <Input 
            value={name} 
            onChange={(e) => setName(e.target.value)} 
            placeholder="e.g. Note Taking Server"
            required
            autoFocus
          />
        </div>

        {/* HTTP / SSE endpoint */}
        {transport === 'streamable_http' && (
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Server URL</label>
            <Input 
              value={url} 
              onChange={(e) => setUrl(e.target.value)} 
              placeholder="http://localhost:8000/mcp"
              required
              type="url"
            />
            <p className="text-xs text-slate-400 mt-1">Supports Streamable-HTTP and SSE JSON-RPC endpoints.</p>
          </div>
        )}

        {/* stdio options */}
        {transport === 'stdio' && (
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Executable Command</label>
              <Input 
                value={command} 
                onChange={(e) => setCommand(e.target.value)} 
                placeholder="python or node or npx"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Arguments (space separated)</label>
              <Input 
                value={argsStr} 
                onChange={(e) => setArgsStr(e.target.value)} 
                placeholder="server.py --port 8000"
              />
              <p className="text-xs text-slate-400 mt-1">Direct arguments passed safely to the subprocess.</p>
            </div>
          </div>
        )}
        
        <div className="flex justify-end gap-3 pt-3 border-t border-slate-100">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" isLoading={isSubmitting}>Register & Discover Tools</Button>
        </div>
      </form>
    </Modal>
  )
}
