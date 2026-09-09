import RichText from './RichText';
import { mediaUrl } from '../api/quiz';

export default function QuestionMedia({ images, table }) {
  return <>
    {(images || []).filter(image => image.image_url && mediaUrl(image.image_url)).map((image, index) =>
      <figure key={image.id ?? index}>
        <a href={mediaUrl(image.image_url)} target="_blank" rel="noopener noreferrer">
          <img src={mediaUrl(image.image_url)} alt={`Savol rasmi ${index + 1}`} onError={event => { event.currentTarget.alt = 'Rasm yuklanmadi'; }} />
        </a>
      </figure>)}
    {table && <div className="table-scroll"><RichText text={table} /></div>}
  </>;
}
