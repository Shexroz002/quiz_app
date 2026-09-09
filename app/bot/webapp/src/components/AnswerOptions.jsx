import RichText from './RichText';

export default function AnswerOptions({ options, selected, onSelect, disabled }) {
  return <fieldset disabled={disabled} className="answers"><legend className="visually-hidden">Javobni tanlang</legend>
    {options.map(option => <label className={`answer ${selected === option.label ? 'selected' : ''}`} key={option.label}>
      <input type="radio" name="answer" value={option.label} checked={selected === option.label} onChange={() => onSelect(option.label)} />
      <span className="option-label">{option.label}</span><RichText text={option.text} />
    </label>)}
  </fieldset>;
}
