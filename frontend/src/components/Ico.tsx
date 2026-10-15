/** A decorative emoji before the label of a button: hidden from screen readers and from the accessible name, so the label stays the label. */
export function Ico({ children }: { children: string }) {
  return (
    <span aria-hidden="true" className="mr-1.5 select-none">
      {children}
    </span>
  );
}
