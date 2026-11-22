import { Link, useLocation } from "react-router-dom";
import { useSession } from "../../app/session/context";
import WolfHead from "../../shared/brand/WolfHead";
import { usePageTitle } from "../../shared/hooks/usePageTitle";

/** Shown for any address that is not a LATZ page. */
export default function NotFound() {
    const { authenticated } = useSession();
    const location = useLocation();

    usePageTitle("Page not found");

    return (
        <main className="guest">
            <section className="guest__card panel not-found">
                <WolfHead size={72} mood="error" />
                <h1>Page not found</h1>
                <p>
                    There is no LATZ page at <code>{location.pathname}</code>. The link may be old or
                    mistyped.
                </p>
                <Link className="btn btn--primary" to={authenticated ? "/mission-control" : "/"}>
                    {authenticated ? "Go to Mission Control" : "Go to the home page"}
                </Link>
            </section>
        </main>
    );
}
