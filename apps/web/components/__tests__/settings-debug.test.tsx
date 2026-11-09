import { render, screen } from '@testing-library/react';
import SettingsPage from '@/app/settings/page';
import { ShellProvider } from '@/lib/useShell';

describe('SettingsPage Debug', () => {
  it('should have gateway base URL label', () => {
    render(
      <ShellProvider>
        <SettingsPage />
      </ShellProvider>
    );
    console.log('Full container HTML:', document.body.innerHTML);
    try {
      const label = screen.getByLabelText(/gateway base url/i);
      console.log('Found label:', label);
      expect(label).toBeInTheDocument();
    } catch (e) {
      console.log('Could not find label');
      // Print all labels
      const labels = document.querySelectorAll('label');
      console.log('All labels:', Array.from(labels).map(l => l.textContent));
      throw e;
    }
  });
});