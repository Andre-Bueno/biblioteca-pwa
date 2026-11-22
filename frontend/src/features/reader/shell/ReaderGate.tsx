import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { usePreferences } from '../../../shared/preferences';
import '../../../shared/ui';
import type { ReaderData, ReaderReady } from '../hooks/useReaderData';
import './shell.css';

function Message({ children }: { children: ReactNode }) {
  return (
    <main className="reader-message" data-testid="reader-message">
      {children}
      <Link className="btn" to="/">
        Voltar para a biblioteca
      </Link>
    </main>
  );
}

interface ReaderGateProps {
  data: ReaderData;
  retry: () => void;
  /** Renders the reader once the data is in and there is something to read. */
  children: (ready: ReaderReady) => ReactNode;
}

/** The states every reader shares before it mounts: loading, not found, error, empty, unsupported. */
export function ReaderGate({ data, retry, children }: ReaderGateProps) {
  const { loaded } = usePreferences(); // the reading mode and the book theme come from the preferences

  if (data.status === 'loading' || !loaded) {
    return (
      <div className="splash" role="status" aria-label="Carregando" data-testid="reader-loading">
        <div className="spinner" />
      </div>
    );
  }
  if (data.status === 'notfound') {
    return <Message>{data.subject === 'book' ? 'Livro' : 'Item'} não encontrado.</Message>;
  }
  if (data.status === 'error') {
    return (
      <Message>
        Não foi possível abrir este {data.subject === 'book' ? 'livro' : 'item'}.
        <button type="button" className="btn" onClick={retry}>
          Tentar novamente
        </button>
      </Message>
    );
  }
  if (data.status !== 'ready') return <Message>Este formato ainda não é suportado.</Message>;
  if (data.source.unitCount === 0) {
    return (
      <Message>
        {data.source.kind === 'chapters'
          ? 'Este livro não tem capítulos para ler.'
          : 'Este item não tem páginas para ler.'}
      </Message>
    );
  }
  return <>{children(data)}</>;
}
