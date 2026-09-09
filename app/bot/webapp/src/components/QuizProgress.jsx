import { BookOpen, Flag, Grid3X3 } from 'lucide-react';

export default function QuizProgress({ current, total, answered, timer, onToggleNavigator, onFinish }) {
  const percent = total ? Math.round((answered / total) * 100) : 0;

  return <section className="status-panel" aria-label="Test holati">
    <span className="status-icon" aria-hidden="true"><BookOpen size={20} /></span>
    <div className="progress-copy">
      <div className="progress-heading">
        <strong>Savol {current}/{total}</strong>
        <span className="answer-count">{answered}</span>
      </div>
      <div className="progress-line">
        <progress value={answered} max={total || 1} aria-label="Javob berilgan savollar" />
        <span>{percent}%</span>
      </div>
    </div>
    {timer}
    <button className="icon-button" type="button" onClick={onToggleNavigator} title="Savollar ro‘yxati" aria-label="Savollar ro‘yxati">
      <Grid3X3 size={19} />
    </button>
    <button className="icon-button icon-button-primary" type="button" onClick={onFinish} title="Testni yakunlash" aria-label="Testni yakunlash">
      <Flag size={18} />
    </button>
  </section>;
}
