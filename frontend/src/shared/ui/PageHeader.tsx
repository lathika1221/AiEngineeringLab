import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

export type Crumb = { label: string; to?: string };

type PageHeaderProps = {
    title: string;
    lede?: ReactNode;
    /** Trail of parent pages. The current page is added automatically. */
    breadcrumbs?: Crumb[];
    actions?: ReactNode;
    /** Small decorative mark shown beside the title. */
    mark?: ReactNode;
};

/** The one heading block every workspace page starts with. Holds the page's only h1. */
export default function PageHeader({ title, lede, breadcrumbs, actions, mark }: PageHeaderProps) {
    return (
        <header className="page-header">
            {breadcrumbs && breadcrumbs.length > 0 && (
                <nav className="breadcrumbs" aria-label="Breadcrumb">
                    <ol>
                        {breadcrumbs.map((crumb) => (
                            <li key={crumb.label}>
                                {crumb.to ? <Link to={crumb.to}>{crumb.label}</Link> : <span>{crumb.label}</span>}
                                <ChevronRight size={13} aria-hidden="true" />
                            </li>
                        ))}
                        <li aria-current="page">{title}</li>
                    </ol>
                </nav>
            )}

            <div className="page-header__row">
                {mark && (
                    <div className="page-header__mark" aria-hidden="true">
                        {mark}
                    </div>
                )}
                <div className="page-header__copy">
                    <h1 className="display page-title">{title}</h1>
                    {lede && <p className="page-lede">{lede}</p>}
                </div>
                {actions && <div className="page-header__actions">{actions}</div>}
            </div>
        </header>
    );
}
