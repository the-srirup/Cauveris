import { render, screen } from '@testing-library/react';
import SettingsPage from '@/app/settings/page';
import { ShellProvider } from '@/lib/useShell';

describe('SettingsPage Debug', () => {
  it('should have session timeout label', () => {
    render(
      <ShellProvider>
        <SettingsPage />
      </ShellProvider>
    );
    console.log('Full container HTML:', document.body.innerHTML);
    try {
      const label = screen.getByLabelText(/session timeout/i);
      console.log('Found label:', label);
    } catch (e) {
      console.log('Could not find label');
      // Print all labels
      const labels = document.querySelectorAll('label');
      console.log('All labels:', Array.from(labels).map(l => l.textContent));
    }
  });
});