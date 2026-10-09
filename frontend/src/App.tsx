import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { AuthenticatedRoute } from "@/auth/AuthenticatedRoute";
import { HomePage } from "@/pages/Home";
import { LoginPage } from "@/pages/Login";
import { SignupPage } from "@/pages/Signup";
import { ForgotPasswordPage } from "@/pages/ForgotPassword";
import { ResetPasswordPage } from "@/pages/ResetPassword";
import { VerifyEmailPage } from "@/pages/VerifyEmail";
import { AccountPage } from "@/pages/Account";
import { OwnerLayout } from "@/pages/owner/OwnerLayout";
import { OwnerDashboardPage } from "@/pages/owner/Dashboard";
import { OwnerProjectNewPage } from "@/pages/owner/ProjectNew";
import { OwnerProjectDetailPage } from "@/pages/owner/ProjectDetail";
import { OwnerVerifyPage } from "@/pages/owner/Verify";
import { OwnerStatusPage } from "@/pages/owner/Status";
import { ServiceProviderLayout } from "@/pages/service-provider/ServiceProviderLayout";
import { ServiceProviderDashboardPage } from "@/pages/service-provider/Dashboard";
import { ServiceProviderSavedPage } from "@/pages/service-provider/Saved";
import { ServiceProviderFeedPage } from "@/pages/service-provider/Feed";
import { ServiceProviderVerifyPage } from "@/pages/service-provider/Verify";
import { ServiceProviderStatusPage } from "@/pages/service-provider/Status";
import { ServiceProviderOfferPage } from "@/pages/service-provider/Offer";
import { ServiceProviderSubscribePage } from "@/pages/service-provider/Subscribe";
import { AdminLayout } from "@/pages/admin/AdminLayout";
import { AdminRequirementsPage } from "@/pages/admin/Requirements";
import { AdminCategoriesPage } from "@/pages/admin/Categories";
import { InvitePage } from "@/pages/Invite";
import { OwnerOfferDetailPage } from "@/pages/owner/OfferDetail";
import { OwnerCompareOffersPage } from "@/pages/owner/CompareOffers";
import { OwnerProjectPreviewPage } from "@/pages/owner/ProjectPreview";
import { AdminReviewPage } from "@/pages/admin/Review";
import { AdminReviewReportsPage } from "@/pages/admin/ReviewReports";
import { AdminOverviewPage } from "@/pages/admin/Overview";
import { AdminServiceProvidersPage } from "@/pages/admin/ServiceProviders";
import { AdminServiceProviderDetailPage } from "@/pages/admin/ServiceProviderDetail";
import { AdminOwnersPage } from "@/pages/admin/Owners";
import { AdminOwnerDetailPage } from "@/pages/admin/OwnerDetail";
import { AdminOffersPage } from "@/pages/admin/Offers";
import { AdminProjectsPage } from "@/pages/admin/Projects";
import { AdminProjectDetailPage } from "@/pages/admin/ProjectDetail";
import { AdminCmsPage } from "@/pages/admin/Cms";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/invite/:token" element={<InvitePage />} />
        <Route
          path="/account"
          element={
            <AuthenticatedRoute>
              <AccountPage />
            </AuthenticatedRoute>
          }
        />

        <Route
          path="/owner/verify"
          element={
            <ProtectedRoute role="owner">
              <OwnerLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<OwnerVerifyPage />} />
        </Route>
        <Route
          path="/owner/status"
          element={
            <ProtectedRoute role="owner">
              <OwnerLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<OwnerStatusPage />} />
        </Route>
        <Route
          path="/owner"
          element={
            <ProtectedRoute role="owner" gate>
              <OwnerLayout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<OwnerDashboardPage />} />
          <Route path="projects/new" element={<OwnerProjectNewPage />} />
          <Route path="projects/:id" element={<OwnerProjectDetailPage />} />
          <Route path="projects/:id/preview" element={<OwnerProjectPreviewPage />} />
          <Route path="projects/:id/offers/:offerId" element={<OwnerOfferDetailPage />} />
          <Route path="projects/:id/compare" element={<OwnerCompareOffersPage />} />
        </Route>

        <Route
          path="/service-provider/dashboard"
          element={
            <ProtectedRoute role="service_provider">
              <ServiceProviderLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ServiceProviderDashboardPage />} />
        </Route>
        <Route
          path="/service-provider/verify"
          element={
            <ProtectedRoute role="service_provider">
              <ServiceProviderLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ServiceProviderVerifyPage />} />
        </Route>
        <Route
          path="/service-provider/status"
          element={
            <ProtectedRoute role="service_provider">
              <ServiceProviderLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ServiceProviderStatusPage />} />
        </Route>
        <Route
          path="/service-provider"
          element={
            <ProtectedRoute role="service_provider" gate>
              <ServiceProviderLayout />
            </ProtectedRoute>
          }
        >
          <Route path="feed" element={<ServiceProviderFeedPage />} />
          <Route path="saved" element={<ServiceProviderSavedPage />} />
          <Route path="subscribe" element={<ServiceProviderSubscribePage />} />
          <Route path="projects/:id/offer" element={<ServiceProviderOfferPage />} />
        </Route>

        <Route
          path="/admin"
          element={
            <ProtectedRoute role="admin">
              <AdminLayout />
            </ProtectedRoute>
          }
        >
          <Route path="overview" element={<AdminOverviewPage />} />
          <Route path="requirements" element={<AdminRequirementsPage />} />
          <Route path="categories" element={<AdminCategoriesPage />} />
          <Route path="review" element={<AdminReviewPage />} />
          <Route path="review-reports" element={<AdminReviewReportsPage />} />
          <Route path="service-providers" element={<AdminServiceProvidersPage />} />
          <Route path="service-providers/:id" element={<AdminServiceProviderDetailPage />} />
          <Route path="owners" element={<AdminOwnersPage />} />
          <Route path="owners/:id" element={<AdminOwnerDetailPage />} />
          <Route path="offers" element={<AdminOffersPage />} />
          <Route path="projects" element={<AdminProjectsPage />} />
          <Route path="projects/:id" element={<AdminProjectDetailPage />} />
          <Route path="cms" element={<AdminCmsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
