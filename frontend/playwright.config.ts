import { defineConfig } from '@playwright/test';
export default defineConfig({
  expect:{timeout:30000},
  testDir:'./tests',workers:1,fullyParallel:false,
  reporter:[['list'],['html',{open:'never'}]],
  use:{baseURL:process.env.ERP_E2E_BASE_URL||'http://127.0.0.1:5173',browserName:'chromium',channel:'msedge',headless:true,viewport:{width:1440,height:1000},actionTimeout:60000,navigationTimeout:60000,trace:'retain-on-failure'},
});
