import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { I18nProvider } from './i18n/i18nContext'
import { ToastContainer } from './components/ui/Toast'
import App from './App.tsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <App />
        <ToastContainer />
      </I18nProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
