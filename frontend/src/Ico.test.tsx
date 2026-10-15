import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Ico } from './components/Ico';

describe('Ico (Stage 18G)', () => {
  it('is decorative: hidden from the accessible name and from text queries on the label', () => {
    render(<button type="button"><Ico>✏️</Ico>Edytuj</button>);
    expect(screen.getByRole('button', { name: 'Edytuj' })).toBeInTheDocument();
    expect(screen.getByText('Edytuj')).toBe(screen.getByRole('button'));
    expect(screen.getByRole('button').querySelector('[aria-hidden="true"]')).toHaveTextContent('✏️');
  });
});
