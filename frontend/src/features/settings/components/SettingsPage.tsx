import { Link } from 'react-router-dom';
import { usePreferences, type ReadingDirection } from '../../../shared/preferences';
import { useSession } from '../../../shared/session';
import { SegmentedControl, ThemeToggle, type SegmentedOption } from '../../../shared/ui';
import { UpdateNotice, useVersion } from '../../../shared/system';
import { useCheckUpdates, type CheckResult } from '../hooks/useCheckUpdates';
import { ChangePasswordForm } from './ChangePasswordForm';
import { SettingsSection } from './SettingsSection';
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

      <SettingsSection
        id="appearance-title"
        icon="appearance"
        title="Aparência"
        description="Escolha o tema do app. Sistema acompanha o seu aparelho."
      >
        <ThemeToggle onSelect={(theme) => void update({ theme })} />
      </SettingsSection>

      <SettingsSection
        id="reading-title"
        icon="reading"
        title="Leitura"
        description="Sentido padrão de leitura dos mangás."
      >
        <SegmentedControl
          label="Sentido de leitura"
          options={DIRECTION_OPTIONS}
          value={preferences.reading_direction}
          onChange={(reading_direction) => void update({ reading_direction })}
          testId="reading-direction"
        />
        <p className="settings__help">
          D→E: mangá, da direita para a esquerda. E→D: da esquerda para a direita. Vertical: rolagem
          contínua (webtoon). Você pode trocar o modo dentro do leitor.
        </p>
      </SettingsSection>

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

      <SettingsSection id="about-title" icon="about" title="Sobre o app">
        {version.info?.current && (
          <dl className="settings__kv">
            <div className="settings__kv-row" data-testid="app-version">
              <dt>Versão do app:</dt> <dd>{version.info.current}</dd>
            </div>
          </dl>
        )}
        {user?.role === 'admin' && (
          <>
            <button
              type="button"
              className="btn settings__action"
              disabled={check.busy || check.blocked}
              data-testid="check-updates"
              onClick={() => void check.run()}
            >
              {check.busy ? 'Verificando…' : 'Verificar atualizações'}
            </button>
            <p className="settings__help" role="status" data-testid="check-result">
              {CHECK_TEXT[check.result.kind]}
              {check.result.kind === 'available' ? ` ${check.result.tag}.` : ''}
            </p>
          </>
        )}
      </SettingsSection>

      <SettingsSection
        id="account-title"
        icon="account"
        title="Conta"
        description="Troque a senha ou encerre a sessão neste aparelho."
      >
        {user && (
          <dl className="settings__kv">
            <div className="settings__kv-row">
              <dt>Conectado como</dt> <dd>{user.username}</dd>
            </div>
          </dl>
        )}
        <ChangePasswordForm />
        <hr className="settings__rule" />
        <button
          type="button"
          className="btn btn--danger settings__action settings__logout"
          data-testid="logout"
          onClick={() => void logout()}
        >
          Sair
        </button>
      </SettingsSection>
    </main>
  );
}
