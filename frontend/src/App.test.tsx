import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App component', () => {
  it('renders application title and running status', () => {
    render(<App />);

    expect(
      screen.getByRole('heading', { name: /renovation app/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/frontend is running/i)).toBeInTheDocument();
  });
});
