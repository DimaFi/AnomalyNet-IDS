import { createPortal } from "react-dom";
import { useAppStore } from "../app/store";
import { Toast } from "./Toast";
import styles from "./ToastContainer.module.css";

export function ToastContainer() {
  const toasts = useAppStore((state) => state.toasts);

  if (!toasts.length) return null;

  return createPortal(
    <div className={styles.container}>
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} />
      ))}
    </div>,
    document.body
  );
}
