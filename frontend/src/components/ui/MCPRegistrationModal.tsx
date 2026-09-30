import React, { useState } from 'react'
import { Modal, Input, Button } from '.'
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
  const [url, setUrl] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !url.trim()) return

    setIsSubmitting(true)
    try {
      await registerMCPServer({ name, url })
      addToast({ type: 'success', message: 'MCP server registered successfully' })
      setName('')
      setUrl('')
      onClose()
    } catch (err: any) {
      addToast({ type: 'error', message: err.message || 'Failed to register MCP server' })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Register MCP Server">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-slate-600">
          Connect a Model Context Protocol (MCP) server to give Relay access to custom tools and resources.
          The server must expose an HTTP/SSE transport endpoint.
        </p>
        
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Server Name</label>
          <Input 
            value={name} 
            onChange={(e) => setName(e.target.value)} 
            placeholder="e.g. Filesystem Tools"
            required
            autoFocus
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Server URL</label>
          <Input 
            value={url} 
            onChange={(e) => setUrl(e.target.value)} 
            placeholder="http://localhost:8080"
            required
            type="url"
          />
        </div>
        
        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" isLoading={isSubmitting}>Register Server</Button>
        </div>
      </form>
    </Modal>
  )
}
