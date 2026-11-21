import { Link } from 'react-router-dom';
import { usePreferences, type ReadingDirection } from '../../../shared/preferences';
import { useSession } from '../../../shared/session';
import { SegmentedControl, ThemeToggle, type SegmentedOption } from '../../../shared/ui';
import { UpdateNotice, useVersion } from '../../../shared/system';
import { useCheckUpdates, type CheckResult } from '../hooks/useCheckUpdates';
import { ChangePasswordForm } from './ChangePasswordForm';
import '../settings.css';

const DIRECTION_OPTIONS: SegmentedOption<ReadingDirection>[] = [
  { value: 'rtl', label: 'D→E' },
  { value: 'ltr', label: 'E→D' },
  { value: 'vertical', label: 'Vertical' },
];

const CHECK_TEXT: Record<CheckResult['kind'], string> = {
  none: '',
  latest: 'Você está na versão mais recente.',
  available: 'Nova versão disponível:',
  'rate-limited': 'Muitas verificações seguidas. Aguarde um pouco e tente de novo.',
  error: 'Não foi possível verificar agora.',
};

export function SettingsPage() {
  const { user, logout } = useSession();
  const { preferences, update, saveFailed, loadFailed, reload } = usePreferences();
  const version = useVersion();
  const check = useCheckUpdates();

  return (
    <main className="settings" data-testid="settings-page">
      <header className="settings__header">
        <Link className="btn" to="/" data-testid="settings-back">
          ‹ Biblioteca
        </Link>
        <h1 className="settings__title">Ajustes</h1>
      </header>

      <section className="settings__section" aria-labelledby="appearance-title">
        <h2 id="appearance-title">Aparência</h2>
        <ThemeToggle onSelect={(theme) => void update({ theme })} />
      </section>

      <section className="settings__section" aria-labelledby="reading-title">
        <h2 id="reading-title">Leitura</h2>
        <SegmentedControl
          label="Sentido de leitura"
          options={DIRECTION_OPTIONS}
          value={preferences.reading_direction}
          onChange={(reading_direction) => void update({ reading_direction })}
          testId="reading-direction"
        />
        <p className="muted">
          D→E: mangá, da direita para a esquerda. E→D: da esquerda para a direita. Vertical: rolagem
          contínua (webtoon). Você pode trocar o modo dentro do leitor.
        </p>
      </section>

      {loadFailed && (
        <div className="alert alert--error" role="alert" data-testid="preferences-load-error">
          <p>
            Não foi possível carregar suas preferências do servidor. O que você escolher agora será
            salvo quando a conexão voltar.
          </p>
          <button type="button" className="btn btn--small" onClick={reload}>
            Tentar de novo
          </button>
        </div>
      )}

      {saveFailed && (
        <p className="alert alert--error" role="alert" data-testid="preferences-error">
          Não foi possível salvar as preferências no servidor. A escolha vale só nesta sessão.
        </p>
      )}

      <UpdateNotice />

      <section className="settings__section" aria-labelledby="about-title">
        <h2 id="about-title">Sobre o app</h2>
        {version.info?.current && (
          <p className="muted" data-testid="app-version">
            Versão do app: {version.info.current}
          </p>
        )}
        {user?.role === 'admin' && (
          <>
            <button
              type="button"
              className="btn"
              disabled={check.busy || check.blocked}
              data-testid="check-updates"
              onClick={() => void check.run()}
            >
              {check.busy ? 'Verificando…' : 'Verificar atualizações'}
            </button>
            <p className="muted" role="status" data-testid="check-result">
              {CHECK_TEXT[check.result.kind]}
              {check.result.kind === 'available' ? ` ${check.result.tag}.` : ''}
            </p>
          </>
        )}
      </section>

      <section className="settings__section" aria-labelledby="account-title">
        <h2 id="account-title">Conta</h2>
        {user && <p className="muted">Conectado como {user.username}</p>}
        <ChangePasswordForm />
        <button
          type="button"
          className="btn btn--danger"
          data-testid="logout"
          onClick={() => void logout()}
        >
          Sair
        </button>
      </section>
    </main>
  );
}
