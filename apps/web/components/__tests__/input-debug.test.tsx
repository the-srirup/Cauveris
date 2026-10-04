import { render, screen } from '@testing-library/react';
import { Input } from '@/components/primitives/Input';

describe('Input Debug', () => {
  it('should render label', () => {
    const { container } = render(
      <Input
        label="Session Timeout"
        hint="Minutes of inactivity before auto-logout"
        type="number"
        value={30}
        onChange={() => {}}
        className="w-24 text-right"
        min={5}
        max={480}
      />
    );
    console.log('Container HTML:', container.innerHTML);
    expect(screen.getByLabelText(/session timeout/i)).toBeInTheDocument();
  });
});