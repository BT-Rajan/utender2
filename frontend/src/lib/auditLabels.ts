// Admin views of the audit log: what was done, in words. The common account
// actions are named; any other code reads as words ("project.close_early" ->
// "Project close early"). The code itself stays available (title) for support.
const LABELS: Record<string, string> = {
  "stakeholder.set": "Identity set (who the account represents)",
  "verification_status.set": "Verification decision",
  "owner_verification_status.set": "Verification decision",
  "document.approved": "Document approved",
  "document.expiry_set": "Document expiry date set",
  "payment_override.grant": "Payment override granted",
  "payment_override.revoke": "Payment override revoked",
  "marketplace_access.requested": "Asked to have access activated",
  "account.deactivate": "Account deactivated",
  "account.reactivate": "Account reactivated",
  "account.email_changed": "Email address changed",
  "account.password_changed": "Password changed",
  "account.password_reset": "Password reset",
  "account.updated_by_admin": "Account details edited by an admin",
  "service_provider.admin_edit": "Company details edited by an admin",
  "service_provider.suspend": "Suspension changed",
  "owner.suspend": "Suspension changed",
  "organization.member_invited": "Person invited to the organization",
  "organization.member_joined": "Person joined the organization",
  "organization.member_added_by_admin": "Person added to the organization by an admin",
  "organization.member_removed": "Person removed from the organization",
  "organization.representative_changed": "Representative changed",
  "organization.invitation_revoked_on_deactivation": "Open invitations withdrawn (account deactivated)",
};

export function auditLabel(code: string): string {
  const known = LABELS[code];
  if (known) return known;
  const words = code.replace(/[._]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
