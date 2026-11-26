// Preview only fully received JSON string values. Never eval model output.
export function completedFiles(text) {
  const files = {}
  for (const match of text.matchAll(/"(index\.html|styles\.css|script\.js)"\s*:\s*("(?:\\.|[^"\\])*")/g)) {
    try { const value = JSON.parse(match[2]); if (value.length <= 250000) files[match[1]] = value } catch { /* Partial JSON strings are expected while streaming. */ }
  }
  return files
}
