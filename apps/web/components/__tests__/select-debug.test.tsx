import { render, screen } from '@testing-library/react';
import { Select } from '@/components/primitives/Select';

describe('Select Debug', () => {
  it('should not pass label prop to select element', () => {
    const { container } = render(
      <Select
        label="Test Label"
        value=""
        onChange={() => {}}
        options={[{ value: "1", label: "Option 1" }]}
        className="w-32"
      />
    );
    console.log('Container HTML:', container.innerHTML);
    const select = container.querySelector('select');
    console.log('Select element:', select?.outerHTML);
    console.log('Select props:', select?.attributes);
    if (select) {
      expect(select.hasAttribute('label')).toBe(false);
    }
  });
});