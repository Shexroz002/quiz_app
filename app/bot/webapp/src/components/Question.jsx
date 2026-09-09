import QuestionMedia from './QuestionMedia';
import RichText from './RichText';

export default function Question({ question }) {
  return <section className="question" aria-label="Savol">
    <RichText text={question.question_text} />
    <QuestionMedia images={question.images} table={question.table_markdown} />
  </section>;
}
