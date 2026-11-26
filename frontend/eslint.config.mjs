import js from '@eslint/js'
import globals from 'globals'

// Mark JSX tags as references with the automatic React transform.
const jsxUsed = { rules: { references: { create(context) {
  return { JSXOpeningElement(node) {
    let name = node.name
    while (name.type === 'JSXMemberExpression') name = name.object
    if (name.type === 'JSXIdentifier') context.sourceCode.markVariableAsUsed(name.name, node)
  } }
} } } }
export default [{ ignores: ['dist/**', 'node_modules/**'] }, {
  files: ['src/pages/PlatformPage.jsx','src/components/SaaSEntry.jsx','src/components/SaaSWorkspace.jsx','src/pages/BuilderPage.jsx','src/model-store.js','src/sitebuilder/preview.js','src/components/CommandCenter.jsx','src/components/ModelWorkbench.jsx','src/components/AccountSecurity.jsx','src/components/AccessPolicy.jsx','src/components/InstanceConfiguration.jsx','src/components/UsersDirectory.jsx','src/components/RolesManager.jsx','src/components/AgentTools.jsx','src/components/HealthChecks.jsx','src/pages/SettingsPage.jsx', 'src/pages/admin-models.js', 'src/components/admin-ui.jsx', 'src/components/Sidebar.jsx', 'src/components/TopBar.jsx', 'src/components/AuthGate.jsx', 'src/App.jsx', 'src/main.jsx'],
  languageOptions: { ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } }, globals: globals.browser },
  plugins: { jsxUsed },
  rules: { ...js.configs.recommended.rules, 'jsxUsed/references': 'error', 'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrors: 'none' }] },
}]
