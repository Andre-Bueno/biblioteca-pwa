import { useContext } from 'react';
import { VersionContext, type VersionContextValue } from './version-context';

export function useVersion(): VersionContextValue {
  const ctx = useContext(VersionContext);
  if (!ctx) throw new Error('useVersion must be used inside <VersionProvider>');
  return ctx;
}
