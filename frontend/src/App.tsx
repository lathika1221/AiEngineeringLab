import { MotionConfig } from "framer-motion";
import { BrowserRouter } from "react-router-dom";

import AppRoutes from "./app/routes";
import ErrorBoundary from "./shared/ui/ErrorBoundary";
import SessionProvider from "./app/session/SessionProvider";
import NotificationsProvider from "./shared/notifications/NotificationsProvider";

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <SessionProvider>
          <NotificationsProvider>
            <ErrorBoundary scope="app">
                <AppRoutes />
            </ErrorBoundary>
          </NotificationsProvider>
        </SessionProvider>
      </BrowserRouter>
    </MotionConfig>
  );
}
