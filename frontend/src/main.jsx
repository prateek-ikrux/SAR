import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "@/App";
import { applyTheme, useUiStore } from "@/stores/uiStore";
import "@/index.css";

applyTheme(useUiStore.getState().theme);
window
  .matchMedia("(prefers-color-scheme: dark)")
  .addEventListener("change", () => applyTheme(useUiStore.getState().theme));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // A failed request here is usually a 401 or a slow ENN query, neither of
      // which is helped by retrying.
      retry: false,
    },
  },
});

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
