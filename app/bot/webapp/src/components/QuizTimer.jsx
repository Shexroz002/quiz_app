import { useEffect, useState } from 'react';
import { Clock3 } from 'lucide-react';

export default function QuizTimer({ deadline, onExpire }) {
  const [remaining, setRemaining] = useState(() => Math.max(0, Math.ceil((deadline - Date.now()) / 1000)));
  useEffect(() => {
    const tick = () => {
      const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setRemaining(seconds);
      if (!seconds) onExpire();
    };
    tick();
    const interval = setInterval(tick, 500);
    return () => clearInterval(interval);
  }, [deadline, onExpire]);
  return <span className={`timer ${remaining < 60 ? 'urgent' : ''}`} role="timer" aria-label="Qolgan vaqt">
    <Clock3 size={18} />{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}
  </span>;
}
