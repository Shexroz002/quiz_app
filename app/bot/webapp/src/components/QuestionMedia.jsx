import { Maximize2 } from 'lucide-react';
import RichText from './RichText';
import { mediaUrl } from '../api/quiz';

export default function QuestionMedia({ images, table }) {
  const sources = (images || [])
    .map((image, index) => ({ key: image.id ?? index, url: mediaUrl(image.image_url || '') }))
    .filter((image) => image.url);

  return <>
    {sources.map((image, index) => <figure className="media-figure" key={image.key}>
      <a className="media-link" href={image.url} target="_blank" rel="noopener noreferrer">
        <img
          className="media-image"
          src={image.url}
          alt={`Savol rasmi ${index + 1}`}
          loading="lazy"
          onError={(event) => { event.currentTarget.closest('.media-figure')?.classList.add('media-broken'); }}
        />
        <span className="media-zoom" aria-hidden="true"><Maximize2 size={15} /></span>
      </a>
      <figcaption className="media-fallback">Rasmni yuklab bo‘lmadi</figcaption>
    </figure>)}
    {table && <RichText text={table} />}
  </>;
}
