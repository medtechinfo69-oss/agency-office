import { useEffect, useRef } from 'react'

// Keeps keyboard users inside the active dialog and returns focus on dismissal.
// Passing null disables the behavior (useful for conditionally visible dialogs).
export default function useDialog(onClose) {
  const ref = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  const active = Boolean(onClose)

  useEffect(() => {
    const node = ref.current
    if (!active || !node) return
    const previous = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const background = []
    let branch = node
    while (branch.parentElement && branch !== document.body) {
      for (const sibling of branch.parentElement.children) {
        if (sibling !== branch && sibling instanceof HTMLElement) {
          background.push([sibling, sibling.inert])
          sibling.inert = true
        }
      }
      branch = branch.parentElement
    }
    const focusable = () => [...node.querySelectorAll(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
    )].filter((el) => el.getClientRects().length && !el.closest('[inert]'))
    ;(node.querySelector('[data-dialog-focus]') || focusable()[0] || node).focus()
    const handleKey = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        closeRef.current?.()
      }
      if (event.key === 'Tab') {
        const items = focusable()
        const first = items[0], last = items.at(-1)
        if (!first) { event.preventDefault(); node.focus(); return }
        if (event.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
          event.preventDefault(); last.focus()
        } else if (!event.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) {
          event.preventDefault(); first.focus()
        }
      }
    }
    document.addEventListener('keydown', handleKey, true)
    return () => {
      document.body.style.overflow = overflow
      background.forEach(([element, inert]) => { element.inert = inert })
      document.removeEventListener('keydown', handleKey, true)
      if (previous?.isConnected) previous.focus()
    }
  }, [active])
  return ref
}
