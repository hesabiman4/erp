import {registerOfflineShell} from './offline-store';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import './i18n';
import './style.css';
import './design.css';
import './accounting.css';
import './hr-finance.css';
import './growth.css';
import './refinements.css';
import './document-print.css';
import App from './App';
const client = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15_000, refetchOnWindowFocus: false } } });
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><BrowserRouter><App/></BrowserRouter></QueryClientProvider></React.StrictMode>);

registerOfflineShell().catch(()=>{/* The notebook reports unavailable offline support when explicitly enabled. */});

import './document-page.css';

import './settings-experience.css';
import './premium-experience.css';
import './nawa-redesign.css';
