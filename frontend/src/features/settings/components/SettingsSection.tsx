import type { ReactNode } from 'react';
import { SectionIcon, type SectionIconName } from './SectionIcon';

interface SettingsSectionProps {
  id: string;
  icon: SectionIconName;
  title: string;
  description?: string;
  children: ReactNode;
}

/** Card with icon, title and short description; the `id` feeds aria-labelledby. */
export function SettingsSection({ id, icon, title, description, children }: SettingsSectionProps) {
  return (
    <section className="settings__card" aria-labelledby={id}>
      <header className="settings__card-head">
        <SectionIcon name={icon} />
        <div className="settings__card-text">
          <h2 id={id} className="settings__card-title">
            {title}
          </h2>
          {description && <p className="settings__card-desc">{description}</p>}
        </div>
      </header>
      <div className="settings__card-body">{children}</div>
    </section>
  );
}
