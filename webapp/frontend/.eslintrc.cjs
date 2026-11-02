module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: ['eslint:recommended', 'plugin:react-hooks/recommended', 'prettier'],
  ignorePatterns: ['dist', 'node_modules', 'vite.config.js', 'vitest.config.js'],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: ['react', 'react-refresh'],
  rules: {
    'react/jsx-uses-vars': 'error',
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
  },
  overrides: [
    {
      files: ['src/context/**/*.jsx'],
      // Context 文件同时导出 Provider 和 useXxx，Fast Refresh 规则不适用
      rules: { 'react-refresh/only-export-components': 'off' },
    },
    {
      files: ['src/**/__tests__/**/*.js', 'src/setupTests.js'],
      globals: {
        describe: 'readonly',
        it: 'readonly',
        expect: 'readonly',
        vi: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
      },
    },
  ],
}