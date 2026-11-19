import { useNavigate } from "react-router-dom";
import { ChevronsUpDown, LogOut, Palette, Settings, UserRound } from "lucide-react";
import { useSession } from "../../app/session/context";
import Menu from "../../shared/ui/Menu";
import type { MenuItem } from "../../shared/ui/Menu";
import "./Account.css";

type AccountMenuProps = {
    /** "header" is the avatar at the top right; "sidebar" is the identity row under the navigation. */
    variant: "header" | "sidebar";
};

/** The signed-in user's menu. The header avatar and the sidebar identity open the same one. */
export default function AccountMenu({ variant }: AccountMenuProps) {
    const { account, displayName, logout } = useSession();
    const navigate = useNavigate();
    const initial = displayName.trim().charAt(0).toUpperCase() || "U";

    const items: MenuItem[] = [
        { label: "My Profile", icon: UserRound, onSelect: () => navigate("/profile") },
        { label: "Account Settings", icon: Settings, onSelect: () => navigate("/settings") },
        { label: "Appearance", icon: Palette, onSelect: () => navigate("/settings#appearance") },
        { label: "Sign Out", icon: LogOut, onSelect: logout, danger: true, separated: true },
    ];

    const header = (
        <>
            <strong className="account-menu__name">{displayName}</strong>
            {account && <span className="account-menu__email">{account.email}</span>}
        </>
    );

    if (variant === "sidebar") {
        return (
            <Menu
                label={`${displayName} ${account ? `@${account.username}` : "Personal workspace"}, account menu`}
                className="account-menu account-menu--sidebar"
                triggerClassName="sidebar-user-trigger"
                placement="top-start"
                header={header}
                items={items}
                trigger={
                    <>
                        {/* The initial is drawn by CSS so it is not read or counted as the button's visible label. */}
                        <span className="avatar avatar--drawn" data-initial={initial} aria-hidden="true" />
                        <span className="sidebar-user-copy">
                            <strong>{displayName}</strong>{" "}
                            <small>{account ? `@${account.username}` : "Personal workspace"}</small>
                        </span>
                        <ChevronsUpDown size={15} aria-hidden="true" />
                    </>
                }
            />
        );
    }

    return (
        <Menu
            label="Account menu"
            className="account-menu topbar-avatar"
            triggerClassName="avatar avatar-trigger"
            placement="bottom-end"
            header={header}
            items={items}
            trigger={<span aria-hidden="true">{initial}</span>}
        />
    );
}
