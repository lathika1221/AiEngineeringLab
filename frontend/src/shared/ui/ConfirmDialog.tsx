import Button from "./Button";
import Modal from "./Modal";

type ConfirmDialogProps = {
    title: string;
    description: string;
    confirmLabel: string;
    cancelLabel?: string;
    busy?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
};

/** Asks before something that cannot be undone. The safe choice is listed first. */
export default function ConfirmDialog({
    title,
    description,
    confirmLabel,
    cancelLabel = "Cancel",
    busy = false,
    onConfirm,
    onCancel,
}: ConfirmDialogProps) {
    return (
        <Modal
            title={title}
            description={description}
            onClose={() => {
                if (!busy) onCancel();
            }}
            actions={
                <>
                    <Button disabled={busy} onClick={onCancel}>
                        {cancelLabel}
                    </Button>
                    <Button variant="danger" busy={busy} onClick={onConfirm}>
                        {confirmLabel}
                    </Button>
                </>
            }
        />
    );
}
