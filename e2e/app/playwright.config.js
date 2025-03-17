import baseConfig from '../playwright.config';
import { deepMerge } from '../lib/util';
import { defineConfig } from '@playwright/test';

export default defineConfig(deepMerge(
  baseConfig,
  {
    use: {
      baseURL: baseConfig.use.baseURL || "localhost:8000",
      // emailServiceType: "Mailinator", // Options: ["MessageChecker", "Mailinator"]. Default: "MessageChecker"
    },
  }
));
