export function printReport(title: string): void {
  const previousTitle = document.title;
  const closed = Array.from(
    document.querySelectorAll<HTMLDetailsElement>('.report-page details')
  ).filter((details) => !details.open);
  const restore = () => {
    window.removeEventListener('afterprint', restore);
    document.title = previousTitle;
    for (const details of closed) {
      details.open = false;
    }
  };
  for (const details of closed) {
    details.open = true;
  }
  document.title = title;
  window.addEventListener('afterprint', restore);
  window.print();
}
