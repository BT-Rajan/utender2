export interface Dictionary {
  common: { loading: string; save: string; cancel: string; back: string };
  brand: { tagline: string };
  home: {
    login: string;
    signup: string;
    statOpen: string;
    statVerified: string;
    statAwarded: string;
    stepsLabel: string;
    afterLabel: string;
    costLabel: string;
    optional: string;
    noDocuments: string;
  };
  pricing: { monthly: string; annual: string; perMonth: string; perYear: string; unavailable: string };
  header: { logOut: string; account: string };
  language: { label: string; en: string; ar: string };
  auth: {
    login: {
      heading: string;
      email: string;
      password: string;
      submit: string;
      submitting: string;
      noAccount: string;
      signupLink: string;
      forgotPassword: string;
      genericError: string;
    };
    signup: {
      heading: string;
      iAmA: string;
      propertyOwner: string;
      contractor: string;
      chooseRole: string;
      companyName: string;
      companyNameHint: string;
      fullName: string;
      email: string;
      password: string;
      submit: string;
      submitting: string;
      haveAccount: string;
      loginLink: string;
      genericError: string;
    };
    forgotPassword: {
      heading: string;
      description: string;
      email: string;
      submit: string;
      submitting: string;
      sent: string;
      backToLogin: string;
    };
    resetPassword: {
      heading: string;
      newPassword: string;
      submit: string;
      submitting: string;
      success: string;
      invalidToken: string;
      goToLogin: string;
      requestNew: string;
      missingToken: string;
    };
    verifyEmail: {
      heading: string;
      success: string;
      invalidToken: string;
      continue: string;
      missingToken: string;
    };
    changePassword: {
      heading: string;
      currentPassword: string;
      newPassword: string;
      submit: string;
      submitting: string;
      success: string;
    };
    emailVerifyBanner: { message: string; resend: string; sent: string };
  };
  clarifications: {
    heading: string;
    noQuestions: string;
    sealedBidder: string;
    privateTag: string;
    writeAnswerPlaceholder: string;
    answerButton: string;
    awaitingAnswer: string;
    shareCheckboxLabel: string;
    askPlaceholder: string;
    askButton: string;
    askError: string;
    answerError: string;
  };
  contractor: {
    roleLabel: string;
    dashboard: {
      kpiActiveBids: string;
      kpiProjectsWon: string;
      kpiTotalBids: string;
      myBids: string;
      browseOpenProjects: string;
      noBidsYetPrefix: string;
      banner: {
        documentsIncompleteTitle: string;
        documentsIncompleteBody: string;
        documentsIncompleteCta: string;
        submittedTitle: string;
        submittedBody: string;
        submittedCta: string;
        changesRequestedTitle: string;
        changesRequestedBody: string;
        changesRequestedCta: string;
        paymentRequiredTitle: string;
        paymentRequiredBody: string;
        paymentRequiredCta: string;
        paymentRestrictedTitle: string;
        paymentRestrictedBody: string;
        paymentRestrictedCta: string;
        suspendedTitle: string;
        suspendedBody: string;
      };
    };
    feed: {
      eyebrow: string;
      heading: string;
      sortedNewest: string;
      sortedClosest: string;
      subscribeBanner: string;
      viewPlans: string;
      searchPlaceholder: string;
      allTrades: string;
      sortClosest: string;
      sortNewest: string;
      noMatch: string;
      noOpenProjects: string;
      deadline: string;
      offersSoFar: string;
      trade: string;
      bidPlaced: string;
      lockedTitle: string;
      lockedDescription: string;
    };
    status: {
      suspendedTitle: string;
      suspendedBody: string;
      approvedTitle: string;
      approvedBody: string;
      eyebrow: string;
      heading: string;
      changesRequestedTitle: string;
      underReviewTitle: string;
      submittedOn: string;
      pending: string;
      actionNeeded: string;
      document: string;
      statusCol: string;
      required: string;
      optional: string;
      adminNote: string;
      reupload: string;
      upload: string;
      footerNote: string;
    };
    verify: {
      eyebrow: string;
      heading: string;
      description: string;
      companyName: string;
      licenseNumber: string;
      document: string;
      statusCol: string;
      required: string;
      optional: string;
      submitting: string;
      submit: string;
      uploadError: string;
      submitError: string;
    };
    subscribe: {
      feature1: string;
      feature2: string;
      feature3: string;
      feature4: string;
      save: string;
      priceMonthlyNote: string;
      priceAnnualNote: string;
      start: string;
      eyebrow: string;
      headingActive: string;
      headingInactive: string;
      subheadingActive: string;
      subheadingInactive: string;
      overrideBadge: string;
      overrideMessage: string;
      renews: string;
      manageBilling: string;
      checkoutNote: string;
      checkoutError: string;
      portalError: string;
    };
    offer: {
      deadlineLabel: string;
      closed: string;
      scope: string;
      drawings: string;
      downloadZip: string;
      noDrawings: string;
      biddingClosedNotice: string;
      yourFinalOffer: string;
      awardedTo: string;
      anotherContractor: string;
      noAwardNotice: string;
      bidAmount: string;
      timeline: string;
      timelinePlaceholder: string;
      messageToOwner: string;
      messagePlaceholder: string;
      updateOffer: string;
      submitOffer: string;
      withdraw: string;
      withdrawing: string;
      tipsHeading: string;
      tip1: string;
      tip2: string;
      tip3: string;
      withdrawError: string;
      submitError: string;
      notAvailableNotice: string;
    };
  };
  owner: {
    roleLabel: string;
    dashboard: {
      statusAll: string;
      statusDraft: string;
      statusOpen: string;
      statusAwaitingReview: string;
      statusUnderEvaluation: string;
      statusAwarded: string;
      statusNoAward: string;
      statusCanceled: string;
      statusExpired: string;
      eyebrow: string;
      heading: string;
      newProject: string;
      kpiOpen: string;
      kpiAwaitingReview: string;
      kpiUnderEvaluation: string;
      kpiAwarded: string;
      kpiTotalOffers: string;
      emptyStatePrefix: string;
      emptyStateLink: string;
      emptyStateSuffix: string;
      searchPlaceholder: string;
      allTenderTypes: string;
      sealed: string;
      ownerVisible: string;
      noMatch: string;
      nothingHere: string;
      offersReceived: string;
      readyToReview: string;
      deadline: string;
      trade: string;
      posted: string;
    };
    projectNew: {
      eyebrow: string;
      heading: string;
      description: string;
      tenderType: string;
      ownerVisibleToggle: string;
      sealedToggle: string;
      ownerVisibleHint: string;
      sealedHint: string;
      title: string;
      titlePlaceholder: string;
      address: string;
      addressPlaceholder: string;
      trade: string;
      tradePlaceholder: string;
      scope: string;
      scopePlaceholder: string;
      drawings: string;
      drawingsHint: string;
      drawingsAccessNote: string;
      deadline: string;
      deadlineNote: string;
      postProject: string;
      posting: string;
      saveAsDraft: string;
      draftNote: string;
      sidebarHeading: string;
      tip1: string;
      tip2: string;
      tip3: string;
      validationError: string;
      submitError: string;
    };
    projectDetail: {
      reviewOffers: string;
      sealedBadge: string;
      ownerVisibleBadge: string;
      publish: string;
      closeEarly: string;
      startEvaluation: string;
      markNoAward: string;
      cancelProject: string;
      noDrawings: string;
      downloadZip: string;
      hideHistory: string;
      viewHistory: string;
      noHistory: string;
      current: string;
      view: string;
      addDrawings: string;
      zipHint: string;
      scope: string;
      lowestBid: string;
      averageBid: string;
      highestBid: string;
      sealedBidsReceived: string;
      sealedExplanation: string;
      noOffersYet: string;
      contractorCol: string;
      ratingCol: string;
      bidCol: string;
      timelineCol: string;
      revisedSuffix: string;
      approve: string;
      closeToAwardHint: string;
      rateContractor: string;
      theContractor: string;
      submittedOn: string;
      ratingPlaceholder: string;
      submitReview: string;
      approveError: string;
      drawingsError: string;
      reviewError: string;
      statusError: string;
    };
    verify: {
      eyebrow: string;
      heading: string;
      description: string;
      document: string;
      statusCol: string;
      required: string;
      optional: string;
      submitting: string;
      submit: string;
      uploadError: string;
      submitError: string;
    };
    status: {
      suspendedTitle: string;
      suspendedBody: string;
      approvedTitle: string;
      approvedBody: string;
      eyebrow: string;
      heading: string;
      changesRequestedTitle: string;
      underReviewTitle: string;
      submittedOn: string;
      pending: string;
      actionNeeded: string;
      document: string;
      statusCol: string;
      required: string;
      optional: string;
      adminNote: string;
      reupload: string;
      upload: string;
      footerNote: string;
    };
  };
  admin: {
    nav: {
      requirements: string;
      review: string;
      contractors: string;
      owners: string;
      offers: string;
      projects: string;
      cms: string;
    };
    owners: {
      eyebrow: string;
      heading: string;
      total: string;
      empty: string;
      name: string;
      status: string;
      projects: string;
      manage: string;
    };
    ownerDetail: {
      docReviewError: string;
      approveError: string;
      rejectError: string;
      suspendError: string;
      deleteError: string;
      suspended: string;
      documentsHeading: string;
      document: string;
      statusCol: string;
      approve: string;
      reject: string;
      applicationHeading: string;
      currentStatus: string;
      approveApplication: string;
      requestChanges: string;
      accessHeading: string;
      reactivate: string;
      suspend: string;
      suspendedNote: string;
      suspendNote: string;
      dangerZone: string;
      deleteBlockedNote: string;
      deleteNote: string;
      deleteConfirm: string;
      deleteAccount: string;
      projectsHeading: string;
      noProjects: string;
      projectTitleCol: string;
      projectStatusCol: string;
      projectOffersCol: string;
      viewProject: string;
    };
    offers: {
      eyebrow: string;
      heading: string;
      total: string;
      empty: string;
      project: string;
      contractor: string;
      amount: string;
      status: string;
      tenderType: string;
      submitted: string;
      revised: string;
      suspendedBadge: string;
      viewProject: string;
    };
    projects: {
      eyebrow: string;
      heading: string;
      total: string;
      empty: string;
      owner: string;
      title: string;
      status: string;
      offers: string;
      suspendedBadge: string;
      manage: string;
    };
    projectDetail: {
      eyebrow: string;
      suspended: string;
      editHeading: string;
      titleLabel: string;
      addressLabel: string;
      descriptionLabel: string;
      tradeLabel: string;
      deadlineLabel: string;
      saveChanges: string;
      saveError: string;
      accessHeading: string;
      reactivate: string;
      suspend: string;
      suspendedNote: string;
      suspendNote: string;
      suspendError: string;
      dangerZone: string;
      deleteBlockedNote: string;
      deleteNote: string;
      deleteConfirm: string;
      deleteProject: string;
      deleteError: string;
      offersHeading: string;
      noOffers: string;
      contractorCol: string;
      amountCol: string;
      timelineCol: string;
      statusCol: string;
      actionsCol: string;
      edit: string;
      editOfferHeading: string;
      amountFieldLabel: string;
      timelineFieldLabel: string;
      messageFieldLabel: string;
      saveOffer: string;
      cancel: string;
      editOfferError: string;
      suspendOffer: string;
      reactivateOffer: string;
      suspendOfferError: string;
      deleteOffer: string;
      deleteOfferError: string;
      deleteOfferConfirm: string;
      deleteOfferBlocked: string;
      offerSuspendedBadge: string;
    };
    requirements: {
      eyebrow: string;
      heading: string;
      description: string;
      forContractors: string;
      forOwners: string;
      emptyForScope: string;
      toggleRequiredFor: string;
      required: string;
      optional: string;
      removeTitle: string;
      namePlaceholder: string;
      descriptionPlaceholder: string;
      addForOwners: string;
      addForContractors: string;
      edit: string;
      addError: string;
      updateError: string;
      removeError: string;
    };
  };
}

export const en: Dictionary = {
  common: {
    loading: "Loading…",
    save: "Save",
    cancel: "Cancel",
    back: "Back",
  },
  brand: {
    tagline: "Drawings in. Offers out.",
  },
  home: {
    login: "Log in",
    signup: "Sign up",
    statOpen: "Open tenders",
    statVerified: "Verified service providers",
    statAwarded: "Projects awarded",
    stepsLabel: "What you'll do",
    afterLabel: "After you sign up",
    costLabel: "Cost",
    optional: "optional",
    noDocuments: "No documents are currently required.",
  },
  pricing: {
    monthly: "Monthly",
    annual: "Annual",
    perMonth: "/ month",
    perYear: "/ year",
    unavailable: "Subscription prices are shown on the subscription page before you pay.",
  },
  header: {
    logOut: "Log out",
    account: "Account",
  },
  language: {
    label: "Language",
    en: "English",
    ar: "العربية",
  },
  auth: {
    login: {
      heading: "Log in",
      email: "Email",
      password: "Password",
      submit: "Log in",
      submitting: "Logging in…",
      noAccount: "No account?",
      signupLink: "Sign up",
      forgotPassword: "Forgot password?",
      genericError: "Invalid email or password.",
    },
    signup: {
      heading: "Create an account",
      iAmA: "I am a...",
      propertyOwner: "Owner",
      contractor: "Service provider",
      chooseRole: "Choose Owner or Service provider to continue.",
      companyName: "Company name",
      companyNameHint: "You'll submit verification documents after signing up.",
      fullName: "Full name",
      email: "Email",
      password: "Password",
      submit: "Create account",
      submitting: "Creating…",
      haveAccount: "Already have an account?",
      loginLink: "Log in",
      genericError: "Could not create account.",
    },
    forgotPassword: {
      heading: "Reset your password",
      description: "Enter your account email and we'll send you a link to reset your password.",
      email: "Email",
      submit: "Send reset link",
      submitting: "Sending…",
      sent: "If an account with that email exists, a reset link has been sent.",
      backToLogin: "Back to log in",
    },
    resetPassword: {
      heading: "Choose a new password",
      newPassword: "New password",
      submit: "Reset password",
      submitting: "Resetting…",
      success: "Your password has been reset. You can now log in.",
      invalidToken: "This reset link is invalid or has expired.",
      goToLogin: "Go to log in",
      requestNew: "Request a new reset link",
      missingToken: "No reset token was provided.",
    },
    verifyEmail: {
      heading: "Verifying your email…",
      success: "Your email address has been verified.",
      invalidToken: "This verification link is invalid or has expired.",
      continue: "Continue",
      missingToken: "No verification token was provided.",
    },
    changePassword: {
      heading: "Change password",
      currentPassword: "Current password",
      newPassword: "New password",
      submit: "Change password",
      submitting: "Changing…",
      success: "Password changed.",
    },
    emailVerifyBanner: {
      message: "Please verify your email address.",
      resend: "Resend verification email",
      sent: "Verification email sent.",
    },
  },
  clarifications: {
    heading: "Questions & answers",
    noQuestions: "No questions yet.",
    sealedBidder: "sealed bidder",
    privateTag: "private",
    writeAnswerPlaceholder: "Write an answer…",
    answerButton: "Answer",
    awaitingAnswer: "Awaiting an answer from the owner.",
    shareCheckboxLabel: "Share this Q&A with other bidders once answered",
    askPlaceholder: "Ask the owner a question about this project…",
    askButton: "Ask",
    askError: "Could not submit your question.",
    answerError: "Could not submit your answer.",
  },
  contractor: {
    roleLabel: "Service provider",
    dashboard: {
      kpiActiveBids: "Active bids",
      kpiProjectsWon: "Projects won",
      kpiTotalBids: "Total bids placed",
      myBids: "My bids",
      browseOpenProjects: "Browse open projects",
      noBidsYetPrefix: "You haven't placed any bids yet.",
      banner: {
        documentsIncompleteTitle: "Finish verifying your company",
        documentsIncompleteBody: "Upload your documents so an admin can review your account.",
        documentsIncompleteCta: "Continue verification",
        submittedTitle: "Application under review",
        submittedBody: "An admin is reviewing your documents. We'll notify you once a decision is made.",
        submittedCta: "View submission",
        changesRequestedTitle: "Changes requested",
        changesRequestedBody: "One or more documents need to be re-uploaded before your account can be approved.",
        changesRequestedCta: "Review and re-upload",
        paymentRequiredTitle: "Subscribe to unlock bidding",
        paymentRequiredBody: "You're verified — subscribe to view drawings and submit offers.",
        paymentRequiredCta: "View plans",
        paymentRestrictedTitle: "Payment issue on your account",
        paymentRestrictedBody: "Your subscription payment failed or is past due. Update billing to keep bidding.",
        paymentRestrictedCta: "Manage billing",
        suspendedTitle: "Account suspended",
        suspendedBody: "Your account has been suspended by a site admin. Contact support if you believe this is a mistake.",
      },
    },
    feed: {
      eyebrow: "Service provider · Open projects",
      heading: "Projects open for bidding",
      sortedNewest: "Sorted by most recently posted.",
      sortedClosest: "Sorted by closing soonest.",
      subscribeBanner: "You're approved, but drawings and offers stay locked until you subscribe.",
      viewPlans: "View plans",
      searchPlaceholder: "Search title, address, or scope…",
      allTrades: "All trades",
      sortClosest: "Closing soonest",
      sortNewest: "Newest first",
      noMatch: "No projects match your filters.",
      noOpenProjects: "No open projects right now. Check back soon.",
      deadline: "Deadline",
      offersSoFar: "Offers so far",
      trade: "Trade",
      bidPlaced: "Bid placed",
      lockedTitle: "Subscribe to view drawings",
      lockedDescription: "Unlock full drawings, scope details, and the ability to submit offers.",
    },
    status: {
      suspendedTitle: "Account suspended",
      suspendedBody:
        "Your account has been suspended by a site admin. You can't view new projects or submit offers while suspended. Contact support if you believe this is a mistake.",
      approvedTitle: "You're approved",
      approvedBody: "Head to your dashboard to browse open projects.",
      eyebrow: "Service provider · Account verification",
      heading: "Application status",
      changesRequestedTitle: "Changes requested — one or more documents need to be re-uploaded",
      underReviewTitle: "Application under review",
      submittedOn: "Submitted",
      pending: "Pending",
      actionNeeded: "Action needed",
      document: "Document",
      statusCol: "Status",
      required: "Required",
      optional: "Optional",
      adminNote: "Admin note:",
      reupload: "Re-upload",
      upload: "Upload",
      footerNote:
        "You'll be notified as soon as your account is fully approved. Full access to drawings and offers stays locked until then.",
    },
    verify: {
      eyebrow: "Service provider · Account verification",
      heading: "Verify your company",
      description: "Submit the documents below so a site admin can activate your account.",
      companyName: "Company name",
      licenseNumber: "License number",
      document: "Document",
      statusCol: "Status",
      required: "Required",
      optional: "Optional",
      submitting: "Submitting…",
      submit: "Submit for review",
      uploadError: "Could not upload document.",
      submitError: "Could not submit for review.",
    },
    subscribe: {
      feature1: "Unlimited open projects in your service area",
      feature2: "Full drawings and scope details on every listing",
      feature3: "Unlimited offers and revisions before deadline",
      feature4: "Public rating and review profile",
      save: "save {percent}%",
      priceMonthlyNote: "Billed monthly. No lead fees, no commission on top.",
      priceAnnualNote: "Billed annually at {amount}. No lead fees, no commission on top.",
      start: "Start subscription",
      eyebrow: "Service provider access",
      headingActive: "Your subscription",
      headingInactive: "Subscribe to bid on projects",
      subheadingActive: "Manage your plan and billing details.",
      subheadingInactive: "One plan, full access. Cancel any time.",
      overrideBadge: "admin override",
      overrideMessage: "An administrator has granted your account full marketplace access without a paid subscription.",
      renews: "Renews",
      manageBilling: "Manage billing",
      checkoutNote: "You'll be redirected to Stripe's secure checkout to complete your subscription.",
      checkoutError: "Could not start checkout. Try again.",
      portalError: "Could not open billing portal. Try again.",
    },
    offer: {
      deadlineLabel: "Deadline",
      closed: "Closed",
      scope: "Scope",
      drawings: "Drawings",
      downloadZip: "Download all as .zip",
      noDrawings: "No drawings were uploaded for this project.",
      biddingClosedNotice: "Bidding on this project has closed.",
      yourFinalOffer: "Your final offer:",
      awardedTo: "Awarded to",
      anotherContractor: "another service provider",
      noAwardNotice: "The owner decided not to award this project.",
      bidAmount: "Your bid amount (USD)",
      timeline: "Estimated timeline",
      timelinePlaceholder: "e.g. 3 weeks from start",
      messageToOwner: "Message to owner",
      messagePlaceholder: "Outline your approach, materials, and anything the drawings don't cover.",
      updateOffer: "Update offer",
      submitOffer: "Submit offer",
      withdraw: "Withdraw offer",
      withdrawing: "Withdrawing…",
      tipsHeading: "Tips for winning bids",
      tip1: "Reference specific details from the drawings — it signals you reviewed them closely.",
      tip2: "Owners can see your rating and past reviews next to your bid.",
      tip3: "You can revise your offer any time before the deadline.",
      withdrawError: "Could not withdraw offer.",
      submitError: "Could not submit offer.",
      notAvailableNotice: "That project isn't available to you right now.",
    },
  },
  owner: {
    roleLabel: "Owner",
    dashboard: {
      statusAll: "All statuses",
      statusDraft: "Draft",
      statusOpen: "Open",
      statusAwaitingReview: "Awaiting review",
      statusUnderEvaluation: "Under evaluation",
      statusAwarded: "Awarded",
      statusNoAward: "No award",
      statusCanceled: "Canceled",
      statusExpired: "Expired",
      eyebrow: "Owner dashboard",
      heading: "Your projects",
      newProject: "+ New project",
      kpiOpen: "Open",
      kpiAwaitingReview: "Awaiting review",
      kpiUnderEvaluation: "Under evaluation",
      kpiAwarded: "Awarded",
      kpiTotalOffers: "Total offers",
      emptyStatePrefix: "You haven't posted a project yet.",
      emptyStateLink: "Post your first one",
      emptyStateSuffix: "to start receiving offers.",
      searchPlaceholder: "Search title or address…",
      allTenderTypes: "All tender types",
      sealed: "Sealed",
      ownerVisible: "Owner-visible",
      noMatch: "No projects match your filters.",
      nothingHere: "Nothing here.",
      offersReceived: "offer(s) received",
      readyToReview: "ready to review",
      deadline: "Deadline",
      trade: "Trade",
      posted: "Posted",
    },
    projectNew: {
      eyebrow: "New project",
      heading: "Post a project",
      description: "Add your drawings and set a deadline — service providers can only bid before it closes.",
      tenderType: "Tender type",
      ownerVisibleToggle: "Owner-visible",
      sealedToggle: "Sealed",
      ownerVisibleHint: "You can see bids as they come in. Locked in once the first bid arrives.",
      sealedHint: "Bids stay hidden from you until bidding closes. Locked in once the first bid arrives.",
      title: "Project title",
      titlePlaceholder: "e.g. Maple St. Duplex — Roof Replacement",
      address: "Site address",
      addressPlaceholder: "Street, city, state",
      trade: "Trade",
      tradePlaceholder: "e.g. Roofing, Framing, Fencing",
      scope: "Scope of work",
      scopePlaceholder: "Describe the work you need done. Service providers will use this alongside your drawings to price their offer.",
      drawings: "Drawings",
      drawingsHint: "PDF, DWG, JPG, PNG, or a .zip folder of drawings — up to 50MB total",
      drawingsAccessNote: "Only approved, subscribed service providers can view these files.",
      deadline: "Bid deadline",
      deadlineNote: "No offers are accepted after this time.",
      postProject: "Post project",
      posting: "Posting…",
      saveAsDraft: "Save as draft",
      draftNote: "A draft is only visible to you. Publish it later from the project page when you're ready for bids.",
      sidebarHeading: "Before you post",
      tip1: "Clear drawings get more accurate offers — include dimensions where you can.",
      tip2: "Give service providers at least 5–7 days to price the job properly.",
      tip3: "You won't be charged. Posting and reviewing offers is free for property owners.",
      validationError: "Title, address, and deadline are required.",
      submitError: "Could not create project.",
    },
    projectDetail: {
      reviewOffers: "Review offers",
      sealedBadge: "Sealed",
      ownerVisibleBadge: "Owner-visible",
      publish: "Publish — start accepting bids",
      closeEarly: "Close bidding early",
      startEvaluation: "Start evaluation",
      markNoAward: "Mark no award",
      cancelProject: "Cancel project",
      noDrawings: "No drawings uploaded yet",
      downloadZip: "Download all as .zip",
      hideHistory: "Hide revision history",
      viewHistory: "View revision history",
      noHistory: "No revision history yet.",
      current: "(current)",
      view: "view",
      addDrawings: "Add drawings",
      zipHint: "You can also upload a .zip folder of drawings.",
      scope: "Scope",
      lowestBid: "Lowest bid",
      averageBid: "Average bid",
      highestBid: "Highest bid",
      sealedBidsReceived: "sealed bid(s) received",
      sealedExplanation:
        "This is a sealed tender — bidder identities and amounts stay hidden from you until bidding closes. Close bidding to reveal and evaluate them.",
      noOffersYet: "No offers yet. Service providers can bid until the deadline above.",
      contractorCol: "Service provider",
      ratingCol: "Rating",
      bidCol: "Bid",
      timelineCol: "Timeline",
      revisedSuffix: "revised x",
      approve: "Approve",
      closeToAwardHint: "Close bidding to award",
      rateContractor: "Rate",
      theContractor: "the service provider",
      submittedOn: "Submitted",
      ratingPlaceholder: "How did the work go? Optional, but helps other owners.",
      submitReview: "Submit review",
      approveError: "Could not approve this offer.",
      drawingsError: "Could not add drawings.",
      reviewError: "Could not submit review.",
      statusError: "Could not update this project's status.",
    },
    verify: {
      eyebrow: "Owner · Account verification",
      heading: "Verify your account",
      description: "Submit the documents below so a site admin can activate your account.",
      document: "Document",
      statusCol: "Status",
      required: "Required",
      optional: "Optional",
      submitting: "Submitting…",
      submit: "Submit for review",
      uploadError: "Could not upload document.",
      submitError: "Could not submit for review.",
    },
    status: {
      suspendedTitle: "Account suspended",
      suspendedBody:
        "Your account has been suspended by a site admin. You can't post or manage projects while suspended. Contact support if you believe this is a mistake.",
      approvedTitle: "You're approved",
      approvedBody: "Head to your dashboard to post a project.",
      eyebrow: "Owner · Account verification",
      heading: "Application status",
      changesRequestedTitle: "Changes requested — one or more documents need to be re-uploaded",
      underReviewTitle: "Application under review",
      submittedOn: "Submitted",
      pending: "Pending",
      actionNeeded: "Action needed",
      document: "Document",
      statusCol: "Status",
      required: "Required",
      optional: "Optional",
      adminNote: "Admin note:",
      reupload: "Re-upload",
      upload: "Upload",
      footerNote:
        "You'll be notified as soon as your account is fully approved. Posting and managing projects stays locked until then.",
    },
  },
  admin: {
    nav: {
      requirements: "Document requirements",
      review: "Review applications",
      contractors: "All service providers",
      owners: "All owners",
      offers: "All offers",
      projects: "All projects",
      cms: "Website content",
    },
    owners: {
      eyebrow: "Admin · Owners",
      heading: "All property owners",
      total: "total",
      empty: "No owners have signed up yet.",
      name: "Name",
      status: "Status",
      projects: "Projects",
      manage: "Manage",
    },
    ownerDetail: {
      docReviewError: "Could not update this document.",
      approveError: "Could not approve this owner.",
      rejectError: "Could not request changes.",
      suspendError: "Could not update account access.",
      deleteError: "Could not delete this owner.",
      suspended: "Suspended",
      documentsHeading: "Verification documents",
      document: "Document",
      statusCol: "Status",
      approve: "Approve",
      reject: "Reject",
      applicationHeading: "Application",
      currentStatus: "Current status",
      approveApplication: "Approve owner",
      requestChanges: "Request changes",
      accessHeading: "Account access",
      reactivate: "Reactivate account",
      suspend: "Suspend account",
      suspendedNote: "This owner can't post or manage projects until reactivated.",
      suspendNote: "Immediately blocks the owner from posting or managing projects, without deleting anything.",
      dangerZone: "Danger zone",
      deleteBlockedNote:
        "This owner has posted projects. Suspend the account instead of deleting it, to keep that project and offer history intact for the service providers involved.",
      deleteNote: "This owner has no projects yet, so deleting removes the account entirely. This can't be undone.",
      deleteConfirm: "Permanently delete this owner's account? This can't be undone.",
      deleteAccount: "Delete account",
      projectsHeading: "Projects posted",
      noProjects: "This owner hasn't posted any projects yet.",
      projectTitleCol: "Project",
      projectStatusCol: "Status",
      projectOffersCol: "Offers",
      viewProject: "View",
    },
    offers: {
      eyebrow: "Admin · Offers",
      heading: "All offers",
      total: "total",
      empty: "No offers have been submitted yet.",
      project: "Project",
      contractor: "Service provider",
      amount: "Amount",
      status: "Status",
      tenderType: "Tender type",
      submitted: "Submitted",
      revised: "revised",
      suspendedBadge: "Offer suspended",
      viewProject: "View full project",
    },
    projects: {
      eyebrow: "Admin · Projects",
      heading: "All projects",
      total: "total",
      empty: "No projects have been posted yet.",
      owner: "Owner",
      title: "Project",
      status: "Status",
      offers: "Offers",
      suspendedBadge: "Suspended",
      manage: "Manage",
    },
    projectDetail: {
      eyebrow: "Admin · Projects",
      suspended: "Suspended",
      editHeading: "Project details",
      titleLabel: "Title",
      addressLabel: "Address",
      descriptionLabel: "Scope",
      tradeLabel: "Trade",
      deadlineLabel: "Bid deadline",
      saveChanges: "Save changes",
      saveError: "Could not save changes.",
      accessHeading: "Marketplace visibility",
      reactivate: "Reactivate project",
      suspend: "Suspend project",
      suspendedNote: "This project is hidden from the service provider feed and can't receive new offers until reactivated.",
      suspendNote: "Immediately hides this project from the service provider feed and blocks new offers, without deleting anything.",
      suspendError: "Could not update project visibility.",
      dangerZone: "Danger zone",
      deleteBlockedNote:
        "This project has offers on it. Suspend it instead of deleting it, to keep that bid history intact for the service providers involved.",
      deleteNote: "This project has no offers yet, so deleting removes it entirely. This can't be undone.",
      deleteConfirm: "Permanently delete this project? This can't be undone.",
      deleteProject: "Delete project",
      deleteError: "Could not delete this project.",
      offersHeading: "Offers on this project",
      noOffers: "No offers have been submitted on this project.",
      contractorCol: "Service provider",
      amountCol: "Amount",
      timelineCol: "Timeline",
      statusCol: "Status",
      actionsCol: "",
      edit: "Edit",
      editOfferHeading: "Edit offer",
      amountFieldLabel: "Amount (USD)",
      timelineFieldLabel: "Timeline",
      messageFieldLabel: "Message",
      saveOffer: "Save",
      cancel: "Cancel",
      editOfferError: "Could not save this offer.",
      suspendOffer: "Suspend",
      reactivateOffer: "Reactivate",
      suspendOfferError: "Could not update this offer.",
      deleteOffer: "Delete",
      deleteOfferError: "Could not delete this offer.",
      deleteOfferConfirm: "Permanently delete this offer? This can't be undone.",
      deleteOfferBlocked: "This offer was awarded — suspend it instead of deleting it.",
      offerSuspendedBadge: "Offer suspended",
    },
    requirements: {
      eyebrow: "Admin · Document requirements",
      heading: "Required documents",
      description:
        "Turn requirements on or off, or remove one entirely. Changes apply to new submissions right away — accounts already approved aren't affected.",
      forContractors: "For service providers",
      forOwners: "For owners",
      emptyForScope: "No requirements set up for this group yet.",
      toggleRequiredFor: "Toggle required for",
      required: "Required",
      optional: "Optional",
      removeTitle: "Remove requirement",
      namePlaceholder: "Document name, e.g. Civil ID",
      descriptionPlaceholder: "Short description shown to the applicant",
      addForOwners: "+ Add owner requirement",
      addForContractors: "+ Add service provider requirement",
      edit: "Edit",
      addError: "Could not add requirement.",
      updateError: "Could not update requirement.",
      removeError: "Could not remove requirement.",
    },
  },
};

export const ar: Dictionary = {
  common: {
    loading: "جارٍ التحميل…",
    save: "حفظ",
    cancel: "إلغاء",
    back: "رجوع",
  },
  brand: {
    tagline: "المخططات تدخل، والعروض تخرج.",
  },
  home: {
    login: "تسجيل الدخول",
    signup: "إنشاء حساب",
    statOpen: "مناقصات مفتوحة",
    statVerified: "مزوّدو خدمات موثقون",
    statAwarded: "مشاريع تمت ترسيتها",
    stepsLabel: "ما الذي ستفعله",
    afterLabel: "بعد التسجيل",
    costLabel: "التكلفة",
    optional: "اختياري",
    noDocuments: "لا توجد مستندات مطلوبة حاليًا.",
  },
  pricing: {
    monthly: "شهري",
    annual: "سنوي",
    perMonth: "/ شهر",
    perYear: "/ سنة",
    unavailable: "تُعرض أسعار الاشتراك في صفحة الاشتراك قبل الدفع.",
  },
  header: {
    logOut: "تسجيل الخروج",
    account: "الحساب",
  },
  language: {
    label: "اللغة",
    en: "English",
    ar: "العربية",
  },
  auth: {
    login: {
      heading: "تسجيل الدخول",
      email: "البريد الإلكتروني",
      password: "كلمة المرور",
      submit: "تسجيل الدخول",
      submitting: "جارٍ تسجيل الدخول…",
      noAccount: "ليس لديك حساب؟",
      signupLink: "إنشاء حساب",
      forgotPassword: "نسيت كلمة المرور؟",
      genericError: "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
    },
    signup: {
      heading: "إنشاء حساب",
      iAmA: "أنا...",
      propertyOwner: "مالك",
      contractor: "مزوّد خدمة",
      chooseRole: "اختر مالك أو مزوّد خدمة للمتابعة.",
      companyName: "اسم الشركة",
      companyNameHint: "ستقوم بتقديم مستندات التحقق بعد إنشاء الحساب.",
      fullName: "الاسم الكامل",
      email: "البريد الإلكتروني",
      password: "كلمة المرور",
      submit: "إنشاء الحساب",
      submitting: "جارٍ الإنشاء…",
      haveAccount: "لديك حساب بالفعل؟",
      loginLink: "تسجيل الدخول",
      genericError: "تعذر إنشاء الحساب.",
    },
    forgotPassword: {
      heading: "إعادة تعيين كلمة المرور",
      description: "أدخل البريد الإلكتروني لحسابك، وسنرسل لك رابطًا لإعادة تعيين كلمة المرور.",
      email: "البريد الإلكتروني",
      submit: "إرسال رابط إعادة التعيين",
      submitting: "جارٍ الإرسال…",
      sent: "إذا كان هناك حساب مرتبط بهذا البريد الإلكتروني، فسيتم إرسال رابط إعادة التعيين إليه.",
      backToLogin: "العودة إلى تسجيل الدخول",
    },
    resetPassword: {
      heading: "اختر كلمة مرور جديدة",
      newPassword: "كلمة المرور الجديدة",
      submit: "إعادة تعيين كلمة المرور",
      submitting: "جارٍ إعادة التعيين…",
      success: "تم إعادة تعيين كلمة المرور بنجاح. يمكنك الآن تسجيل الدخول.",
      invalidToken: "رابط إعادة التعيين غير صالح أو منتهي الصلاحية.",
      goToLogin: "الذهاب إلى تسجيل الدخول",
      requestNew: "طلب رابط جديد لإعادة التعيين",
      missingToken: "لم يتم توفير رمز إعادة التعيين.",
    },
    verifyEmail: {
      heading: "جارٍ التحقق من بريدك الإلكتروني…",
      success: "تم التحقق من بريدك الإلكتروني بنجاح.",
      invalidToken: "رابط التحقق غير صالح أو منتهي الصلاحية.",
      continue: "متابعة",
      missingToken: "لم يتم توفير رمز التحقق.",
    },
    changePassword: {
      heading: "تغيير كلمة المرور",
      currentPassword: "كلمة المرور الحالية",
      newPassword: "كلمة المرور الجديدة",
      submit: "تغيير كلمة المرور",
      submitting: "جارٍ التغيير…",
      success: "تم تغيير كلمة المرور.",
    },
    emailVerifyBanner: {
      message: "يرجى تأكيد بريدك الإلكتروني.",
      resend: "إعادة إرسال رسالة التحقق",
      sent: "تم إرسال رسالة التحقق.",
    },
  },
  clarifications: {
    heading: "الأسئلة والأجوبة",
    noQuestions: "لا توجد أسئلة بعد.",
    sealedBidder: "مزوّد خدمة مغفل الهوية",
    privateTag: "خاص",
    writeAnswerPlaceholder: "اكتب إجابة…",
    answerButton: "إجابة",
    awaitingAnswer: "بانتظار إجابة من المالك.",
    shareCheckboxLabel: "مشاركة هذا السؤال والجواب مع مزوّدي الخدمات الآخرين بعد الإجابة عليه",
    askPlaceholder: "اطرح سؤالاً على المالك حول هذا المشروع…",
    askButton: "إرسال السؤال",
    askError: "تعذر إرسال سؤالك.",
    answerError: "تعذر إرسال إجابتك.",
  },
  contractor: {
    roleLabel: "مزوّد خدمة",
    dashboard: {
      kpiActiveBids: "العروض النشطة",
      kpiProjectsWon: "المشاريع الفائزة",
      kpiTotalBids: "إجمالي العروض المقدمة",
      myBids: "عروضي",
      browseOpenProjects: "تصفح المشاريع المفتوحة",
      noBidsYetPrefix: "لم تقدم أي عروض بعد.",
      banner: {
        documentsIncompleteTitle: "أكمل التحقق من شركتك",
        documentsIncompleteBody: "قم برفع مستنداتك ليتمكن أحد المسؤولين من مراجعة حسابك.",
        documentsIncompleteCta: "متابعة التحقق",
        submittedTitle: "الطلب قيد المراجعة",
        submittedBody: "يقوم أحد المسؤولين بمراجعة مستنداتك. سنُعلمك فور اتخاذ القرار.",
        submittedCta: "عرض الطلب المُقدَّم",
        changesRequestedTitle: "تم طلب تعديلات",
        changesRequestedBody: "يجب إعادة رفع مستند واحد أو أكثر قبل الموافقة على حسابك.",
        changesRequestedCta: "مراجعة وإعادة الرفع",
        paymentRequiredTitle: "اشترك لفتح إمكانية تقديم العروض",
        paymentRequiredBody: "تم التحقق من حسابك — اشترك لعرض المخططات وتقديم العروض.",
        paymentRequiredCta: "عرض الباقات",
        paymentRestrictedTitle: "مشكلة في الدفع على حسابك",
        paymentRestrictedBody: "فشلت عملية دفع اشتراكك أو أنها متأخرة. حدّث بيانات الفوترة لمواصلة تقديم العروض.",
        paymentRestrictedCta: "إدارة الفوترة",
        suspendedTitle: "الحساب موقوف",
        suspendedBody: "تم إيقاف حسابك من قبل مسؤول الموقع. تواصل مع الدعم إذا كنت تعتقد أن هذا خطأ.",
      },
    },
    feed: {
      eyebrow: "مزوّد خدمة · المشاريع المفتوحة",
      heading: "مشاريع مفتوحة لتقديم العروض",
      sortedNewest: "مرتبة حسب الأحدث نشرًا.",
      sortedClosest: "مرتبة حسب الأقرب إغلاقًا.",
      subscribeBanner: "تمت الموافقة عليك، لكن المخططات والعروض تبقى مقفلة حتى تشترك.",
      viewPlans: "عرض الباقات",
      searchPlaceholder: "ابحث بالعنوان أو الموقع أو نطاق العمل…",
      allTrades: "كل التخصصات",
      sortClosest: "الأقرب إغلاقًا",
      sortNewest: "الأحدث أولاً",
      noMatch: "لا توجد مشاريع مطابقة لعوامل التصفية.",
      noOpenProjects: "لا توجد مشاريع مفتوحة حاليًا. تحقق مرة أخرى قريبًا.",
      deadline: "الموعد النهائي",
      offersSoFar: "العروض حتى الآن",
      trade: "التخصص",
      bidPlaced: "تم تقديم العرض",
      lockedTitle: "اشترك لعرض المخططات",
      lockedDescription: "افتح المخططات الكاملة وتفاصيل نطاق العمل والقدرة على تقديم العروض.",
    },
    status: {
      suspendedTitle: "الحساب موقوف",
      suspendedBody:
        "تم إيقاف حسابك من قبل مسؤول الموقع. لا يمكنك عرض مشاريع جديدة أو تقديم عروض أثناء الإيقاف. تواصل مع الدعم إذا كنت تعتقد أن هذا خطأ.",
      approvedTitle: "تمت الموافقة عليك",
      approvedBody: "توجه إلى لوحة التحكم لتصفح المشاريع المفتوحة.",
      eyebrow: "مزوّد خدمة · التحقق من الحساب",
      heading: "حالة الطلب",
      changesRequestedTitle: "تم طلب تعديلات — يجب إعادة رفع مستند واحد أو أكثر",
      underReviewTitle: "الطلب قيد المراجعة",
      submittedOn: "تاريخ التقديم",
      pending: "قيد الانتظار",
      actionNeeded: "يتطلب إجراء",
      document: "المستند",
      statusCol: "الحالة",
      required: "مطلوب",
      optional: "اختياري",
      adminNote: "ملاحظة المسؤول:",
      reupload: "إعادة الرفع",
      upload: "رفع",
      footerNote:
        "سيتم إعلامك بمجرد الموافقة الكاملة على حسابك. يبقى الوصول الكامل إلى المخططات والعروض مقفلاً حتى ذلك الحين.",
    },
    verify: {
      eyebrow: "مزوّد خدمة · التحقق من الحساب",
      heading: "تحقق من شركتك",
      description: "قدّم المستندات أدناه ليتمكن مسؤول الموقع من تفعيل حسابك.",
      companyName: "اسم الشركة",
      licenseNumber: "رقم الترخيص",
      document: "المستند",
      statusCol: "الحالة",
      required: "مطلوب",
      optional: "اختياري",
      submitting: "جارٍ الإرسال…",
      submit: "إرسال للمراجعة",
      uploadError: "تعذر رفع المستند.",
      submitError: "تعذر الإرسال للمراجعة.",
    },
    subscribe: {
      feature1: "مشاريع مفتوحة غير محدودة في منطقة خدمتك",
      feature2: "مخططات كاملة وتفاصيل نطاق العمل لكل إعلان",
      feature3: "عروض ومراجعات غير محدودة قبل الموعد النهائي",
      feature4: "ملف تقييمات ومراجعات عام",
      save: "وفّر {percent}٪",
      priceMonthlyNote: "تُفوتَر شهريًا. بلا رسوم عمولات إضافية.",
      priceAnnualNote: "تُفوتَر سنويًا بمبلغ {amount}. بلا رسوم عمولات إضافية.",
      start: "بدء الاشتراك",
      eyebrow: "وصول مزوّد الخدمة",
      headingActive: "اشتراكك",
      headingInactive: "اشترك لتقديم العروض على المشاريع",
      subheadingActive: "أدر باقتك وتفاصيل الفوترة.",
      subheadingInactive: "باقة واحدة، وصول كامل. يمكن الإلغاء في أي وقت.",
      overrideBadge: "استثناء إداري",
      overrideMessage: "منحك أحد المسؤولين وصولاً كاملاً للسوق دون اشتراك مدفوع.",
      renews: "يتجدد في",
      manageBilling: "إدارة الفوترة",
      checkoutNote: "سيتم تحويلك إلى صفحة الدفع الآمنة الخاصة بـ Stripe لإتمام اشتراكك.",
      checkoutError: "تعذر بدء عملية الدفع. حاول مرة أخرى.",
      portalError: "تعذر فتح بوابة الفوترة. حاول مرة أخرى.",
    },
    offer: {
      deadlineLabel: "الموعد النهائي",
      closed: "مغلق",
      scope: "نطاق العمل",
      drawings: "المخططات",
      downloadZip: "تنزيل الكل كملف .zip",
      noDrawings: "لم يتم رفع أي مخططات لهذا المشروع.",
      biddingClosedNotice: "أُغلق تقديم العروض على هذا المشروع.",
      yourFinalOffer: "عرضك النهائي:",
      awardedTo: "تم الترسية على",
      anotherContractor: "مزوّد خدمة آخر",
      noAwardNotice: "قرر المالك عدم ترسية هذا المشروع.",
      bidAmount: "قيمة عرضك (دولار أمريكي)",
      timeline: "الجدول الزمني المتوقع",
      timelinePlaceholder: "مثال: 3 أسابيع من بدء العمل",
      messageToOwner: "رسالة إلى المالك",
      messagePlaceholder: "اشرح منهجك ومواد العمل وأي تفاصيل لا تغطيها المخططات.",
      updateOffer: "تحديث العرض",
      submitOffer: "تقديم العرض",
      withdraw: "سحب العرض",
      withdrawing: "جارٍ السحب…",
      tipsHeading: "نصائح للفوز بالعروض",
      tip1: "أشر إلى تفاصيل محددة من المخططات — فهذا يدل على أنك راجعتها بعناية.",
      tip2: "يمكن للمالكين رؤية تقييمك ومراجعاتك السابقة بجانب عرضك.",
      tip3: "يمكنك تعديل عرضك في أي وقت قبل الموعد النهائي.",
      withdrawError: "تعذر سحب العرض.",
      submitError: "تعذر تقديم العرض.",
      notAvailableNotice: "هذا المشروع غير متاح لك حاليًا.",
    },
  },
  owner: {
    roleLabel: "مالك",
    dashboard: {
      statusAll: "كل الحالات",
      statusDraft: "مسودة",
      statusOpen: "مفتوح",
      statusAwaitingReview: "بانتظار المراجعة",
      statusUnderEvaluation: "قيد التقييم",
      statusAwarded: "تمت الترسية",
      statusNoAward: "بلا ترسية",
      statusCanceled: "ملغى",
      statusExpired: "منتهي الصلاحية",
      eyebrow: "لوحة تحكم المالك",
      heading: "مشاريعك",
      newProject: "+ مشروع جديد",
      kpiOpen: "مفتوح",
      kpiAwaitingReview: "بانتظار المراجعة",
      kpiUnderEvaluation: "قيد التقييم",
      kpiAwarded: "تمت الترسية",
      kpiTotalOffers: "إجمالي العروض",
      emptyStatePrefix: "لم تنشر أي مشروع بعد.",
      emptyStateLink: "انشر أول مشروع لك",
      emptyStateSuffix: "لتبدأ باستقبال العروض.",
      searchPlaceholder: "ابحث بالعنوان أو الموقع…",
      allTenderTypes: "كل أنواع العطاءات",
      sealed: "مغلق (سري)",
      ownerVisible: "مرئي للمالك",
      noMatch: "لا توجد مشاريع مطابقة لعوامل التصفية.",
      nothingHere: "لا يوجد شيء هنا.",
      offersReceived: "عرض/عروض مستلمة",
      readyToReview: "جاهز للمراجعة",
      deadline: "الموعد النهائي",
      trade: "التخصص",
      posted: "تاريخ النشر",
    },
    projectNew: {
      eyebrow: "مشروع جديد",
      heading: "انشر مشروعًا",
      description: "أضف مخططاتك وحدّد موعدًا نهائيًا — لا يمكن لمزوّدي الخدمات تقديم عروض إلا قبل إغلاقه.",
      tenderType: "نوع العطاء",
      ownerVisibleToggle: "مرئي للمالك",
      sealedToggle: "مغلق (سري)",
      ownerVisibleHint: "يمكنك رؤية العروض فور ورودها. يُثبَّت النوع بمجرد وصول أول عرض.",
      sealedHint: "تبقى العروض مخفية عنك حتى يُغلق تقديم العروض. يُثبَّت النوع بمجرد وصول أول عرض.",
      title: "عنوان المشروع",
      titlePlaceholder: "مثال: دوبلكس شارع مابل — استبدال السقف",
      address: "عنوان الموقع",
      addressPlaceholder: "الشارع، المدينة، المنطقة",
      trade: "التخصص",
      tradePlaceholder: "مثال: أسقف، هياكل، أسوار",
      scope: "نطاق العمل",
      scopePlaceholder: "صف العمل المطلوب. سيستخدم مزوّدو الخدمات هذا الوصف مع مخططاتك لتسعير عروضهم.",
      drawings: "المخططات",
      drawingsHint: "PDF أو DWG أو JPG أو PNG أو ملف .zip للمخططات — حتى 50 ميغابايت إجمالاً",
      drawingsAccessNote: "فقط مزوّدو الخدمات المعتمدون والمشتركون يمكنهم عرض هذه الملفات.",
      deadline: "الموعد النهائي لتقديم العروض",
      deadlineNote: "لا تُقبل العروض بعد هذا الوقت.",
      postProject: "نشر المشروع",
      posting: "جارٍ النشر…",
      saveAsDraft: "حفظ كمسودة",
      draftNote: "المسودة مرئية لك فقط. يمكنك نشرها لاحقًا من صفحة المشروع عندما تكون جاهزًا لاستقبال العروض.",
      sidebarHeading: "قبل أن تنشر",
      tip1: "المخططات الواضحة تُنتج عروضًا أدق — أضف الأبعاد قدر الإمكان.",
      tip2: "امنح مزوّدي الخدمات 5 إلى 7 أيام على الأقل لتسعير العمل بشكل صحيح.",
      tip3: "لن يتم تحصيل أي رسوم منك. نشر المشاريع ومراجعة العروض مجاني لملاك العقارات.",
      validationError: "العنوان والموقع والموعد النهائي حقول مطلوبة.",
      submitError: "تعذر إنشاء المشروع.",
    },
    projectDetail: {
      reviewOffers: "مراجعة العروض",
      sealedBadge: "مغلق (سري)",
      ownerVisibleBadge: "مرئي للمالك",
      publish: "نشر — بدء استقبال العروض",
      closeEarly: "إغلاق تقديم العروض مبكرًا",
      startEvaluation: "بدء التقييم",
      markNoAward: "وضع علامة بلا ترسية",
      cancelProject: "إلغاء المشروع",
      noDrawings: "لم يتم رفع أي مخططات بعد",
      downloadZip: "تنزيل الكل كملف .zip",
      hideHistory: "إخفاء سجل المراجعات",
      viewHistory: "عرض سجل المراجعات",
      noHistory: "لا يوجد سجل مراجعات بعد.",
      current: "(الحالي)",
      view: "عرض",
      addDrawings: "إضافة مخططات",
      zipHint: "يمكنك أيضًا رفع ملف .zip يحتوي على المخططات.",
      scope: "نطاق العمل",
      lowestBid: "أقل عرض",
      averageBid: "متوسط العروض",
      highestBid: "أعلى عرض",
      sealedBidsReceived: "عرض/عروض سرية مستلمة",
      sealedExplanation:
        "هذا عطاء مغلق (سري) — تبقى هويات مزوّدي الخدمات وقيم عروضهم مخفية عنك حتى يُغلق تقديم العروض. أغلق تقديم العروض لكشفها وتقييمها.",
      noOffersYet: "لا توجد عروض بعد. يمكن لمزوّدي الخدمات تقديم عروض حتى الموعد النهائي أعلاه.",
      contractorCol: "مزوّد الخدمة",
      ratingCol: "التقييم",
      bidCol: "العرض",
      timelineCol: "الجدول الزمني",
      revisedSuffix: "مُعدَّل ×",
      approve: "قبول",
      closeToAwardHint: "أغلق تقديم العروض للترسية",
      rateContractor: "قيّم",
      theContractor: "مزوّد الخدمة",
      submittedOn: "تاريخ التقديم",
      ratingPlaceholder: "كيف سار العمل؟ اختياري، لكنه يساعد الملاك الآخرين.",
      submitReview: "إرسال التقييم",
      approveError: "تعذر قبول هذا العرض.",
      drawingsError: "تعذر إضافة المخططات.",
      reviewError: "تعذر إرسال التقييم.",
      statusError: "تعذر تحديث حالة هذا المشروع.",
    },
    verify: {
      eyebrow: "مالك · التحقق من الحساب",
      heading: "تحقق من حسابك",
      description: "قدّم المستندات أدناه ليتمكن مسؤول الموقع من تفعيل حسابك.",
      document: "المستند",
      statusCol: "الحالة",
      required: "مطلوب",
      optional: "اختياري",
      submitting: "جارٍ الإرسال…",
      submit: "إرسال للمراجعة",
      uploadError: "تعذر رفع المستند.",
      submitError: "تعذر الإرسال للمراجعة.",
    },
    status: {
      suspendedTitle: "الحساب موقوف",
      suspendedBody:
        "تم إيقاف حسابك من قبل مسؤول الموقع. لا يمكنك نشر أو إدارة المشاريع أثناء الإيقاف. تواصل مع الدعم إذا كنت تعتقد أن هذا خطأ.",
      approvedTitle: "تمت الموافقة عليك",
      approvedBody: "توجه إلى لوحة التحكم لنشر مشروع.",
      eyebrow: "مالك · التحقق من الحساب",
      heading: "حالة الطلب",
      changesRequestedTitle: "تم طلب تعديلات — يجب إعادة رفع مستند واحد أو أكثر",
      underReviewTitle: "الطلب قيد المراجعة",
      submittedOn: "تاريخ التقديم",
      pending: "قيد الانتظار",
      actionNeeded: "يتطلب إجراء",
      document: "المستند",
      statusCol: "الحالة",
      required: "مطلوب",
      optional: "اختياري",
      adminNote: "ملاحظة المسؤول:",
      reupload: "إعادة الرفع",
      upload: "رفع",
      footerNote:
        "سيتم إعلامك بمجرد الموافقة الكاملة على حسابك. يبقى نشر المشاريع وإدارتها مقفلاً حتى ذلك الحين.",
    },
  },
  admin: {
    nav: {
      requirements: "متطلبات المستندات",
      review: "مراجعة الطلبات",
      contractors: "جميع مزوّدي الخدمات",
      owners: "جميع الملاك",
      offers: "جميع العروض",
      projects: "جميع المشاريع",
      cms: "محتوى الموقع",
    },
    owners: {
      eyebrow: "المسؤول · الملاك",
      heading: "جميع ملاك العقارات",
      total: "الإجمالي",
      empty: "لم يسجل أي مالك بعد.",
      name: "الاسم",
      status: "الحالة",
      projects: "المشاريع",
      manage: "إدارة",
    },
    ownerDetail: {
      docReviewError: "تعذر تحديث هذا المستند.",
      approveError: "تعذر قبول هذا المالك.",
      rejectError: "تعذر طلب التعديلات.",
      suspendError: "تعذر تحديث صلاحية الوصول للحساب.",
      deleteError: "تعذر حذف هذا المالك.",
      suspended: "موقوف",
      documentsHeading: "مستندات التحقق",
      document: "المستند",
      statusCol: "الحالة",
      approve: "قبول",
      reject: "رفض",
      applicationHeading: "الطلب",
      currentStatus: "الحالة الحالية",
      approveApplication: "الموافقة على المالك",
      requestChanges: "طلب تعديلات",
      accessHeading: "الوصول إلى الحساب",
      reactivate: "إعادة تفعيل الحساب",
      suspend: "إيقاف الحساب",
      suspendedNote: "لا يمكن لهذا المالك نشر أو إدارة المشاريع حتى تتم إعادة التفعيل.",
      suspendNote: "يمنع المالك فورًا من نشر أو إدارة المشاريع، دون حذف أي شيء.",
      dangerZone: "منطقة الخطر",
      deleteBlockedNote:
        "قام هذا المالك بنشر مشاريع. أوقف الحساب بدلاً من حذفه، للحفاظ على سجل المشاريع والعروض سليماً لمزوّدي الخدمات المعنيين.",
      deleteNote: "لا يملك هذا المالك أي مشاريع بعد، لذا فإن الحذف يزيل الحساب بالكامل. لا يمكن التراجع عن هذا.",
      deleteConfirm: "هل تريد حذف حساب هذا المالك نهائيًا؟ لا يمكن التراجع عن هذا.",
      deleteAccount: "حذف الحساب",
      projectsHeading: "المشاريع المنشورة",
      noProjects: "لم ينشر هذا المالك أي مشاريع بعد.",
      projectTitleCol: "المشروع",
      projectStatusCol: "الحالة",
      projectOffersCol: "العروض",
      viewProject: "عرض",
    },
    offers: {
      eyebrow: "المسؤول · العروض",
      heading: "جميع العروض",
      total: "الإجمالي",
      empty: "لم يتم تقديم أي عروض بعد.",
      project: "المشروع",
      contractor: "مزوّد الخدمة",
      amount: "القيمة",
      status: "الحالة",
      tenderType: "نوع العطاء",
      submitted: "تاريخ التقديم",
      revised: "مُعدَّل",
      suspendedBadge: "العرض موقوف",
      viewProject: "عرض المشروع كاملاً",
    },
    projects: {
      eyebrow: "المسؤول · المشاريع",
      heading: "جميع المشاريع",
      total: "الإجمالي",
      empty: "لم يُنشر أي مشروع بعد.",
      owner: "المالك",
      title: "المشروع",
      status: "الحالة",
      offers: "العروض",
      suspendedBadge: "موقوف",
      manage: "إدارة",
    },
    projectDetail: {
      eyebrow: "المسؤول · المشاريع",
      suspended: "موقوف",
      editHeading: "تفاصيل المشروع",
      titleLabel: "العنوان",
      addressLabel: "العنوان الجغرافي",
      descriptionLabel: "نطاق العمل",
      tradeLabel: "التخصص",
      deadlineLabel: "الموعد النهائي للعروض",
      saveChanges: "حفظ التغييرات",
      saveError: "تعذر حفظ التغييرات.",
      accessHeading: "الظهور في السوق",
      reactivate: "إعادة تفعيل المشروع",
      suspend: "إيقاف المشروع",
      suspendedNote: "هذا المشروع مخفي عن قائمة مزوّدي الخدمات ولا يمكنه استقبال عروض جديدة حتى تتم إعادة التفعيل.",
      suspendNote: "يخفي هذا المشروع فورًا عن قائمة مزوّدي الخدمات ويمنع العروض الجديدة، دون حذف أي شيء.",
      suspendError: "تعذر تحديث ظهور المشروع.",
      dangerZone: "منطقة الخطر",
      deleteBlockedNote:
        "يحتوي هذا المشروع على عروض. أوقفه بدلاً من حذفه، للحفاظ على سجل العروض سليماً لمزوّدي الخدمات المعنيين.",
      deleteNote: "لا يحتوي هذا المشروع على أي عروض بعد، لذا فإن الحذف يزيله بالكامل. لا يمكن التراجع عن هذا.",
      deleteConfirm: "هل تريد حذف هذا المشروع نهائيًا؟ لا يمكن التراجع عن هذا.",
      deleteProject: "حذف المشروع",
      deleteError: "تعذر حذف هذا المشروع.",
      offersHeading: "العروض على هذا المشروع",
      noOffers: "لم يتم تقديم أي عروض على هذا المشروع.",
      contractorCol: "مزوّد الخدمة",
      amountCol: "القيمة",
      timelineCol: "الجدول الزمني",
      statusCol: "الحالة",
      actionsCol: "",
      edit: "تعديل",
      editOfferHeading: "تعديل العرض",
      amountFieldLabel: "القيمة (بالدولار)",
      timelineFieldLabel: "الجدول الزمني",
      messageFieldLabel: "الرسالة",
      saveOffer: "حفظ",
      cancel: "إلغاء",
      editOfferError: "تعذر حفظ هذا العرض.",
      suspendOffer: "إيقاف",
      reactivateOffer: "إعادة تفعيل",
      suspendOfferError: "تعذر تحديث هذا العرض.",
      deleteOffer: "حذف",
      deleteOfferError: "تعذر حذف هذا العرض.",
      deleteOfferConfirm: "هل تريد حذف هذا العرض نهائيًا؟ لا يمكن التراجع عن هذا.",
      deleteOfferBlocked: "تمت ترسية هذا العرض — أوقفه بدلاً من حذفه.",
      offerSuspendedBadge: "العرض موقوف",
    },
    requirements: {
      eyebrow: "المسؤول · متطلبات المستندات",
      heading: "المستندات المطلوبة",
      description:
        "فعّل أو عطّل المتطلبات، أو أزل أحدها نهائيًا. تُطبَّق التغييرات على الطلبات الجديدة فورًا — الحسابات التي تمت الموافقة عليها سابقًا لا تتأثر.",
      forContractors: "لمزوّدي الخدمات",
      forOwners: "للملاك",
      emptyForScope: "لا توجد متطلبات مُعدة لهذه المجموعة بعد.",
      toggleRequiredFor: "تبديل حالة الإلزام لـ",
      required: "مطلوب",
      optional: "اختياري",
      removeTitle: "إزالة المتطلب",
      namePlaceholder: "اسم المستند، مثال: الهوية المدنية",
      descriptionPlaceholder: "وصف مختصر يظهر لمقدم الطلب",
      addForOwners: "+ إضافة متطلب للملاك",
      addForContractors: "+ إضافة متطلب لمزوّدي الخدمات",
      edit: "تعديل",
      addError: "تعذر إضافة المتطلب.",
      updateError: "تعذر تحديث المتطلب.",
      removeError: "تعذر إزالة المتطلب.",
    },
  },
};
