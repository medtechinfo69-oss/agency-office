// Explainable heuristic, not a benchmark. Unknown model sizes are never claimed to fit RAM.
export function recommendModel(models, task = 'reasoning', ramGB = null) {
  const available = models.filter((m) => !ramGB || !m.size || m.size / 1e9 * 1.4 <= Number(ramGB))
  const scores = available.map((model) => {
    const id = model.id.toLowerCase()
    let score = model.free ? 4 : 0
    if (task === 'code' && /coder|codestral|code|devstral/.test(id)) score += 20
    if (task === 'reasoning' && /reason|deepseek|qwq|r1|thinking/.test(id)) score += 20
    if (task === 'design' && /vision|vl|gemini|gpt-4|llama-4/.test(id)) score += 20
    if (task === 'speed' && /mini|flash|small|8b|3b|1b|nano/.test(id)) score += 20
    if (task !== 'speed' && /32b|70b|large|pro/.test(id)) score += 5
    return { model, score }
  })
  scores.sort((a, b) => b.score - a.score || a.model.id.localeCompare(b.model.id))
  return scores[0]?.model || null
}
