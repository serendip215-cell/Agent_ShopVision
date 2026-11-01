import { useEffect, useState } from 'react'

// 数字从 0 缓动计数到目标值：识别结果置信度、首页指标栏共用。
// target 为 null/undefined 时归零（结果卡切换/清空时用）。
export default function useCountUp(target, { delay = 260, duration = 950 } = {}) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (target == null) {
      setValue(0)
      return
    }
    let raf
    const start = performance.now() + delay
    const tick = (now) => {
      const t = Math.min(1, Math.max(0, (now - start) / duration))
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(target * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, delay, duration])
  return value
}
