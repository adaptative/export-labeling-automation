import { useEffect } from "react";
import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import Login from "@/pages/login";
import { RouteGuard, AdminGuard } from "@/components/RouteGuard";
import { useAuthStore } from "@/store/authStore";
import Dashboard from "@/pages/dashboard";
import Orders from "@/pages/orders";
import OrdersNew from "@/pages/orders-new";
import OrderDetail from "@/pages/orders-detail";
import ItemPreview from "@/pages/item-preview";
import ItemRedirect from "@/pages/item-redirect";
import Hitl from "@/pages/hitl";
import Agents from "@/pages/agents";
import Artifacts from "@/pages/artifacts";
import Automation from "@/pages/automation";
import Rules from "@/pages/rules";
import Evals from "@/pages/evals";
import EvalsDetail from "@/pages/evals-detail";
import Cost from "@/pages/cost";
import Importers from "@/pages/importers";
import ImporterDetail from "@/pages/importer-detail";
import OnboardingImporter from "@/pages/onboarding-importer";
import PortalImporter from "@/pages/portal-importer";
import PortalPrinter from "@/pages/portal-printer";
import WarningLabels from "@/pages/warning-labels";
import Audit from "@/pages/audit";
import Admin from "@/pages/admin";
import Settings from "@/pages/settings";
import Documents from "@/pages/documents";
import { AppShell } from "@/components/AppShell";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const queryClient = new QueryClient();

function Router() {
  return (
    <Switch>
      <Route path="/login" component={Login} />

      {/* External portals — no auth, no AppShell */}
      <Route path="/portal/importer/:token" component={PortalImporter} />
      <Route path="/portal/printer/:token" component={PortalPrinter} />

      {/* Onboarding wizard — full-screen, no AppShell */}
      <Route path="/onboarding/importer" component={OnboardingImporter} />

      <Route path="/orders/new">
        <RouteGuard>
          <AppShell>
            <OrdersNew />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/orders/:id/items/:itemId">
        <RouteGuard>
          <AppShell>
            <ItemPreview />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/items/:id">
        <RouteGuard>
          <AppShell>
            <ItemRedirect />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/orders/:id">
        <RouteGuard>
          <AppShell>
            <OrderDetail />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/orders">
        <RouteGuard>
          <AppShell>
            <Orders />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/documents">
        <RouteGuard>
          <AppShell>
            <Documents />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/hitl">
        <RouteGuard>
          <AppShell>
            <Hitl />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/agents">
        <RouteGuard>
          <AppShell>
            <Agents />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/artifacts">
        <RouteGuard>
          <AppShell>
            <Artifacts />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/automation">
        <RouteGuard>
          <AppShell>
            <Automation />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/rules">
        <RouteGuard>
          <AppShell>
            <Rules />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/evals/:id">
        <RouteGuard>
          <AppShell>
            <EvalsDetail />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/evals">
        <RouteGuard>
          <AppShell>
            <Evals />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/cost">
        <RouteGuard>
          <AppShell>
            <Cost />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/importers/:id">
        <RouteGuard>
          <AppShell>
            <ImporterDetail />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/importers">
        <RouteGuard>
          <AppShell>
            <Importers />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/warning-labels">
        <RouteGuard>
          <AppShell>
            <WarningLabels />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/audit">
        <RouteGuard>
          <AppShell>
            <Audit />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/admin/:section">
        <RouteGuard>
          <AdminGuard>
            <AppShell>
              <Admin />
            </AppShell>
          </AdminGuard>
        </RouteGuard>
      </Route>
      <Route path="/settings/:section">
        <RouteGuard>
          <AppShell>
            <Settings />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route path="/">
        <RouteGuard>
          <AppShell>
            <Dashboard />
          </AppShell>
        </RouteGuard>
      </Route>
      <Route>
        <AppShell>
          <NotFound />
        </AppShell>
      </Route>
    </Switch>
  );
}

function App() {
  useEffect(() => {
    useAuthStore.getState().verifySession();
  }, []);

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
            <Router />
          </WouterRouter>
          <Toaster />
          <SonnerToaster position="top-right" richColors closeButton />
        </TooltipProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
