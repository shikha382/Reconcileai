import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page__header">
      <div className="page__heading-copy">
        <span className="page__eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p className="page__description">{description}</p>
      </div>
      {actions && <div className="page__actions">{actions}</div>}
    </header>
  );
}
