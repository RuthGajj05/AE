import { useEffect, useRef, useState } from 'react'

/** Lets a JSON file be dropped anywhere on the page. Returns true while a file is dragged over it. */
export function useFileDrop(onFile) {
  const [dragging, setDragging] = useState(false)
  const depth = useRef(0)
  const latest = useRef(onFile)

  useEffect(() => {
    latest.current = onFile
  })

  useEffect(() => {
    const hasFiles = (e) => [...(e.dataTransfer?.types ?? [])].includes('Files')
    const enter = (e) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth.current += 1
      setDragging(true)
    }
    const over = (e) => {
      if (hasFiles(e)) e.preventDefault()
    }
    const leave = (e) => {
      if (!hasFiles(e)) return
      depth.current = Math.max(0, depth.current - 1)
      if (depth.current === 0) setDragging(false)
    }
    const drop = (e) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth.current = 0
      setDragging(false)
      latest.current(e.dataTransfer.files[0])
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [])

  return dragging
}
