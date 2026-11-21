import { Navigate, Route, Routes } from 'react-router-dom';
import { LoginPage, RequireAuth } from '../features/auth';
import { LibraryPage } from '../features/library';
import { SeriesPage } from '../features/series';
import { SettingsPage } from '../features/settings';
import { ReaderRoute } from './ReaderRoute';

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<LibraryPage />} />
        <Route path="/serie/:id" element={<SeriesPage />} />
        <Route path="/ler/:itemId" element={<ReaderRoute />} />
        <Route path="/ajustes" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
