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
  services: {
    heading: string;
    hint: string;
    categories: string;
    governorates: string;
    allKuwait: string;
    noCategories: string;
    save: string;
    saved: string;
    saveError: string;
  };
  categoryPicker: {
    choose: string;
    none: string;
  };
  tenderRules: {
    heading: string;
    hint: string;
    offersClose: string;
    offersCloseHint: string;
    visibility: string;
    ownerVisible: string;
    sealed: string;
    questions: string;
    questionsAllowed: string;
    questionsUntil: string;
    questionsUntilHint: string;
    commercialTerms: string;
    commercialTermsHint: string;
    instructions: string;
    instructionsHint: string;
    save: string;
    saved: string;
    saveError: string;
    providerHeading: string;
    pOffersClose: string;
    pRevise: string;
    pSealed: string;
    pOwnerVisible: string;
    pQuestionsUntil: string;
    pQuestionsClosed: string;
    pNoQuestions: string;
    pDeclarations: string;
    pCommercial: string;
    pInstructions: string;
    offerValidity: string;
    paymentStages: string;
    paymentStagesHint: string;
    milestone: string;
    percent: string;
    addStage: string;
    remove: string;
    stagesTotal: string;
    retention: string;
    retentionPercent: string;
    retentionMonths: string;
    warranty: string;
    otherConditions: string;
    pValidity: string;
    pPayment: string;
    pRetention: string;
    pWarranty: string;
    pOther: string;
  };
  organization: {
    heading: string;
    hint: string;
    representative: string;
    member: string;
    remove: string;
    removeConfirm: string;
    email: string;
    emailPlaceholder: string;
    position: string;
    add: string;
    addHint: string;
    error: string;
    invite: string;
    inviteHint: string;
    inviteSent: string;
    pending: string;
    expires: string;
    withdraw: string;
  };
  quality: {
    ready: string;
    readyHint: string;
    notReady: string;
    notReadyHint: string;
    warningsHeading: string;
    section_details: string;
    section_dates: string;
    section_rules: string;
    section_items: string;
    section_response: string;
    section_eligibility: string;
    section_documents: string;
    title_too_short: string;
    scope_missing: string;
    scope_brief: string;
    type_missing: string;
    type_unlisted: string;
    address_missing: string;
    governorate_missing: string;
    area_missing: string;
    deadline_passed: string;
    deadline_soon: string;
    timing_missing: string;
    questions_deadline_passed: string;
    per_item_without_items: string;
    item_unit_missing: string;
    item_quantity_missing: string;
    eligibility_category_missing: string;
    eligibility_governorate_missing: string;
    qualification_retired: string;
    documents_missing: string;
    publishBlocked: string;
    documents_required_missing: string;
  };
  invite: {
    heading: string;
    body: string;
    someone: string;
    expires: string;
    accept: string;
    signUp: string;
    logIn: string;
    wrongAccount: string;
    invalid: string;
    acceptError: string;
  };
  preview: {
    heading: string;
    draftNote: string;
    liveNote: string;
    back: string;
    inList: string;
    inListHint: string;
    opened: string;
    openedHint: string;
    thenForm: string;
    open: string;
    audienceHeading: string;
    audienceCount: string;
    excluded_organization_only: string;
    excluded_qualification_missing: string;
    excluded_qualification_expired: string;
    excluded_category_not_offered: string;
    excluded_governorate_not_served: string;
    audienceNone: string;
    audienceNote: string;
  };
  confirm: {
    cancel: string;
    remove: string;
  };
  participate: {
    heading: string;
    body: string;
    button: string;
    notNow: string;
    error: string;
    changedHeading: string;
    changedBody: string;
    reviewed: string;
    preparingHeading: string;
    changedShort: string;
    preparingFor: string;
    reviewFirst: string;
    draftStatus: string;
    draftStarted: string;
    lastSaved: string;
  };
  offerHistory: {
    yourOffer: string;
    readOnlyNote: string;
    earlier: string;
  };
  submitOffer: {
    confirmTitle: string;
    confirmBody: string;
    submitted: string;
    submittedAt: string;
    revision: string;
    sealedNote: string;
    visibleNote: string;
    canStill: string;
    reviseTitle: string;
    reviseBody: string;
    docsOnUpdate: string;
    withdrawTitle: string;
    withdrawBody: string;
    withdrawnAt: string;
    withdrawnNote: string;
    resubmit: string;
  };
  offerPreview: {
    open: string;
    heading: string;
    backToEdit: string;
    notSubmitted: string;
    passed: string;
    fix: string;
    requirement: string;
    version: string;
    amendment: string;
    outdated: string;
    scope: string;
    from: string;
    total: string;
    unknownItems: string;
    notProvided: string;
    loading: string;
    unavailable: string;
  };
  readiness: {
    ready: string;
    notReady: string;
    recheck: string;
    savedOnly: string;
    section_requirement: string;
    section_account: string;
    section_eligibility: string;
    section_price: string;
    section_technical: string;
    section_timing: string;
    section_documents: string;
    section_declarations: string;
    section_offer: string;
  };
  timing: {
    heading: string;
    ownerExpects: string;
    start: string;
    completion: string;
    duration: string;
    durationDays: string;
    days: string;
    hint: string;
    conflict_starts_later: string;
    conflict_finishes_later: string;
    conflict_takes_longer: string;
  };
  saved: {
    save: string;
    saved: string;
    unsave: string;
    saveForLater: string;
    heading: string;
    intro: string;
    backToFeed: string;
    empty: string;
    unavailable: string;
    remove: string;
  };
  detail: {
    addedAfter: string;
    needsAccess: string;
    kuwaitTime: string;
  };
  feed: {
    pricing: string;
    items: string;
    loadMore: string;
    loading: string;
    hiddenIneligible: string;
    checkServices: string;
    lump_sum: string;
    per_item: string;
    timeLeft: string;
    anyTimeLeft: string;
    atLeastDays: string;
    sortBy: string;
    sortLatest: string;
    sortedLatest: string;
    myServices: string;
    myAreas: string;
    acceptingNow: string;
    clear: string;
    sortRelevance: string;
    sortedRelevance: string;
    closedNow: string;
    leftDays: string;
    leftHours: string;
    documents: string;
    published: string;
    sealed: string;
    sealedHint: string;
    whoCanRespond: string;
    youQualify: string;
    offer_withdrawn: string;
    offer_draft: string;
    offer_approved: string;
    offer_rejected: string;
  };
  versions: {
    version: string;
    before: string;
    yourOfferVersion: string;
    pricedOn: string;
    from: string;
    until: string;
    current: string;
    incomplete: string;
    documents: string;
    replacedSince: string;
    docsAdded: string;
    docsReplaced: string;
    yes: string;
    no: string;
    field_title: string;
    field_address: string;
    field_governorate: string;
    field_area: string;
    field_trade: string;
    field_description: string;
    field_bid_deadline: string;
    field_expected_start_date: string;
    field_expected_completion_date: string;
    field_expected_duration_days: string;
    field_documents_required: string;
  };
  closure: {
    open: string;
    heading: string;
    hint: string;
    note: string;
    noteHint: string;
    cancelHeading: string;
    reason_not_needed: string;
    reason_postponed: string;
    reason_other: string;
    cancel: string;
    cancelConfirm: string;
    cancelConfirmBody: string;
    externalHeading: string;
    externalHint: string;
    external: string;
    externalConfirm: string;
    externalConfirmBody: string;
    noSuitableHeading: string;
    noSuitableHint: string;
    noSuitable: string;
    noSuitableConfirm: string;
    noSuitableConfirmBody: string;
    error: string;
    labelCanceled: string;
    labelExpired: string;
    labelExternal: string;
    labelNoSuitable: string;
    textCanceled: string;
    textExpired: string;
    textExternal: string;
    textNoSuitable: string;
    offersKept: string;
    dismiss: string;
    yourNote: string;
    restart: string;
    restartConfirm: string;
    restartConfirmBody: string;
    restartedFrom: string;
    restartedFromLink: string;
    adminSuspended: string;
    labelSuspended: string;
  };
  postPub: {
    pause: string;
    pauseReason: string;
    pauseHint: string;
    pausedSince: string;
    pausedDeadline: string;
    resume: string;
    resumeConfirm: string;
    amendHeading: string;
    amendHint: string;
    address: string;
    area: string;
    reason: string;
    amendSave: string;
    savedMaterial: string;
    savedMinor: string;
    changesHeading: string;
    material: string;
    outdatedHeading: string;
    outdatedBody: string;
    confirmOffer: string;
    outdatedOwner: string;
    pausedProvider: string;
    pausedProviderBody: string;
    closedEarly: string;
    closeConfirm: string;
    closeConfirmBody: string;
    error: string;
    pausedPill: string;
  };
  eligibility: {
    heading: string;
    hint: string;
    providerType: string;
    anyProvider: string;
    organizationOnly: string;
    qualificationsHeading: string;
    qualificationsHint: string;
    noQualifications: string;
    save: string;
    saved: string;
    saveError: string;
    openToAll: string;
    notEligible: string;
    notEligibleIntro: string;
    backToFeed: string;
    rulesLine: string;
    reason_organization_only: string;
    reason_qualification_missing: string;
    reason_qualification_expired: string;
    reason_category_not_offered: string;
    reason_governorate_not_served: string;
    matchCategory: string;
    matchCategoryUnavailable: string;
    matchGovernorate: string;
    matchGovernorateUnavailable: string;
    matchingHeading: string;
    fixServices: string;
    addQualification: string;
    notForYou: string;
    youCanFix: string;
    canParticipate: string;
    ended: string;
    unavailable: string;
    verificationNeeded: string;
  };
  response: {
    heading: string;
    hint: string;
    completionPeriod: string;
    approach: string;
    required: string;
    optional: string;
    documentsHeading: string;
    documentsHint: string;
    documentName: string;
    addDocument: string;
    remove: string;
    declarationsHeading: string;
    declarationsHint: string;
    declarationText: string;
    addDeclaration: string;
    save: string;
    saved: string;
    saveError: string;
    whatToSubmit: string;
    priceTotal: string;
    pricePerItem: string;
    rateCol: string;
    saveDraft: string;
    unsaved: string;
    approachGuide: string;
    assumptionsGuide: string;
    draftSaved: string;
    saveDraftError: string;
    lineTotalCol: string;
    total: string;
    amount: string;
    assumptions: string;
    assumptionsPlaceholder: string;
    attachments: string;
    upload: string;
    replace: string;
    uploadError: string;
    declarations: string;
    requiredMark: string;
    noDocuments: string;
    itemBreakdown: string;
    declarationsConfirmed: string;
    details: string;
  };
  dates: {
    heading: string;
    responseHeading: string;
    responseHint: string;
    workHeading: string;
    workHint: string;
    start: string;
    finishBy: string;
    completion: string;
    duration: string;
    durationOr: string;
    save: string;
    saved: string;
    saveError: string;
    pastDeadline: string;
    work: string;
    from: string;
    until: string;
    days: string;
  };
  documents: {
    drawing: string;
    boq: string;
    specification: string;
    photo: string;
    site: string;
    other: string;
    typeLabel: string;
    essential: string;
    supplementary: string;
    essentialToggle: string;
    remove: string;
    removeConfirm: string;
    uploadHint: string;
    heading: string;
    saveError: string;
    neededToPrice: string;
    neededToPriceHint: string;
  };
  location: {
    governorate: string;
    chooseGovernorate: string;
    allGovernorates: string;
    capital: string;
    hawalli: string;
    farwaniya: string;
    mubarak_al_kabeer: string;
    ahmadi: string;
    jahra: string;
    area: string;
    areaHint: string;
    address: string;
    addressHint: string;
    siteNotesHint: string;
    notSpecified: string;
  };
  requirementItems: {
    heading: string;
    intro: string;
    basisLabel: string;
    lump_sum: string;
    lump_sum_hint: string;
    per_item: string;
    per_item_hint: string;
    item: string;
    quantity: string;
    unit: string;
    specification: string;
    specificationPlaceholder: string;
    addItem: string;
    remove: string;
    noItems: string;
    save: string;
    saved: string;
    saveError: string;
    providerHeading: string;
    provider_lump_sum: string;
    provider_per_item: string;
    notSpecified: string;
  };
  draftDetails: {
    heading: string;
    intro: string;
    title: string;
    titleHint: string;
    category: string;
    categoryHint: string;
    location: string;
    locationHint: string;
    scopeHeading: string;
    scopeIntro: string;
    scopeTopics: string;
    insertOutline: string;
    outline: string;
    charCount: string;
    save: string;
    saving: string;
    saved: string;
    saveError: string;
    notSet: string;
    lastSaved: string;
    discard: string;
    discardConfirm: string;
    discarded: string;
    resumeHeading: string;
    resumeHint: string;
    untitled: string;
    lastSavedShort: string;
    expired: string;
    publishConfirm: string;
    publishNowConfirm: string;
    published: string;
  };
  verification: {
    scopeLabel: string;
    scopeAll: string;
    scopeIndividual: string;
    scopeOrganization: string;
    requiresExpiry: string;
    expiryBadge: string;
    state_not_started: string;
    state_incomplete: string;
    state_submitted: string;
    state_under_review: string;
    state_correction_required: string;
    state_approved: string;
    state_rejected: string;
    stateLabel: string;
    correctionNeeded: string;
    reviewerMessage: string;
    rejectedBody: string;
    locked: string;
    replace: string;
    noRequirements: string;
    addLaterHint: string;
  };
  stakeholder: {
    heading: string;
    intro: string;
    individual_owner: string;
    individual_owner_hint: string;
    organization_owner: string;
    organization_owner_hint: string;
    individual_service_provider: string;
    individual_service_provider_hint: string;
    organization_service_provider: string;
    organization_service_provider_hint: string;
    legalName: string;
    position: string;
    positionPlaceholder: string;
    authorized: string;
    save: string;
    saving: string;
    change: string;
    saveError: string;
    actingAs: string;
    typeIndividual: string;
    typeOrganization: string;
    representative: string;
    member: string;
    yourRole: string;
    locked: string;
    mustEstablish: string;
    notEstablished: string;
    accountCreated: string;
    established: string;
    verified: string;
    eligible: string;
    adminHeading: string;
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
      service_provider: string;
      chooseRole: string;
      signingUpAs: string;
      changeRole: string;
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
    closesAt: string;
    closedAt: string;
    unansweredClosed: string;
    yourQuestion: string;
    answeredOn: string;
    cameWithChange: string;
    publishForAll: string;
    materialHint: string;
    becauseOf: string;
    notBecauseOf: string;
    attachFiles: string;
  };
  service_provider: {
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
      anotherServiceProvider: string;
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
      serviceProviderCol: string;
      ratingCol: string;
      bidCol: string;
      timelineCol: string;
      revisedSuffix: string;
      approve: string;
      closeToAwardHint: string;
      rateServiceProvider: string;
      theServiceProvider: string;
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
      service_providers: string;
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
      service_provider: string;
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
      serviceProviderCol: string;
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
      forServiceProviders: string;
      forOwners: string;
      emptyForScope: string;
      toggleRequiredFor: string;
      required: string;
      optional: string;
      removeTitle: string;
      namePlaceholder: string;
      descriptionPlaceholder: string;
      addForOwners: string;
      addForServiceProviders: string;
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
  services: {
    heading: "Your services",
    hint: "Tell owners what you do and where. Some requirements are open only to providers who offer that type of work or serve that governorate. You can change this at any time.",
    categories: "Types of work you offer",
    governorates: "Governorates you serve",
    allKuwait: "Leave all unticked if you serve all of Kuwait.",
    noCategories: "The platform has no service categories yet.",
    save: "Save services",
    saved: "Saved",
    saveError: "Could not save your services.",
  },
  categoryPicker: {
    choose: "Choose a type of work",
    none: "Not specified",
  },
  tenderRules: {
    heading: "Offer & question rules",
    hint: "How this opportunity is run — kept apart from what you're asking for. Providers see these rules before they respond.",
    offersClose: "Offers close",
    offersCloseHint: "Set under Dates. Offers, changes and withdrawals are refused after this moment.",
    visibility: "Who sees offers, and when",
    ownerVisible: "I see each offer as it arrives",
    sealed: "Sealed — I see offers only after offers close",
    questions: "Questions from providers",
    questionsAllowed: "Providers may ask questions",
    questionsUntil: "Questions close at (optional)",
    questionsUntilHint: "Leave blank to take questions until offers close. At the cut-off, questions and answers both close. In your local time.",
    commercialTerms: "Commercial conditions",
    commercialTermsHint: "Only what applies, e.g. payment stages, retention, warranty, how long prices must stay valid.",
    instructions: "Instructions for providers",
    instructionsHint: "Anything providers must know or do before responding, e.g. site-visit arrangements.",
    save: "Save rules",
    saved: "Saved",
    saveError: "Could not save the rules.",
    providerHeading: "Rules for this opportunity",
    pOffersClose: "Offers close {date}. After that, offers can't be submitted, changed or withdrawn.",
    pRevise: "Until then you can revise or withdraw your offer. Every revision is recorded.",
    pSealed: "Sealed: the owner sees offers only after offers close.",
    pOwnerVisible: "The owner sees each offer as it arrives.",
    pQuestionsUntil: "Questions are accepted until {date}.",
    pQuestionsClosed: "Questions are closed.",
    pNoQuestions: "This requirement doesn't accept questions.",
    pDeclarations: "Before submitting, you must confirm the owner's declarations ({count}).",
    pCommercial: "Commercial conditions",
    pInstructions: "Instructions",
    offerValidity: "Offer validity (days after offers close)",
    paymentStages: "Payment stages",
    paymentStagesHint: "How you will pay, e.g. 30% on mobilisation, 60% on progress, 10% on handover. Must add up to 100%.",
    milestone: "Milestone",
    percent: "%",
    addStage: "Add stage",
    remove: "Remove",
    stagesTotal: "Total {total}%",
    retention: "Retention",
    retentionPercent: "% held",
    retentionMonths: "for (months)",
    warranty: "Warranty / defects liability (months from handover)",
    otherConditions: "Other conditions",
    pValidity: "Prices must stay valid for {days} days after offers close.",
    pPayment: "Payment:",
    pRetention: "Retention: {percent}% held for {months} months.",
    pWarranty: "Warranty: {months} months from handover.",
    pOther: "Other conditions",
  },
  organization: {
    heading: "Organization members",
    hint: "Everyone here acts for the organization and shares everything done for it: its verification, requirements, offers and questions.",
    representative: "Authorized representative",
    member: "Member",
    remove: "Remove",
    removeConfirm: "Remove this member? They will no longer act for the organization. Everything they worked on stays with the organization.",
    email: "Colleague's email",
    emailPlaceholder: "colleague@company.com",
    position: "Position (optional)",
    add: "Add member",
    addHint: "Your colleague signs up for their own account first. They then act for the organization; they don't need to verify separately.",
    error: "Could not update the members.",
    invite: "Send invitation",
    inviteHint: "We email them a link. They accept it after signing in (or signing up) with that email, and then act for the organization — no separate verification. You can also share the link yourself.",
    inviteSent: "Invitation sent. You can also share this link (for example on WhatsApp); it only works for that email:",
    pending: "Invitations waiting to be accepted",
    expires: "link valid until {date}",
    withdraw: "Withdraw",
  },
  quality: {
    ready: "Ready for preview",
    readyHint: "Nothing essential is missing. Look over any suggestions below, then preview and publish when you're ready — nothing is published until you do.",
    notReady: "{count} thing(s) to fix before publishing",
    notReadyHint: "Providers couldn't understand or price this requirement yet. Each item says what is missing and where to fix it.",
    warningsHeading: "Suggestions (won't stop you publishing)",
    section_details: "Fix in Details",
    section_dates: "Fix in Dates",
    section_rules: "Fix in Offer & question rules",
    section_items: "Fix in What to price",
    section_response: "Fix in What providers must submit",
    section_eligibility: "Fix in Who can respond",
    section_documents: "Add documents",
    title_too_short: "Give the requirement a title that says what the work is (at least 5 characters).",
    scope_missing: "Describe the work: what needs doing, where on the site and to what standard. A provider can't price a requirement without it.",
    scope_brief: "The scope is very brief. Providers price more accurately when they know exactly what's included and what isn't.",
    type_missing: "Choose the type of work, so the right providers find it.",
    type_unlisted: "The type of work isn't one of the platform's categories, so providers filtering by category won't find it.",
    address_missing: "Give the site address or a description of where the site is.",
    governorate_missing: "Choose the governorate, so providers can judge travel and whether they cover the area.",
    area_missing: "Add the area (e.g. Salwa), so providers can judge the location without the exact address.",
    deadline_passed: "Set an offer deadline in the future.",
    deadline_soon: "Offers close in under 3 days. Providers may not have time to visit the site and price properly.",
    timing_missing: "Say roughly when the work should happen (a start date or a duration), so providers can check their availability.",
    questions_deadline_passed: "The question deadline has passed: move it later, or remove it to take questions until offers close.",
    per_item_without_items: "The requirement is priced per item but lists no items. Add the items, or price it as one total.",
    item_unit_missing: "Item {position} has a quantity but no unit.",
    item_quantity_missing: "Item {position} has no quantity, so providers will price it as a lump sum.",
    eligibility_category_missing: "Who can respond depends on the type of work, but none from the platform's list is chosen.",
    eligibility_governorate_missing: "Who can respond depends on the governorate, but none is chosen.",
    qualification_retired: "A required qualification is no longer on the platform's list. Choose again under Who can respond.",
    documents_missing: "No drawings, BOQ or photos are attached. For detailed work, providers usually need them to price accurately.",
    publishBlocked: "Fix the items above before publishing.",
    documents_required_missing: "You said providers need the documents to price this, but none are uploaded. Upload them, or untick that option.",
  },
  invite: {
    heading: "Join {organization} on U-Tender",
    body: "{inviter} invited {email} to act for {organization}: to work on its requirements or offers together with colleagues.",
    someone: "Someone",
    expires: "This invitation is valid until {date}.",
    accept: "Join {organization}",
    signUp: "Sign up with this email",
    logIn: "Log in",
    wrongAccount: "You're signed in with a different account. Log out and sign in as {email} to accept.",
    invalid: "This invitation link is invalid, has expired or was withdrawn. Ask for a new one.",
    acceptError: "Could not accept the invitation.",
  },
  preview: {
    heading: "Provider preview",
    draftNote: "This is how verified providers who may respond will see your requirement once you publish it. It is not published: only you and your organization can see it.",
    liveNote: "This is how providers who may respond see your requirement.",
    back: "Back to the draft",
    inList: "In the list of opportunities",
    inListHint: "Before opening it, providers see only this: not the exact address, scope or documents.",
    opened: "When a provider opens it",
    openedHint: "What an eligible provider sees, with the exact address, scope, items, documents and rules.",
    thenForm: "Below this, providers fill in their offer: the price (per item if you asked for it) and everything listed under \"What your offer must include\".",
    open: "Preview as a provider",
    audienceHeading: "Who this reaches",
    audienceCount: "{eligible} of the {total} verified providers on U-Tender meet your \"who can respond\" rules today.",
    excluded_organization_only: "{count} are registered as individuals (you asked for organizations only)",
    excluded_qualification_missing: "{count} don't hold a required qualification",
    excluded_qualification_expired: "{count} hold a required qualification that has expired",
    excluded_category_not_offered: "{count} don't list this type of work among their services",
    excluded_governorate_not_served: "{count} don't serve this governorate",
    audienceNone: "No provider meets these rules right now. Consider relaxing them under Who can respond.",
    audienceNote: "Counts only; providers who qualify later will be able to respond too.",
  },
  confirm: {
    cancel: "Cancel",
    remove: "Remove",
  },
  participate: {
    heading: "Decided to take part?",
    body: "Start preparing your offer. Nothing is sent to the owner until you submit it, and you can stop at any time before then.",
    button: "Participate — prepare an offer",
    notNow: "Not for you? You don’t need to do anything. Save it if you want to decide later.",
    error: "Couldn’t start preparing an offer.",
    changedHeading: "The requirement changed after you decided to take part",
    changedBody: "Review the changes above: the current requirement is the one your offer will be made against.",
    reviewed: "I’ve reviewed the current requirement",
    preparingHeading: "Preparing an offer",
    changedShort: "changed since you started",
    preparingFor: "You are preparing an offer for",
    reviewFirst: "Confirm you’ve reviewed the current requirement to continue preparing your offer.",
    draftStatus: "Draft — not submitted. Nothing is sent to the owner until you submit it.",
    draftStarted: "started",
    lastSaved: "last saved",
  },
  offerHistory: {
    yourOffer: "Your offer",
    readOnlyNote: "Your offer as it stands. Offers have closed, so it can no longer be changed.",
    earlier: "Earlier versions",
  },
  submitOffer: {
    confirmTitle: "Submit this offer?",
    confirmBody: "Your saved offer is sent to the owner exactly as the preview shows it. Until offers close you can still update or withdraw it, and every change is recorded.",
    submitted: "Offer submitted",
    submittedAt: "Submitted",
    revision: "revision",
    sealedNote: "This tender is sealed: the owner sees your offer's content only after the deadline.",
    visibleNote: "The owner can see your offer now.",
    canStill: "Until offers close you can update or withdraw it.",
    reviseTitle: "Update your submitted offer?",
    reviseBody: "This version replaces your current offer for the owner. The previous version stays in your offer’s history, as submitted.",
    docsOnUpdate: "Document changes go to the owner when you update your offer; until then the owner has the documents you submitted.",
    withdrawTitle: "Withdraw your offer?",
    withdrawBody: "The owner will no longer have an offer from you to consider. Your offer and its history are kept, and you can submit again while offers are open.",
    withdrawnAt: "Withdrawn",
    withdrawnNote: "The owner has no offer from you to consider. You can submit again while offers are open; your earlier versions stay in the history.",
    resubmit: "Submit again",
  },
  offerPreview: {
    open: "Preview offer",
    heading: "Preview of your offer",
    backToEdit: "Back to edit",
    notSubmitted: "This is your saved draft, exactly as it would be sent to the owner. It has not been submitted. Save any changes first to see them here.",
    passed: "Passed the current checks — ready to submit",
    fix: "Go to section",
    requirement: "Responding to",
    version: "Requirement version",
    amendment: "amendment",
    outdated: "The requirement changed after you started this offer. Review the current requirement before submitting.",
    scope: "Scope of work",
    from: "From",
    total: "Total price:",
    unknownItems: "Some prices refer to items no longer in this requirement.",
    notProvided: "Not provided",
    loading: "Loading preview…",
    unavailable: "This offer can’t be previewed right now.",
  },
  readiness: {
    ready: "Ready to submit",
    notReady: "Cannot submit yet",
    recheck: "Check again",
    savedOnly: "This checks your saved draft — save first. Submitting checks everything again.",
    section_requirement: "Requirement",
    section_account: "Your account",
    section_eligibility: "Eligibility",
    section_price: "Price",
    section_technical: "Technical approach",
    section_timing: "Timing",
    section_documents: "Documents",
    section_declarations: "Declarations",
    section_offer: "Offer",
  },
  timing: {
    heading: "Your start and completion commitment",
    ownerExpects: "The owner expects:",
    start: "Start",
    completion: "Completion",
    duration: "Duration",
    durationDays: "Or duration (days)",
    days: "days",
    hint: "Give a completion date or a duration, not both. Work can’t start or finish before offers close.",
    conflict_starts_later: "You propose to start after the owner’s expected start date.",
    conflict_finishes_later: "You propose to finish after the owner’s expected completion.",
    conflict_takes_longer: "You propose more days than the owner’s expected duration.",
  },
  saved: {
    save: "Save",
    saved: "Saved",
    unsave: "Remove from saved",
    saveForLater: "Save for later",
    heading: "Saved opportunities",
    intro: "Opportunities you marked to come back to, as they stand now. Still open first.",
    backToFeed: "Back to all opportunities",
    empty: "Nothing saved yet. Use Save on an opportunity to keep it here.",
    unavailable: "An opportunity you saved is temporarily unavailable.",
    remove: "Remove",
  },
  detail: {
    addedAfter: "Added after publishing · {date}",
    needsAccess: "You meet this opportunity’s conditions. Activate your marketplace access to read the full requirement, open its documents and send an offer.",
    kuwaitTime: "Kuwait time",
  },
  feed: {
    pricing: "Priced as",
    items: "{n} items",
    loadMore: "Show more opportunities",
    loading: "Loading…",
    hiddenIneligible: "{n} open requirement(s) aren’t shown because their conditions (provider type, qualifications, type of work or area) don’t match your account.",
    checkServices: "Check the services and areas you declared",
    lump_sum: "One total",
    per_item: "Per item",
    timeLeft: "Time left to respond",
    anyTimeLeft: "Any time left",
    atLeastDays: "At least {n} days left",
    sortBy: "Sort",
    sortLatest: "Closing latest",
    sortedLatest: "Open opportunities, closing latest first",
    myServices: "My types of work",
    myAreas: "My service areas",
    acceptingNow: "Accepting offers now",
    clear: "Clear search and filters",
    sortRelevance: "Best match to search",
    sortedRelevance: "Open opportunities, best match to your search first",
    closedNow: "Offers closed",
    leftDays: "{d} d {h} h left to respond",
    leftHours: "{h} h left to respond",
    documents: "{n} documents",
    published: "Published {date}",
    sealed: "Sealed offers",
    sealedHint: "Offers stay sealed: the owner sees prices only after the deadline.",
    whoCanRespond: "Who can respond:",
    youQualify: "you meet these",
    offer_withdrawn: "Offer withdrawn",
    offer_draft: "Offer in progress",
    offer_approved: "Awarded",
    offer_rejected: "Not selected",
  },
  versions: {
    version: "Version {n}",
    before: "See the requirement as it was before (version {n})",
    yourOfferVersion: "See the requirement your offer was priced on (version {n})",
    pricedOn: "Priced on version {n}",
    from: "from {date}",
    until: "until {date}",
    current: "current",
    incomplete: "Some earlier details weren’t kept for changes made before version history was recorded; they show as they are now.",
    documents: "Documents in this version:",
    replacedSince: "replaced since",
    docsAdded: "Documents added:",
    docsReplaced: "Documents replaced:",
    yes: "Yes",
    no: "No",
    field_title: "Title",
    field_address: "Location",
    field_governorate: "Governorate",
    field_area: "Area",
    field_trade: "Type of work",
    field_description: "Scope of work",
    field_bid_deadline: "Offers close",
    field_expected_start_date: "Expected start",
    field_expected_completion_date: "Expected completion",
    field_expected_duration_days: "Expected duration (days)",
    field_documents_required: "Documents needed to price",
  },
  closure: {
    open: "End this requirement…",
    heading: "End this requirement",
    hint: "Each of these ends the requirement for good: no new offers, and it can't be reopened. Offers already submitted stay on record. Nothing here awards the work.",
    note: "Private note (optional)",
    noteHint: "Kept in your records only; providers don't see it.",
    cancelHeading: "Cancel — it won't go ahead in this form",
    reason_not_needed: "The work is no longer needed.",
    reason_postponed: "The work is postponed.",
    reason_other: "Other reason.",
    cancel: "Cancel requirement",
    cancelConfirm: "Cancel this requirement?",
    cancelConfirmBody: "Providers who responded are told it was canceled and why (the reason above, not your note). It can't be reopened.",
    externalHeading: "Closed outside U-Tender",
    externalHint: "You've arranged the work another way. Nothing is awarded on U-Tender, and no provider is recorded as having won.",
    external: "Close — handled outside U-Tender",
    externalConfirm: "Close this requirement as handled outside U-Tender?",
    externalConfirmBody: "No offer is accepted. Providers who responded are told it was closed without an award through U-Tender. It can't be reopened.",
    noSuitableHeading: "None of the offers is suitable",
    noSuitableHint: "End it without accepting any offer.",
    noSuitable: "End — no suitable offer",
    noSuitableConfirm: "End without accepting any offer?",
    noSuitableConfirmBody: "No offer is accepted and nothing is awarded. Providers who responded are told. It can't be reopened.",
    error: "Couldn't end the requirement.",
    labelCanceled: "Canceled",
    labelExpired: "Expired",
    labelExternal: "Closed outside U-Tender",
    labelNoSuitable: "No award",
    textCanceled: "The owner canceled this requirement; it won't go ahead in this form.",
    textExpired: "The response period ended without any offers.",
    textExternal: "The owner closed this requirement and arranged the work outside U-Tender. No offer was accepted through U-Tender.",
    textNoSuitable: "The owner ended this requirement without accepting any offer.",
    offersKept: "Offers submitted stay on record. This requirement has ended and won't reopen.",
    dismiss: "Keep it as it is",
    yourNote: "Your private note:",
    restart: "Start a new draft from this",
    restartConfirm: "Start a new draft from this requirement?",
    restartConfirmBody: "A new draft is created with this requirement’s description, items, rules, eligibility and current documents. Set a new deadline, check it, then publish it as a new requirement. This one stays as it ended, with its offers.",
    restartedFrom: "Started again from an ended requirement:",
    restartedFromLink: "see the original",
    adminSuspended: "Suspended by U-Tender: hidden from providers and not accepting offers, questions or changes to offers until reactivated. Contact support if you think this is a mistake.",
    labelSuspended: "Suspended by U-Tender",
  },
  postPub: {
    pause: "Pause this requirement",
    pauseReason: "Why are you pausing it? Providers will see this.",
    pauseHint: "While paused, no offers, changes, withdrawals or questions are accepted. Existing offers are kept. The offer deadline keeps running: extend it if the pause will last longer.",
    pausedSince: "Paused since {date}",
    pausedDeadline: "Offers close {date} unless you extend the deadline.",
    resume: "Resume",
    resumeConfirm: "Resume the requirement? Offers will be accepted again until {date}.",
    amendHeading: "Change the published requirement",
    amendHint: "Providers may already be pricing this. Every change is recorded as a numbered amendment and the bidders are told.\nChanges to the scope, location or work timing (and documents you add) change what providers price: their existing offers are flagged so they confirm or revise them, and at least 3 days must remain before offers close. A title correction or more time is not.\nItems, response requirements, who can respond and the tender rules can't change after publication.",
    address: "Site address",
    area: "Area",
    reason: "Reason for the change (shown to providers)",
    amendSave: "Save change",
    savedMaterial: "Saved as an amendment that changes what providers price. Bidders were told and asked to confirm or revise their offers.",
    savedMinor: "Saved as an amendment. Bidders were told; their offers stay as they are.",
    changesHeading: "Changes since publication",
    material: "Changes pricing",
    outdatedHeading: "The requirement changed after your offer",
    outdatedBody: "Review the changes listed above. If your offer still stands as it is, confirm it; otherwise revise it below.",
    confirmOffer: "My offer still stands — confirm it",
    outdatedOwner: "Made before amendment — not yet confirmed",
    pausedProvider: "Paused by the owner since {date}",
    pausedProviderBody: "No offers, changes or questions are accepted until it resumes. Offers already made are kept.",
    closedEarly: "Closed for offers on {date}.",
    closeConfirm: "Close this requirement for offers now?",
    closeConfirmBody: "No more offers will be accepted. All offers received are kept as submitted; awarding is a separate step.",
    error: "Could not complete this.",
    pausedPill: "Paused",
  },
  eligibility: {
    heading: "Who can respond",
    hint: "Every provider must already be verified by U-Tender. Narrow it further only if the work genuinely needs it — each restriction reduces the offers you receive.",
    providerType: "Provider type",
    anyProvider: "Any verified provider (individual or organization)",
    organizationOnly: "Registered organizations only",
    qualificationsHeading: "Required qualifications",
    qualificationsHint: "Providers must hold these documents, approved by U-Tender and not expired. The list is managed by the platform.",
    noQualifications: "The platform has no provider qualifications to choose from yet.",
    save: "Save eligibility",
    saved: "Saved",
    saveError: "Could not save eligibility.",
    openToAll: "Open to every verified provider.",
    notEligible: "Not eligible to respond",
    notEligibleIntro: "You can't respond to this requirement:",
    backToFeed: "Back to available projects",
    rulesLine: "Who can respond",
    reason_organization_only: "This requirement is open to registered organizations only; your account is registered as an individual.",
    reason_qualification_missing: "This requirement needs a U-Tender-approved \"{name}\". You can add it from your verification page.",
    reason_qualification_expired: "This requirement needs a valid \"{name}\"; yours expired on {date}.",
    reason_category_not_offered: "This requirement is for \"{name}\", which isn't among the services on your profile.",
    reason_governorate_not_served: "This requirement is in {governorate}, which isn't among the governorates your profile says you serve.",
    matchCategory: "Only providers who offer this type of work ({category})",
    matchCategoryUnavailable: "Choose the type of work from the platform's list to use this.",
    matchGovernorate: "Only providers who serve {governorate}",
    matchGovernorateUnavailable: "Set the governorate to use this.",
    matchingHeading: "Type of work and location",
    fixServices: "Update your services",
    addQualification: "Add a qualification",
    notForYou: "This opportunity’s conditions — not something you can change:",
    youCanFix: "You can put these right, if they are true of your business:",
    canParticipate: "You can take part in this opportunity.",
    ended: "This opportunity is no longer accepting offers.",
    unavailable: "This opportunity is temporarily unavailable.",
    verificationNeeded: "Complete your verification to take part in opportunities.",
  },
  response: {
    heading: "What providers must submit",
    hint: "Every offer includes a price in {currency}. Choose what else a complete offer must contain. Offers missing a required part are refused.",
    completionPeriod: "Completion period",
    approach: "Technical approach / method",
    required: "Required",
    optional: "Optional",
    documentsHeading: "Documents to attach",
    documentsHint: "e.g. Method statement, Programme, Trade licence copy.",
    documentName: "Document name",
    addDocument: "Add document",
    remove: "Remove",
    declarationsHeading: "Declarations providers must confirm",
    declarationsHint: "Short statements each provider must tick, e.g. \"I have visited the site.\"",
    declarationText: "Declaration",
    addDeclaration: "Add declaration",
    save: "Save response requirements",
    saved: "Saved",
    saveError: "Could not save the response requirements.",
    whatToSubmit: "What your offer must include",
    priceTotal: "Total price in {currency}",
    pricePerItem: "A rate in {currency} for every item listed",
    rateCol: "Rate ({currency})",
    saveDraft: "Save draft",
    unsaved: "Unsaved changes",
    approachGuide: "Explain how your offer meets the item specifications and the instructions to bidders shown above.",
    assumptionsGuide: "State what your price or programme depends on (access, items the owner provides), what is excluded, and any departure from the specification that needs the owner’s acceptance. The owner receives these with your offer. To ask about the requirement itself, use Questions & answers.",
    draftSaved: "Draft saved — not submitted.",
    saveDraftError: "Couldn’t save your draft.",
    lineTotalCol: "Line total",
    total: "Total",
    amount: "Your total price ({currency})",
    assumptions: "Assumptions, exclusions & clarifications",
    assumptionsPlaceholder: "e.g. Excludes dewatering; client provides water and power on site.",
    attachments: "Supporting documents",
    upload: "Upload",
    replace: "Replace",
    uploadError: "Could not upload the document.",
    declarations: "Declarations",
    requiredMark: "required",
    noDocuments: "No documents attached.",
    itemBreakdown: "Price breakdown",
    declarationsConfirmed: "All declarations confirmed",
    details: "Response details",
  },
  dates: {
    heading: "Dates",
    responseHeading: "Offer deadline",
    responseHint: "When service providers must have submitted their offers. Offers are refused after this moment. In your local time.",
    workHeading: "Expected work timing",
    workHint: "When you expect the work itself to happen, so providers can check their availability. Optional; leave blank if it doesn't apply.",
    start: "Expected start",
    finishBy: "Finish by",
    completion: "Expected completion date",
    duration: "Duration (days)",
    durationOr: "or",
    save: "Save dates",
    saved: "Saved",
    saveError: "Could not save the dates.",
    pastDeadline: "This deadline has passed. Set a future one before publishing.",
    work: "Work",
    from: "from {date}",
    until: "until {date}",
    days: "{n} days",
  },
  documents: {
    drawing: "Drawing",
    boq: "BOQ",
    specification: "Specification",
    photo: "Photo",
    site: "Site document",
    other: "Other",
    typeLabel: "Document type",
    essential: "Essential for pricing",
    supplementary: "Supplementary",
    essentialToggle: "Providers need this to price the work",
    remove: "Remove",
    removeConfirm: "Remove this document and its earlier versions from the draft?",
    uploadHint: "PDF, DWG, Excel (.xlsx), Word (.docx), JPG/PNG, or a .zip of them, up to 50 MB per upload. Uploading a file with the same name replaces it as a new version.",
    heading: "Documents",
    saveError: "Could not update the document.",
    neededToPrice: "Providers need these documents to price this work",
    neededToPriceHint: "Tick this if the work can't be priced without the drawings, BOQ or photos. Publishing then needs at least one document.",
  },
  location: {
    governorate: "Governorate",
    chooseGovernorate: "Select governorate",
    allGovernorates: "All governorates",
    capital: "Capital (Al Asimah)",
    hawalli: "Hawalli",
    farwaniya: "Farwaniya",
    mubarak_al_kabeer: "Mubarak Al-Kabeer",
    ahmadi: "Ahmadi",
    jahra: "Jahra",
    area: "Area",
    areaHint: "The neighbourhood, e.g. Salmiya, Mishref, Fahaheel. Shown in listings with the governorate.",
    address: "Exact address or site description",
    addressHint: "Block, street, house or plot, landmarks or directions. Shown only to service providers who can open the full requirement, not in listings.",
    siteNotesHint: "Site access or conditions that affect the work (working hours, access for trucks, occupied building…) go in the scope of work, under \"Site & working conditions\".",
    notSpecified: "Location not specified",
  },
  requirementItems: {
    heading: "Quantities & pricing basis",
    intro: "What a service provider needs to calculate their price. List items only where the work is naturally measured; otherwise leave the list empty.",
    basisLabel: "Providers should price",
    lump_sum: "One total for the whole requirement",
    lump_sum_hint: "Any items below are for reference: they help the provider estimate one overall price.",
    per_item: "Each listed item separately",
    per_item_hint: "Providers give a price for every item below. List at least one.",
    item: "Item / work component",
    quantity: "Quantity",
    unit: "Unit",
    specification: "Specification & notes",
    specificationPlaceholder: "Specs, dimensions, standards, or anything that affects the price",
    addItem: "+ Add item",
    remove: "Remove",
    noItems: "No items. Fine for work that isn't naturally measured; the scope of work describes it.",
    save: "Save quantities & pricing",
    saved: "Saved",
    saveError: "Could not save the items.",
    providerHeading: "What to price",
    provider_lump_sum: "Give one total price for the complete requirement. Any items listed are there to help you estimate it.",
    provider_per_item: "Give a price for each item listed below.",
    notSpecified: "not specified",
  },
  draftDetails: {
    heading: "Requirement details",
    intro: "The basics a service provider sees first: what the work is and where. This draft is private until you publish it.",
    title: "Title",
    titleHint: "Short and specific, e.g. \"Villa extension — ground floor majlis\".",
    category: "Type of work",
    categoryHint: "The trade or service needed, e.g. Construction, MEP, Interior fit-out, Landscaping.",
    location: "Location",
    locationHint: "Governorate, area and block, e.g. \"Hawalli — Salmiya, Block 4\".",
    scopeHeading: "Scope of work",
    scopeIntro: "Describe the work you're asking a service provider to do, clearly enough for them to judge whether they can do it and how to price it.",
    scopeTopics: "Cover what applies to this job: the tasks, what must be delivered, specifications or standards, quantities, what is included and excluded, site conditions, and anything else they need to know. Skip what doesn't apply.",
    insertOutline: "Insert outline",
    outline: "Overview:\n\n\nWork / tasks required:\n- \n\nDeliverables:\n- \n\nSpecifications & standards:\n- \n\nQuantities / measurements:\n- \n\nIncluded:\n- \n\nExcluded (by owner or others):\n- \n\nSite & working conditions:\n- \n\nOther instructions:\n- ",
    charCount: "{count} / {max} characters",
    save: "Save draft",
    saving: "Saving…",
    saved: "Saved",
    saveError: "Could not save the draft.",
    notSet: "Not set",
    lastSaved: "Draft — last saved {date}. Only you can see it; nothing is published until you publish it.",
    discard: "Discard draft",
    discardConfirm: "Discard this draft? It will no longer be listed or editable, and it can't be published. This can't be undone.",
    discarded: "This draft was discarded on {date}. It is kept for your records but can no longer be edited or published.",
    resumeHeading: "You have drafts in progress",
    resumeHint: "Continue one instead of starting again:",
    untitled: "Untitled",
    lastSavedShort: "last saved {date}",
    expired: "This requirement expired at its offer deadline ({date}) without any offers. It is now read-only.",
    publishConfirm: "Publish \"{title}\" now?\n\nVerified providers who meet your \"who can respond\" rules will be able to find it, open it and send offers until {deadline}.\n\nOnce published, its rules and conditions can't be changed here.",
    publishNowConfirm: "Publish this requirement straight away, without saving it as a draft first?\n\nVerified providers will be able to find it and send offers until {deadline}. To review it as providers will see it first, save it as a draft and use Preview.",
    published: "Published {date} — open to offers until {deadline}.",
  },
  verification: {
    scopeLabel: "Applies to",
    scopeAll: "Individuals and organizations",
    scopeIndividual: "Individuals only",
    scopeOrganization: "Organizations only",
    requiresExpiry: "Expiry date required on approval",
    expiryBadge: "Expiry required",
    state_not_started: "Not started",
    state_incomplete: "In progress",
    state_submitted: "Submitted, awaiting review",
    state_under_review: "Under review",
    state_correction_required: "Correction required",
    state_approved: "Approved",
    state_rejected: "Rejected",
    stateLabel: "Verification",
    correctionNeeded: "Correction needed:",
    reviewerMessage: "Message from the reviewer:",
    rejectedBody: "Your verification was rejected. If you think this is a mistake, contact support.",
    locked: "Documents can't be changed while your verification is under review or after a decision.",
    replace: "Replace",
    noRequirements: "No documents are currently required for this account.",
    addLaterHint: "You're verified. You can add optional qualifications at any time — each is reviewed on its own and your access continues meanwhile.",
  },
  stakeholder: {
    heading: "Who does this account represent?",
    intro: "Your login is always you personally. Tell us whether you use U-Tender for yourself or on behalf of an organization: verification and everything you do on the platform are recorded under that identity.",
    individual_owner: "Myself",
    individual_owner_hint: "I'm a landowner, project owner or buyer acting personally.",
    organization_owner: "An organization",
    organization_owner_hint: "A company, government body or other organization I'm authorized to act for.",
    individual_service_provider: "Myself",
    individual_service_provider_hint: "I provide services as an individual or sole trader.",
    organization_service_provider: "A company",
    organization_service_provider_hint: "A contracting or service company I'm authorized to act for.",
    legalName: "Organization's legal name",
    position: "Your position (optional)",
    positionPlaceholder: "e.g. General Manager",
    authorized: "I confirm I'm authorized to act on behalf of this organization.",
    save: "Continue",
    saving: "Saving…",
    change: "Change",
    saveError: "Could not save. Try again.",
    actingAs: "Acting as",
    typeIndividual: "Individual",
    typeOrganization: "Organization",
    representative: "Authorized representative",
    member: "Member",
    yourRole: "Your role",
    locked: "This can't be changed while verification is under review or after it's approved.",
    mustEstablish: "Answer \"Who does this account represent?\" above before submitting for review.",
    notEstablished: "Not established yet",
    accountCreated: "Account created",
    established: "Identity established",
    verified: "Verified",
    eligible: "Eligible to participate",
    adminHeading: "Represents",
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
      service_provider: "Service provider",
      chooseRole: "Choose Owner or Service provider to continue.",
      signingUpAs: "Signing up as",
      changeRole: "Change",
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
    closesAt: "Questions and answers close {date}.",
    closedAt: "Questions and answers closed {date}. No new questions or answers.",
    unansweredClosed: "Not answered before the question cut-off.",
    yourQuestion: "Your question",
    answeredOn: "Answered {date}",
    cameWithChange: "This answer came with a change to the requirement (change #{n}) — see the changes above.",
    publishForAll: "Publish this question and answer to every provider (the asker stays anonymous)",
    materialHint: "If the answer changes the scope, quantities, documents, timing or who can respond, change the requirement itself too (Change the published requirement) and choose this question there.",
    becauseOf: "Because of a question (optional)",
    notBecauseOf: "Not because of a question",
    attachFiles: "Attach files (optional, up to 5: PDF, images, drawings, Excel, Word)",
  },
  service_provider: {
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
      searchPlaceholder: "Search title, area, type of work or scope…",
      allTrades: "All trades",
      sortClosest: "Closing soonest",
      sortNewest: "Newest first",
      noMatch: "No open opportunities match your search and filters.",
      noOpenProjects: "No opportunities you can respond to right now. New ones appear here as soon as they are published.",
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
      heading: "Verify your account",
      description: "Submit the documents below so a site admin can activate your account.",
      companyName: "Name shown to owners (trading name)",
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
      drawings: "Documents",
      downloadZip: "Download all as .zip",
      noDrawings: "No drawings were uploaded for this project.",
      biddingClosedNotice: "Bidding on this project has closed.",
      yourFinalOffer: "Your final offer:",
      awardedTo: "Awarded to",
      anotherServiceProvider: "another service provider",
      noAwardNotice: "The owner decided not to award this project.",
      bidAmount: "Your bid amount",
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
      drawings: "Drawings & documents",
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
      addDrawings: "Add documents",
      zipHint: "You can also upload a .zip folder of drawings.",
      scope: "Scope",
      lowestBid: "Lowest bid",
      averageBid: "Average bid",
      highestBid: "Highest bid",
      sealedBidsReceived: "sealed bid(s) received",
      sealedExplanation:
        "This is a sealed tender — bidder identities and amounts stay hidden from you until bidding closes. Close bidding to reveal and evaluate them.",
      noOffersYet: "No offers yet. Service providers can bid until the deadline above.",
      serviceProviderCol: "Service provider",
      ratingCol: "Rating",
      bidCol: "Bid",
      timelineCol: "Timeline",
      revisedSuffix: "revised x",
      approve: "Approve",
      closeToAwardHint: "Close bidding to award",
      rateServiceProvider: "Rate",
      theServiceProvider: "the service provider",
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
      service_providers: "All service providers",
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
      service_provider: "Service provider",
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
      serviceProviderCol: "Service provider",
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
      forServiceProviders: "For service providers",
      forOwners: "For owners",
      emptyForScope: "No requirements set up for this group yet.",
      toggleRequiredFor: "Toggle required for",
      required: "Required",
      optional: "Optional",
      removeTitle: "Remove requirement",
      namePlaceholder: "Document name, e.g. Civil ID",
      descriptionPlaceholder: "Short description shown to the applicant",
      addForOwners: "+ Add owner requirement",
      addForServiceProviders: "+ Add service provider requirement",
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
  services: {
    heading: "خدماتك",
    hint: "أخبر الملاك بما تقدمه وأين. بعض الطلبات متاحة فقط لمن يقدم نوع العمل المطلوب أو يخدم المحافظة المعنية. يمكنك التعديل في أي وقت.",
    categories: "أنواع الأعمال التي تقدمها",
    governorates: "المحافظات التي تخدمها",
    allKuwait: "اترك الكل دون تحديد إذا كنت تخدم كل الكويت.",
    noCategories: "لا توجد فئات خدمات على المنصة حتى الآن.",
    save: "حفظ الخدمات",
    saved: "تم الحفظ",
    saveError: "تعذر حفظ خدماتك.",
  },
  categoryPicker: {
    choose: "اختر نوع العمل",
    none: "غير محدد",
  },
  tenderRules: {
    heading: "قواعد العروض والأسئلة",
    hint: "طريقة إدارة هذه الفرصة — منفصلة عما تطلبه. يرى مقدمو الخدمة هذه القواعد قبل تقديم عروضهم.",
    offersClose: "موعد إغلاق العروض",
    offersCloseHint: "يُحدد في قسم التواريخ. تُرفض العروض والتعديلات والسحب بعد هذا الموعد.",
    visibility: "من يرى العروض ومتى",
    ownerVisible: "أرى كل عرض فور وصوله",
    sealed: "مختوم — أرى العروض بعد إغلاقها فقط",
    questions: "أسئلة مقدمي الخدمة",
    questionsAllowed: "يمكن لمقدمي الخدمة طرح الأسئلة",
    questionsUntil: "موعد إغلاق الأسئلة (اختياري)",
    questionsUntilHint: "اتركه فارغًا لاستقبال الأسئلة حتى إغلاق العروض. عند هذا الموعد تُغلق الأسئلة والأجوبة معًا. بتوقيتك المحلي.",
    commercialTerms: "الشروط التجارية",
    commercialTermsHint: "ما ينطبق فقط، مثل: مراحل الدفع، المحتجزات، الضمان، مدة صلاحية الأسعار.",
    instructions: "تعليمات لمقدمي الخدمة",
    instructionsHint: "أي شيء يجب أن يعرفه مقدم الخدمة أو يفعله قبل تقديم العرض، مثل ترتيبات زيارة الموقع.",
    save: "حفظ القواعد",
    saved: "تم الحفظ",
    saveError: "تعذر حفظ القواعد.",
    providerHeading: "قواعد هذه الفرصة",
    pOffersClose: "تُغلق العروض في {date}. بعد ذلك لا يمكن تقديم العروض أو تعديلها أو سحبها.",
    pRevise: "حتى ذلك الحين يمكنك تعديل عرضك أو سحبه. يُسجل كل تعديل.",
    pSealed: "مختوم: لا يرى المالك العروض إلا بعد إغلاقها.",
    pOwnerVisible: "يرى المالك كل عرض فور وصوله.",
    pQuestionsUntil: "تُقبل الأسئلة حتى {date}.",
    pQuestionsClosed: "باب الأسئلة مغلق.",
    pNoQuestions: "هذا الطلب لا يقبل الأسئلة.",
    pDeclarations: "قبل التقديم، يجب أن تؤكد إقرارات المالك ({count}).",
    pCommercial: "الشروط التجارية",
    pInstructions: "التعليمات",
    offerValidity: "صلاحية العرض (أيام بعد إغلاق العروض)",
    paymentStages: "مراحل الدفع",
    paymentStagesHint: "طريقة الدفع، مثل: 30% عند بدء الأعمال، 60% حسب الإنجاز، 10% عند التسليم. يجب أن يكون المجموع 100%.",
    milestone: "المرحلة",
    percent: "%",
    addStage: "إضافة مرحلة",
    remove: "إزالة",
    stagesTotal: "المجموع {total}%",
    retention: "المحتجزات",
    retentionPercent: "% محتجزة",
    retentionMonths: "لمدة (أشهر)",
    warranty: "الضمان / مسؤولية العيوب (أشهر من التسليم)",
    otherConditions: "شروط أخرى",
    pValidity: "يجب أن تبقى الأسعار سارية لمدة {days} يومًا بعد إغلاق العروض.",
    pPayment: "الدفع:",
    pRetention: "المحتجزات: {percent}% لمدة {months} شهرًا.",
    pWarranty: "الضمان: {months} شهرًا من التسليم.",
    pOther: "شروط أخرى",
  },
  organization: {
    heading: "أعضاء الجهة",
    hint: "كل من هنا يعمل باسم الجهة ويشارك كل ما يتم باسمها: توثيقها وطلباتها وعروضها وأسئلتها.",
    representative: "الممثل المفوض",
    member: "عضو",
    remove: "إزالة",
    removeConfirm: "هل تريد إزالة هذا العضو؟ لن يعمل باسم الجهة بعد ذلك، وكل ما عمل عليه يبقى للجهة.",
    email: "بريد الزميل",
    emailPlaceholder: "colleague@company.com",
    position: "المنصب (اختياري)",
    add: "إضافة عضو",
    addHint: "ينشئ زميلك حسابه الخاص أولًا، ثم يعمل باسم الجهة دون حاجة إلى توثيق منفصل.",
    error: "تعذر تحديث الأعضاء.",
    invite: "إرسال دعوة",
    inviteHint: "نرسل لهم رابطًا بالبريد. يقبلونه بعد تسجيل الدخول (أو التسجيل) بهذا البريد، ثم يعملون باسم الجهة دون توثيق منفصل. يمكنك أيضًا مشاركة الرابط بنفسك.",
    inviteSent: "تم إرسال الدعوة. يمكنك أيضًا مشاركة هذا الرابط (مثلًا عبر واتساب)؛ لا يعمل إلا لهذا البريد:",
    pending: "دعوات بانتظار القبول",
    expires: "الرابط صالح حتى {date}",
    withdraw: "سحب",
  },
  quality: {
    ready: "جاهز للمعاينة",
    readyHint: "لا ينقص شيء أساسي. راجع الاقتراحات أدناه، ثم عاين وانشر عندما تكون جاهزًا — لن يُنشر شيء حتى تقوم بذلك.",
    notReady: "{count} أمر(أمور) يجب إصلاحها قبل النشر",
    notReadyHint: "لا يستطيع مقدمو الخدمة فهم هذا الطلب أو تسعيره بعد. يوضح كل بند ما ينقص وأين يُصلح.",
    warningsHeading: "اقتراحات (لن تمنعك من النشر)",
    section_details: "أصلحه في التفاصيل",
    section_dates: "أصلحه في التواريخ",
    section_rules: "أصلحه في قواعد العروض والأسئلة",
    section_items: "أصلحه في ما يجب تسعيره",
    section_response: "أصلحه في ما يجب على مقدمي الخدمة تقديمه",
    section_eligibility: "أصلحه في من يمكنه تقديم عرض",
    section_documents: "إضافة مستندات",
    title_too_short: "أعطِ الطلب عنوانًا يوضح نوع العمل (5 أحرف على الأقل).",
    scope_missing: "صف العمل: ما المطلوب، وأين في الموقع، وبأي مستوى. لا يمكن لمقدم الخدمة تسعير طلب بدون ذلك.",
    scope_brief: "نطاق العمل مختصر جدًا. يسعّر مقدمو الخدمة بدقة أكبر عندما يعرفون ما يشمله العمل وما لا يشمله.",
    type_missing: "اختر نوع العمل ليجده مقدمو الخدمة المناسبون.",
    type_unlisted: "نوع العمل ليس من فئات المنصة، لذا لن يجده من يبحث حسب الفئة.",
    address_missing: "أدخل عنوان الموقع أو وصفًا لمكانه.",
    governorate_missing: "اختر المحافظة ليتمكن مقدمو الخدمة من تقدير التنقل وتغطية المنطقة.",
    area_missing: "أضف المنطقة (مثل سلوى) ليتمكن مقدمو الخدمة من تقدير الموقع دون العنوان الدقيق.",
    deadline_passed: "حدد موعدًا مستقبليًا لإغلاق العروض.",
    deadline_soon: "تُغلق العروض خلال أقل من 3 أيام. قد لا يتسع الوقت لزيارة الموقع والتسعير بشكل صحيح.",
    timing_missing: "حدد تقريبًا متى يجب أن يتم العمل (تاريخ بدء أو مدة) ليتحقق مقدمو الخدمة من توفرهم.",
    questions_deadline_passed: "انتهى موعد الأسئلة: أجّله، أو احذفه لاستقبال الأسئلة حتى إغلاق العروض.",
    per_item_without_items: "الطلب مسعّر حسب البنود لكنه لا يتضمن بنودًا. أضف البنود أو اجعله سعرًا إجماليًا واحدًا.",
    item_unit_missing: "البند {position} له كمية بدون وحدة.",
    item_quantity_missing: "البند {position} بدون كمية، لذا سيسعّره مقدمو الخدمة كمبلغ مقطوع.",
    eligibility_category_missing: "شرط من يمكنه تقديم عرض يعتمد على نوع العمل، لكن لم يُختر نوع من قائمة المنصة.",
    eligibility_governorate_missing: "شرط من يمكنه تقديم عرض يعتمد على المحافظة، لكن لم تُختر محافظة.",
    qualification_retired: "أحد المؤهلات المطلوبة لم يعد ضمن قائمة المنصة. اختر مجددًا في من يمكنه تقديم عرض.",
    documents_missing: "لا توجد مخططات أو جدول كميات أو صور. في الأعمال التفصيلية يحتاجها مقدمو الخدمة عادةً للتسعير بدقة.",
    publishBlocked: "أصلح البنود أعلاه قبل النشر.",
    documents_required_missing: "ذكرت أن مقدمي الخدمة يحتاجون المستندات للتسعير، لكن لم يُرفع أي منها. ارفعها أو ألغِ تحديد هذا الخيار.",
  },
  invite: {
    heading: "انضم إلى {organization} على U-Tender",
    body: "دعا {inviter} البريد {email} للعمل باسم {organization}: للعمل على طلباتها أو عروضها مع الزملاء.",
    someone: "شخص ما",
    expires: "هذه الدعوة صالحة حتى {date}.",
    accept: "انضم إلى {organization}",
    signUp: "سجّل بهذا البريد",
    logIn: "تسجيل الدخول",
    wrongAccount: "أنت مسجل الدخول بحساب مختلف. سجّل الخروج وادخل باسم {email} لقبول الدعوة.",
    invalid: "رابط الدعوة غير صالح أو منتهي أو تم سحبه. اطلب رابطًا جديدًا.",
    acceptError: "تعذر قبول الدعوة.",
  },
  preview: {
    heading: "معاينة مقدم الخدمة",
    draftNote: "هكذا سيرى مقدمو الخدمة الموثقون المؤهلون طلبك بعد نشره. الطلب غير منشور: لا يراه إلا أنت وجهتك.",
    liveNote: "هكذا يرى مقدمو الخدمة المؤهلون طلبك.",
    back: "العودة إلى المسودة",
    inList: "في قائمة الفرص",
    inListHint: "قبل فتحه، يرى مقدمو الخدمة هذا فقط: دون العنوان الدقيق أو نطاق العمل أو المستندات.",
    opened: "عندما يفتحه مقدم الخدمة",
    openedHint: "ما يراه مقدم الخدمة المؤهل، مع العنوان الدقيق ونطاق العمل والبنود والمستندات والقواعد.",
    thenForm: "أسفل ذلك يملأ مقدمو الخدمة عرضهم: السعر (حسب البنود إذا طلبت ذلك) وكل ما هو مدرج تحت \"ما يجب أن يتضمنه عرضك\".",
    open: "معاينة كمقدم خدمة",
    audienceHeading: "من سيصله الطلب",
    audienceCount: "{eligible} من أصل {total} من مقدمي الخدمة الموثقين على U-Tender يستوفون شروط \"من يمكنه تقديم عرض\" اليوم.",
    excluded_organization_only: "{count} مسجلون كأفراد (طلبت الجهات فقط)",
    excluded_qualification_missing: "{count} لا يحملون مؤهلًا مطلوبًا",
    excluded_qualification_expired: "{count} يحملون مؤهلًا مطلوبًا منتهي الصلاحية",
    excluded_category_not_offered: "{count} لا يدرجون هذا النوع من العمل ضمن خدماتهم",
    excluded_governorate_not_served: "{count} لا يخدمون هذه المحافظة",
    audienceNone: "لا يستوفي أي مقدم خدمة هذه الشروط حاليًا. فكر في تخفيفها في من يمكنه تقديم عرض.",
    audienceNote: "أعداد فقط؛ من يستوفي الشروط لاحقًا سيتمكن من تقديم عرض أيضًا.",
  },
  confirm: {
    cancel: "إلغاء",
    remove: "إزالة",
  },
  participate: {
    heading: "قررت المشاركة؟",
    body: "ابدأ إعداد عرضك. لا يُرسل شيء إلى المالك حتى تقدّمه، ويمكنك التوقف في أي وقت قبل ذلك.",
    button: "المشاركة — إعداد عرض",
    notNow: "ليست مناسبة لك؟ لا حاجة لأي إجراء. احفظها إن أردت أن تقرر لاحقًا.",
    error: "تعذّر بدء إعداد العرض.",
    changedHeading: "تغيّر الطلب بعد قرارك بالمشاركة",
    changedBody: "راجع التعديلات أعلاه: الطلب الحالي هو الذي سيُقدَّم عرضك على أساسه.",
    reviewed: "راجعت الطلب الحالي",
    preparingHeading: "عروض قيد الإعداد",
    changedShort: "تغيّر منذ أن بدأت",
    preparingFor: "أنت تُعِدّ عرضًا للطلب",
    reviewFirst: "أكّد أنك راجعت الطلب الحالي لمتابعة إعداد عرضك.",
    draftStatus: "مسودة — لم تُقدَّم. لا يُرسل شيء إلى المالك حتى تقدّمها.",
    draftStarted: "بدأت في",
    lastSaved: "آخر حفظ",
  },
  offerHistory: {
    yourOffer: "عرضك",
    readOnlyNote: "عرضك كما هو الآن. أُغلقت العروض، لذا لم يعد بالإمكان تغييره.",
    earlier: "الإصدارات السابقة",
  },
  submitOffer: {
    confirmTitle: "تقديم هذا العرض؟",
    confirmBody: "يُرسل عرضك المحفوظ إلى المالك كما يظهر في المعاينة تمامًا. حتى إغلاق العروض يمكنك تحديثه أو سحبه، ويُسجَّل كل تغيير.",
    submitted: "تم تقديم العرض",
    submittedAt: "قُدّم في",
    revision: "المراجعة",
    sealedNote: "هذه مناقصة مختومة: لا يرى المالك محتوى عرضك إلا بعد الموعد النهائي.",
    visibleNote: "يمكن للمالك رؤية عرضك الآن.",
    canStill: "حتى إغلاق العروض يمكنك تحديثه أو سحبه.",
    reviseTitle: "تحديث عرضك المقدَّم؟",
    reviseBody: "يحلّ هذا الإصدار محل عرضك الحالي لدى المالك. يبقى الإصدار السابق في سجل عرضك كما قُدِّم.",
    docsOnUpdate: "تصل تغييرات المستندات إلى المالك عند تحديث عرضك؛ وحتى ذلك الحين لدى المالك المستندات التي قدّمتها.",
    withdrawTitle: "سحب عرضك؟",
    withdrawBody: "لن يكون لدى المالك عرض منك للنظر فيه. يُحتفظ بعرضك وسجله، ويمكنك التقديم مجددًا ما دامت العروض مفتوحة.",
    withdrawnAt: "سُحب في",
    withdrawnNote: "ليس لدى المالك عرض منك للنظر فيه. يمكنك التقديم مجددًا ما دامت العروض مفتوحة؛ وتبقى إصداراتك السابقة في السجل.",
    resubmit: "التقديم مجددًا",
  },
  offerPreview: {
    open: "معاينة العرض",
    heading: "معاينة عرضك",
    backToEdit: "العودة إلى التعديل",
    notSubmitted: "هذه مسودتك المحفوظة كما ستُرسل إلى المالك تمامًا. لم تُقدَّم بعد. احفظ أي تعديلات أولًا لتظهر هنا.",
    passed: "اجتاز الفحوصات الحالية — جاهز للتقديم",
    fix: "الانتقال إلى القسم",
    requirement: "الرد على",
    version: "إصدار الطلب",
    amendment: "تعديل",
    outdated: "تغيّر الطلب بعد أن بدأت هذا العرض. راجع الطلب الحالي قبل التقديم.",
    scope: "نطاق العمل",
    from: "من",
    total: "السعر الإجمالي:",
    unknownItems: "بعض الأسعار تشير إلى بنود لم تعد في هذا الطلب.",
    notProvided: "غير مُدخل",
    loading: "جارٍ تحميل المعاينة…",
    unavailable: "لا يمكن معاينة هذا العرض الآن.",
  },
  readiness: {
    ready: "جاهز للتقديم",
    notReady: "لا يمكن التقديم بعد",
    recheck: "تحقّق مجددًا",
    savedOnly: "يتحقق هذا من المسودة المحفوظة — احفظ أولًا. يُعاد التحقق من كل شيء عند التقديم.",
    section_requirement: "الطلب",
    section_account: "حسابك",
    section_eligibility: "الأهلية",
    section_price: "السعر",
    section_technical: "المنهجية",
    section_timing: "التوقيت",
    section_documents: "المستندات",
    section_declarations: "الإقرارات",
    section_offer: "العرض",
  },
  timing: {
    heading: "التزامك بموعد البدء والإنجاز",
    ownerExpects: "يتوقع المالك:",
    start: "البدء",
    completion: "الإنجاز",
    duration: "المدة",
    durationDays: "أو المدة (بالأيام)",
    days: "يومًا",
    hint: "أدخل تاريخ الإنجاز أو المدة، وليس كليهما. لا يمكن أن يبدأ العمل أو ينتهي قبل إغلاق العروض.",
    conflict_starts_later: "تقترح البدء بعد تاريخ البدء الذي يتوقعه المالك.",
    conflict_finishes_later: "تقترح الإنجاز بعد موعد الإنجاز الذي يتوقعه المالك.",
    conflict_takes_longer: "تقترح مدة أطول من المدة التي يتوقعها المالك.",
  },
  saved: {
    save: "حفظ",
    saved: "محفوظ",
    unsave: "إزالة من المحفوظات",
    saveForLater: "احفظ لوقت لاحق",
    heading: "الفرص المحفوظة",
    intro: "الفرص التي حفظتها للرجوع إليها، بحالتها الحالية. المفتوحة أولًا.",
    backToFeed: "العودة إلى جميع الفرص",
    empty: "لا شيء محفوظ بعد. استخدم «حفظ» على أي فرصة لتظهر هنا.",
    unavailable: "فرصة حفظتها غير متاحة مؤقتًا.",
    remove: "إزالة",
  },
  detail: {
    addedAfter: "أُضيف بعد النشر · {date}",
    needsAccess: "أنت تستوفي شروط هذه الفرصة. فعّل وصولك إلى السوق لقراءة الطلب كاملًا وفتح مستنداته وتقديم عرض.",
    kuwaitTime: "بتوقيت الكويت",
  },
  feed: {
    pricing: "طريقة التسعير",
    items: "{n} بنود",
    loadMore: "عرض المزيد من الفرص",
    loading: "جارٍ التحميل…",
    hiddenIneligible: "لا تظهر {n} من الطلبات المفتوحة لأن شروطها (نوع مقدّم الخدمة أو المؤهلات أو نوع العمل أو المنطقة) لا تطابق حسابك.",
    checkServices: "راجع الخدمات والمناطق التي أعلنتها",
    lump_sum: "مبلغ إجمالي",
    per_item: "لكل بند",
    timeLeft: "الوقت المتبقي للرد",
    anyTimeLeft: "أي وقت متبقٍ",
    atLeastDays: "{n} أيام على الأقل",
    sortBy: "الترتيب",
    sortLatest: "الأبعد إغلاقًا",
    sortedLatest: "الفرص المفتوحة، الأبعد إغلاقًا أولًا",
    myServices: "أنواع العمل الخاصة بي",
    myAreas: "مناطق خدمتي",
    acceptingNow: "تقبل العروض الآن",
    clear: "مسح البحث والفلاتر",
    sortRelevance: "الأقرب لبحثك",
    sortedRelevance: "الفرص المفتوحة، الأقرب لبحثك أولًا",
    closedNow: "أُغلق تقديم العروض",
    leftDays: "متبقٍ {d} يوم و{h} ساعة للرد",
    leftHours: "متبقٍ {h} ساعة للرد",
    documents: "{n} مستندات",
    published: "نُشر {date}",
    sealed: "عروض مختومة",
    sealedHint: "تبقى العروض مختومة: لا يرى المالك الأسعار إلا بعد الموعد النهائي.",
    whoCanRespond: "من يمكنه الرد:",
    youQualify: "أنت تستوفيها",
    offer_withdrawn: "تم سحب العرض",
    offer_draft: "عرض قيد الإعداد",
    offer_approved: "تمت الترسية",
    offer_rejected: "لم يُختر",
  },
  versions: {
    version: "النسخة {n}",
    before: "اطّلع على الطلب كما كان قبل التغيير (النسخة {n})",
    yourOfferVersion: "اطّلع على الطلب الذي سُعّر عرضك على أساسه (النسخة {n})",
    pricedOn: "سُعّر على النسخة {n}",
    from: "من {date}",
    until: "حتى {date}",
    current: "الحالية",
    incomplete: "لم تُحفظ بعض التفاصيل السابقة للتغييرات التي جرت قبل بدء تسجيل النسخ؛ تظهر كما هي الآن.",
    documents: "المستندات في هذه النسخة:",
    replacedSince: "استُبدل لاحقًا",
    docsAdded: "مستندات أُضيفت:",
    docsReplaced: "مستندات استُبدلت:",
    yes: "نعم",
    no: "لا",
    field_title: "العنوان",
    field_address: "الموقع",
    field_governorate: "المحافظة",
    field_area: "المنطقة",
    field_trade: "نوع العمل",
    field_description: "نطاق العمل",
    field_bid_deadline: "إغلاق العروض",
    field_expected_start_date: "البدء المتوقع",
    field_expected_completion_date: "الإنجاز المتوقع",
    field_expected_duration_days: "المدة المتوقعة (أيام)",
    field_documents_required: "المستندات لازمة للتسعير",
  },
  closure: {
    open: "إنهاء هذا الطلب…",
    heading: "إنهاء هذا الطلب",
    hint: "كلٌّ من هذه الخيارات ينهي الطلب نهائياً: لا عروض جديدة ولا يمكن إعادة فتحه. تبقى العروض المقدَّمة محفوظة. لا شيء هنا يُرسي العمل.",
    note: "ملاحظة خاصة (اختيارية)",
    noteHint: "تُحفظ في سجلاتك فقط؛ لا يراها مقدّمو الخدمة.",
    cancelHeading: "إلغاء — لن يُنفَّذ بهذه الصيغة",
    reason_not_needed: "لم يعد العمل مطلوباً.",
    reason_postponed: "تم تأجيل العمل.",
    reason_other: "سبب آخر.",
    cancel: "إلغاء الطلب",
    cancelConfirm: "إلغاء هذا الطلب؟",
    cancelConfirmBody: "سيُبلَّغ مقدّمو الخدمة الذين قدّموا عروضاً بالإلغاء وسببه (السبب أعلاه، لا ملاحظتك). لا يمكن إعادة فتحه.",
    externalHeading: "أُغلق خارج U-Tender",
    externalHint: "رتّبت تنفيذ العمل بطريقة أخرى. لا تتم أي ترسية على U-Tender ولا يُسجَّل أي مقدّم خدمة فائزاً.",
    external: "إغلاق — تمّت المعالجة خارج U-Tender",
    externalConfirm: "إغلاق هذا الطلب على أنه عولج خارج U-Tender؟",
    externalConfirmBody: "لن يُقبل أي عرض. سيُبلَّغ مقدّمو الخدمة بأنه أُغلق دون ترسية عبر U-Tender. لا يمكن إعادة فتحه.",
    noSuitableHeading: "لا يوجد عرض مناسب",
    noSuitableHint: "أنهِ الطلب دون قبول أي عرض.",
    noSuitable: "إنهاء — لا عرض مناسب",
    noSuitableConfirm: "إنهاء دون قبول أي عرض؟",
    noSuitableConfirmBody: "لن يُقبل أي عرض ولن تتم ترسية. سيُبلَّغ مقدّمو الخدمة. لا يمكن إعادة فتحه.",
    error: "تعذّر إنهاء الطلب.",
    labelCanceled: "ملغى",
    labelExpired: "منتهي الصلاحية",
    labelExternal: "أُغلق خارج U-Tender",
    labelNoSuitable: "بلا ترسية",
    textCanceled: "ألغى المالك هذا الطلب؛ لن يُنفَّذ بهذه الصيغة.",
    textExpired: "انتهت فترة تقديم العروض دون أي عرض.",
    textExternal: "أغلق المالك هذا الطلب ورتّب تنفيذ العمل خارج U-Tender. لم يُقبل أي عرض عبر U-Tender.",
    textNoSuitable: "أنهى المالك هذا الطلب دون قبول أي عرض.",
    offersKept: "تبقى العروض المقدَّمة محفوظة. انتهى هذا الطلب ولن يُعاد فتحه.",
    dismiss: "إبقاؤه كما هو",
    yourNote: "ملاحظتك الخاصة:",
    restart: "بدء مسودة جديدة من هذا الطلب",
    restartConfirm: "بدء مسودة جديدة من هذا الطلب؟",
    restartConfirmBody: "تُنشأ مسودة جديدة بوصف هذا الطلب وبنوده وقواعده وشروط الأهلية ومستنداته الحالية. حدّد موعداً نهائياً جديداً وراجعها ثم انشرها كطلب جديد. يبقى هذا الطلب كما انتهى، مع عروضه.",
    restartedFrom: "بُدئ من جديد من طلب منتهٍ:",
    restartedFromLink: "اطّلع على الطلب الأصلي",
    adminSuspended: "علّقته إدارة U-Tender: مخفي عن مقدّمي الخدمة ولا يقبل عروضاً أو أسئلة أو تعديلات على العروض حتى إعادة تفعيله. تواصل مع الدعم إن رأيت أن ذلك خطأ.",
    labelSuspended: "معلّق من U-Tender",
  },
  postPub: {
    pause: "إيقاف الطلب مؤقتًا",
    pauseReason: "لماذا توقفه مؤقتًا؟ سيرى مقدمو الخدمة السبب.",
    pauseHint: "أثناء الإيقاف لا تُقبل عروض أو تعديلات أو سحب أو أسئلة. تبقى العروض الحالية محفوظة. يستمر موعد إغلاق العروض: مدّده إذا طال الإيقاف.",
    pausedSince: "موقوف مؤقتًا منذ {date}",
    pausedDeadline: "تُغلق العروض في {date} ما لم تمدد الموعد.",
    resume: "استئناف",
    resumeConfirm: "هل تريد استئناف الطلب؟ ستُقبل العروض مجددًا حتى {date}.",
    amendHeading: "تعديل الطلب المنشور",
    amendHint: "قد يكون مقدمو الخدمة يسعّرون هذا الطلب الآن. يُسجَّل كل تعديل بتعديل مرقّم ويُبلَّغ مقدمو العروض.\nتغيير نطاق العمل أو الموقع أو توقيت العمل (أو إضافة مستندات) يغيّر ما يسعّره مقدمو الخدمة: تُعلَّم عروضهم الحالية ليؤكدوها أو يعدّلوها، ويجب أن يتبقى 3 أيام على الأقل قبل إغلاق العروض. تصحيح العنوان أو تمديد الوقت ليس كذلك.\nلا يمكن تغيير البنود ومتطلبات العرض ومن يمكنه تقديم عرض وقواعد المناقصة بعد النشر.",
    address: "عنوان الموقع",
    area: "المنطقة",
    reason: "سبب التعديل (يظهر لمقدمي الخدمة)",
    amendSave: "حفظ التعديل",
    savedMaterial: "حُفظ كتعديل يغيّر ما يسعّره مقدمو الخدمة. تم إبلاغ مقدمي العروض وطُلب منهم تأكيد عروضهم أو تعديلها.",
    savedMinor: "حُفظ كتعديل. تم إبلاغ مقدمي العروض؛ تبقى عروضهم كما هي.",
    changesHeading: "التعديلات منذ النشر",
    material: "يغيّر التسعير",
    outdatedHeading: "تغيّر الطلب بعد تقديم عرضك",
    outdatedBody: "راجع التعديلات أعلاه. إذا كان عرضك ما زال قائمًا كما هو فأكّده، وإلا فعدّله أدناه.",
    confirmOffer: "عرضي ما زال قائمًا — تأكيد",
    outdatedOwner: "قُدّم قبل التعديل — لم يُؤكَّد بعد",
    pausedProvider: "أوقفه المالك مؤقتًا منذ {date}",
    pausedProviderBody: "لا تُقبل عروض أو تعديلات أو أسئلة حتى يُستأنف. تبقى العروض المقدمة محفوظة.",
    closedEarly: "أُغلق أمام العروض في {date}.",
    closeConfirm: "هل تريد إغلاق هذا الطلب أمام العروض الآن؟",
    closeConfirmBody: "لن تُقبل عروض أخرى. تبقى جميع العروض المستلمة كما قُدّمت؛ والترسية خطوة منفصلة.",
    error: "تعذر إتمام ذلك.",
    pausedPill: "موقوف مؤقتًا",
  },
  eligibility: {
    heading: "من يمكنه تقديم عرض",
    hint: "يجب أن يكون كل مقدم خدمة موثقًا مسبقًا لدى U-Tender. لا تضيّق النطاق إلا إذا تطلّب العمل ذلك فعلًا — فكل قيد يقلل عدد العروض التي تصلك.",
    providerType: "نوع مقدم الخدمة",
    anyProvider: "أي مقدم خدمة موثق (فرد أو جهة)",
    organizationOnly: "الجهات المسجلة فقط",
    qualificationsHeading: "المؤهلات المطلوبة",
    qualificationsHint: "يجب أن يحمل مقدم الخدمة هذه المستندات معتمدة من U-Tender وغير منتهية الصلاحية. تدير المنصة هذه القائمة.",
    noQualifications: "لا توجد مؤهلات لمقدمي الخدمة على المنصة حتى الآن.",
    save: "حفظ شروط الأهلية",
    saved: "تم الحفظ",
    saveError: "تعذر حفظ شروط الأهلية.",
    openToAll: "متاح لجميع مقدمي الخدمة الموثقين.",
    notEligible: "غير مؤهل لتقديم عرض",
    notEligibleIntro: "لا يمكنك تقديم عرض لهذا الطلب:",
    backToFeed: "العودة إلى المشاريع المتاحة",
    rulesLine: "من يمكنه تقديم عرض",
    reason_organization_only: "هذا الطلب متاح للجهات المسجلة فقط؛ حسابك مسجل كفرد.",
    reason_qualification_missing: "يتطلب هذا الطلب \"{name}\" معتمدًا من U-Tender. يمكنك إضافته من صفحة التوثيق.",
    reason_qualification_expired: "يتطلب هذا الطلب \"{name}\" ساري المفعول؛ انتهت صلاحية مستندك في {date}.",
    reason_category_not_offered: "هذا الطلب لأعمال \"{name}\"، وهي ليست ضمن الخدمات المدرجة في ملفك.",
    reason_governorate_not_served: "هذا الطلب في محافظة {governorate}، وهي ليست ضمن المحافظات التي يذكر ملفك أنك تخدمها.",
    matchCategory: "فقط مقدمو الخدمة الذين يقدمون هذا النوع من الأعمال ({category})",
    matchCategoryUnavailable: "اختر نوع العمل من قائمة المنصة لاستخدام هذا الخيار.",
    matchGovernorate: "فقط مقدمو الخدمة الذين يخدمون محافظة {governorate}",
    matchGovernorateUnavailable: "حدد المحافظة لاستخدام هذا الخيار.",
    matchingHeading: "نوع العمل والموقع",
    fixServices: "تحديث خدماتك",
    addQualification: "إضافة مؤهل",
    notForYou: "شروط هذه الفرصة — ليست مما يمكنك تغييره:",
    youCanFix: "يمكنك تصحيح ما يلي إن كان ينطبق على نشاطك:",
    canParticipate: "يمكنك المشاركة في هذه الفرصة.",
    ended: "لم تعد هذه الفرصة تقبل العروض.",
    unavailable: "هذه الفرصة غير متاحة مؤقتًا.",
    verificationNeeded: "أكمل التحقق من حسابك للمشاركة في الفرص.",
  },
  response: {
    heading: "ما يجب على مقدمي الخدمة تقديمه",
    hint: "يتضمن كل عرض سعرًا بعملة {currency}. اختر ما يجب أن يحتويه العرض الكامل أيضًا. تُرفض العروض التي ينقصها جزء مطلوب.",
    completionPeriod: "مدة الإنجاز",
    approach: "المنهجية / طريقة التنفيذ",
    required: "مطلوب",
    optional: "اختياري",
    documentsHeading: "المستندات المطلوب إرفاقها",
    documentsHint: "مثل: بيان طريقة التنفيذ، الجدول الزمني، نسخة الرخصة التجارية.",
    documentName: "اسم المستند",
    addDocument: "إضافة مستند",
    remove: "إزالة",
    declarationsHeading: "إقرارات يجب على مقدمي الخدمة تأكيدها",
    declarationsHint: "عبارات قصيرة يؤكدها كل مقدم خدمة، مثل: \"قمت بزيارة الموقع.\"",
    declarationText: "الإقرار",
    addDeclaration: "إضافة إقرار",
    save: "حفظ متطلبات العرض",
    saved: "تم الحفظ",
    saveError: "تعذر حفظ متطلبات العرض.",
    whatToSubmit: "ما يجب أن يتضمنه عرضك",
    priceTotal: "السعر الإجمالي بعملة {currency}",
    pricePerItem: "سعر وحدة بعملة {currency} لكل بند مدرج",
    rateCol: "سعر الوحدة ({currency})",
    saveDraft: "حفظ المسودة",
    unsaved: "تغييرات غير محفوظة",
    approachGuide: "اشرح كيف يلبّي عرضك مواصفات البنود والتعليمات الموجّهة لمقدمي العروض الموضّحة أعلاه.",
    assumptionsGuide: "اذكر ما يعتمد عليه سعرك أو برنامجك (إتاحة الموقع، ما يوفّره المالك)، وما هو مستثنى، وأي اختلاف عن المواصفات يحتاج إلى قبول المالك. يتسلّم المالك ذلك مع عرضك. للاستفسار عن الطلب نفسه، استخدم الأسئلة والأجوبة.",
    draftSaved: "حُفظت المسودة — لم تُقدَّم.",
    saveDraftError: "تعذّر حفظ المسودة.",
    lineTotalCol: "إجمالي البند",
    total: "الإجمالي",
    amount: "السعر الإجمالي ({currency})",
    assumptions: "الافتراضات والاستثناءات والتوضيحات",
    assumptionsPlaceholder: "مثال: لا يشمل نزح المياه الجوفية؛ يوفر المالك الماء والكهرباء في الموقع.",
    attachments: "المستندات الداعمة",
    upload: "رفع",
    replace: "استبدال",
    uploadError: "تعذر رفع المستند.",
    declarations: "الإقرارات",
    requiredMark: "مطلوب",
    noDocuments: "لا توجد مستندات مرفقة.",
    itemBreakdown: "تفصيل السعر",
    declarationsConfirmed: "تم تأكيد جميع الإقرارات",
    details: "تفاصيل العرض",
  },
  dates: {
    heading: "التواريخ",
    responseHeading: "الموعد النهائي لتقديم العروض",
    responseHint: "الوقت الذي يجب أن يقدّم فيه مزوّدو الخدمات عروضهم. تُرفض العروض بعد هذه اللحظة. بتوقيتك المحلي.",
    workHeading: "التوقيت المتوقع للعمل",
    workHint: "متى تتوقع تنفيذ العمل نفسه، ليتمكن مزوّدو الخدمات من التحقق من توفرهم. اختياري؛ اتركه فارغًا إن لم ينطبق.",
    start: "البدء المتوقع",
    finishBy: "الانتهاء بحلول",
    completion: "تاريخ الإنجاز المتوقع",
    duration: "المدة (أيام)",
    durationOr: "أو",
    save: "حفظ التواريخ",
    saved: "تم الحفظ",
    saveError: "تعذر حفظ التواريخ.",
    pastDeadline: "انقضى هذا الموعد. حدّد موعدًا مستقبليًا قبل النشر.",
    work: "العمل",
    from: "من {date}",
    until: "حتى {date}",
    days: "{n} يوم",
  },
  documents: {
    drawing: "مخطط",
    boq: "جدول كميات",
    specification: "مواصفات",
    photo: "صورة",
    site: "مستند الموقع",
    other: "أخرى",
    typeLabel: "نوع المستند",
    essential: "أساسي للتسعير",
    supplementary: "تكميلي",
    essentialToggle: "يحتاجه مزوّدو الخدمات لتسعير العمل",
    remove: "حذف",
    removeConfirm: "حذف هذا المستند ونسخه السابقة من المسودة؟",
    uploadHint: "PDF أو DWG أو Excel (.xlsx) أو Word (.docx) أو JPG/PNG أو ملف .zip يضمها، حتى 50 ميجابايت لكل رفع. رفع ملف بالاسم نفسه يستبدله كنسخة جديدة.",
    heading: "المستندات",
    saveError: "تعذر تحديث المستند.",
    neededToPrice: "يحتاج مقدمو الخدمة هذه المستندات لتسعير العمل",
    neededToPriceHint: "حدد هذا إذا تعذر تسعير العمل بدون المخططات أو جدول الكميات أو الصور. عندها يتطلب النشر مستندًا واحدًا على الأقل.",
  },
  location: {
    governorate: "المحافظة",
    chooseGovernorate: "اختر المحافظة",
    allGovernorates: "كل المحافظات",
    capital: "العاصمة",
    hawalli: "حولي",
    farwaniya: "الفروانية",
    mubarak_al_kabeer: "مبارك الكبير",
    ahmadi: "الأحمدي",
    jahra: "الجهراء",
    area: "المنطقة",
    areaHint: "الحي، مثل: السالمية، مشرف، الفحيحيل. يظهر في القوائم مع المحافظة.",
    address: "العنوان الدقيق أو وصف الموقع",
    addressHint: "القطعة والشارع والمنزل أو القسيمة والمعالم أو الاتجاهات. يظهر فقط لمزوّدي الخدمات الذين يمكنهم فتح المتطلب كاملًا، وليس في القوائم.",
    siteNotesHint: "ظروف الوصول إلى الموقع أو الظروف المؤثرة في العمل (ساعات العمل، دخول الشاحنات، مبنى مأهول…) تُكتب في نطاق العمل تحت «ظروف الموقع والعمل».",
    notSpecified: "الموقع غير محدد",
  },
  requirementItems: {
    heading: "الكميات وأساس التسعير",
    intro: "ما يحتاجه مزوّد الخدمة لحساب سعره. أضف بنودًا فقط إذا كان العمل يُقاس بطبيعته؛ وإلا فاترك القائمة فارغة.",
    basisLabel: "يسعّر مزوّدو الخدمة",
    lump_sum: "سعرًا إجماليًا واحدًا للمتطلب كاملًا",
    lump_sum_hint: "أي بنود أدناه للاسترشاد: تساعد مزوّد الخدمة على تقدير سعر إجمالي واحد.",
    per_item: "كل بند مذكور على حدة",
    per_item_hint: "يقدّم مزوّدو الخدمة سعرًا لكل بند أدناه. أضف بندًا واحدًا على الأقل.",
    item: "البند / مكوّن العمل",
    quantity: "الكمية",
    unit: "الوحدة",
    specification: "المواصفات والملاحظات",
    specificationPlaceholder: "المواصفات أو الأبعاد أو المعايير أو أي شيء يؤثر في السعر",
    addItem: "+ إضافة بند",
    remove: "حذف",
    noItems: "لا توجد بنود. هذا مناسب للأعمال التي لا تُقاس بطبيعتها؛ نطاق العمل يصفها.",
    save: "حفظ الكميات والتسعير",
    saved: "تم الحفظ",
    saveError: "تعذر حفظ البنود.",
    providerHeading: "ما المطلوب تسعيره",
    provider_lump_sum: "قدّم سعرًا إجماليًا واحدًا للمتطلب كاملًا. أي بنود مذكورة هي لمساعدتك على تقديره.",
    provider_per_item: "قدّم سعرًا لكل بند مذكور أدناه.",
    notSpecified: "غير محدد",
  },
  draftDetails: {
    heading: "تفاصيل المتطلب",
    intro: "الأساسيات التي يراها مزوّد الخدمة أولًا: ما هو العمل وأين. هذه المسودة خاصة بك حتى تنشرها.",
    title: "العنوان",
    titleHint: "قصير ومحدد، مثال: «توسعة فيلا — مجلس الدور الأرضي».",
    category: "نوع العمل",
    categoryHint: "الحرفة أو الخدمة المطلوبة، مثل: إنشاءات، أعمال كهروميكانيكية، تشطيبات داخلية، تنسيق حدائق.",
    location: "الموقع",
    locationHint: "المحافظة والمنطقة والقطعة، مثال: «حولي — السالمية، قطعة 4».",
    scopeHeading: "نطاق العمل",
    scopeIntro: "صف العمل الذي تطلبه من مزوّد الخدمة بوضوح يكفي ليقرر هل يستطيع تنفيذه وكيف يسعّره.",
    scopeTopics: "غطِّ ما ينطبق على هذا العمل: المهام، وما يجب تسليمه، والمواصفات أو المعايير، والكميات، وما يشمله وما لا يشمله، وظروف الموقع، وأي شيء آخر يحتاج معرفته. تجاوز ما لا ينطبق.",
    insertOutline: "إدراج مخطط",
    outline: "نظرة عامة:\n\n\nالأعمال / المهام المطلوبة:\n- \n\nالمخرجات المطلوب تسليمها:\n- \n\nالمواصفات والمعايير:\n- \n\nالكميات / القياسات:\n- \n\nيشمل:\n- \n\nلا يشمل (على المالك أو غيره):\n- \n\nظروف الموقع والعمل:\n- \n\nتعليمات أخرى:\n- ",
    charCount: "{count} / {max} حرف",
    save: "حفظ المسودة",
    saving: "جارٍ الحفظ…",
    saved: "تم الحفظ",
    saveError: "تعذر حفظ المسودة.",
    notSet: "غير محدد",
    lastSaved: "مسودة — آخر حفظ {date}. لا يراها أحد غيرك؛ لن يُنشر شيء حتى تقوم بالنشر.",
    discard: "تجاهل المسودة",
    discardConfirm: "هل تريد تجاهل هذه المسودة؟ لن تظهر في القائمة ولن يمكن تعديلها أو نشرها. لا يمكن التراجع عن ذلك.",
    discarded: "تم تجاهل هذه المسودة في {date}. تُحفظ لسجلاتك لكن لا يمكن تعديلها أو نشرها.",
    resumeHeading: "لديك مسودات قيد الإعداد",
    resumeHint: "تابع إحداها بدلًا من البدء من جديد:",
    untitled: "بدون عنوان",
    lastSavedShort: "آخر حفظ {date}",
    expired: "انتهت صلاحية هذا الطلب عند موعد إغلاق العروض ({date}) دون أي عروض. أصبح الآن للقراءة فقط.",
    publishConfirm: "هل تريد نشر \"{title}\" الآن؟\n\nسيتمكن مقدمو الخدمة الموثقون الذين يستوفون شروط \"من يمكنه تقديم عرض\" من العثور عليه وفتحه وتقديم العروض حتى {deadline}.\n\nبعد النشر لا يمكن تغيير قواعده وشروطه من هنا.",
    publishNowConfirm: "هل تريد نشر هذا الطلب فورًا دون حفظه كمسودة أولًا؟\n\nسيتمكن مقدمو الخدمة الموثقون من العثور عليه وتقديم العروض حتى {deadline}. لمراجعته كما سيراه مقدمو الخدمة أولًا، احفظه كمسودة واستخدم المعاينة.",
    published: "نُشر في {date} — مفتوح للعروض حتى {deadline}.",
  },
  verification: {
    scopeLabel: "ينطبق على",
    scopeAll: "الأفراد والجهات",
    scopeIndividual: "الأفراد فقط",
    scopeOrganization: "الجهات فقط",
    requiresExpiry: "يلزم تاريخ انتهاء عند الاعتماد",
    expiryBadge: "يلزم تاريخ انتهاء",
    state_not_started: "لم يبدأ",
    state_incomplete: "قيد الإكمال",
    state_submitted: "تم الإرسال، بانتظار المراجعة",
    state_under_review: "قيد المراجعة",
    state_correction_required: "مطلوب تصحيح",
    state_approved: "معتمد",
    state_rejected: "مرفوض",
    stateLabel: "التحقق",
    correctionNeeded: "مطلوب تصحيح:",
    reviewerMessage: "رسالة من المراجع:",
    rejectedBody: "تم رفض طلب التحقق الخاص بك. إذا كنت تعتقد أن ذلك خطأ، تواصل مع الدعم.",
    locked: "لا يمكن تغيير المستندات أثناء مراجعة طلب التحقق أو بعد اتخاذ قرار بشأنه.",
    replace: "استبدال",
    noRequirements: "لا توجد مستندات مطلوبة حاليًا لهذا الحساب.",
    addLaterHint: "حسابك موثق. يمكنك إضافة مؤهلات اختيارية في أي وقت — تُراجع كل منها على حدة ويستمر وصولك أثناء ذلك.",
  },
  stakeholder: {
    heading: "من يمثّل هذا الحساب؟",
    intro: "تسجيل الدخول يخصك أنت شخصيًا دائمًا. أخبرنا هل تستخدم U-Tender لنفسك أم نيابةً عن جهة: يتم التحقق من هذه الهوية وتُسجَّل باسمها كل أنشطتك على المنصة.",
    individual_owner: "نفسي",
    individual_owner_hint: "أنا مالك أرض أو صاحب مشروع أو مشترٍ أتصرف بصفتي الشخصية.",
    organization_owner: "جهة",
    organization_owner_hint: "شركة أو جهة حكومية أو أي جهة أخرى مخوّل بالتصرف نيابةً عنها.",
    individual_service_provider: "نفسي",
    individual_service_provider_hint: "أقدّم الخدمات بصفتي الفردية أو كتاجر فرد.",
    organization_service_provider: "شركة",
    organization_service_provider_hint: "شركة مقاولات أو خدمات مخوّل بالتصرف نيابةً عنها.",
    legalName: "الاسم القانوني للجهة",
    position: "منصبك (اختياري)",
    positionPlaceholder: "مثال: المدير العام",
    authorized: "أؤكد أنني مخوّل بالتصرف نيابةً عن هذه الجهة.",
    save: "متابعة",
    saving: "جارٍ الحفظ…",
    change: "تغيير",
    saveError: "تعذر الحفظ. حاول مرة أخرى.",
    actingAs: "تتصرف بصفة",
    typeIndividual: "فرد",
    typeOrganization: "جهة",
    representative: "الممثل المفوّض",
    member: "عضو",
    yourRole: "دورك",
    locked: "لا يمكن تغيير ذلك أثناء مراجعة التحقق أو بعد اعتماده.",
    mustEstablish: "أجب عن سؤال «من يمثّل هذا الحساب؟» أعلاه قبل الإرسال للمراجعة.",
    notEstablished: "لم يُحدَّد بعد",
    accountCreated: "تم إنشاء الحساب",
    established: "تم تحديد الهوية",
    verified: "تم التحقق",
    eligible: "مؤهل للمشاركة",
    adminHeading: "يمثّل",
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
      service_provider: "مزوّد خدمة",
      chooseRole: "اختر مالك أو مزوّد خدمة للمتابعة.",
      signingUpAs: "التسجيل بصفة",
      changeRole: "تغيير",
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
    closesAt: "تُغلق الأسئلة والأجوبة في {date}.",
    closedAt: "أُغلقت الأسئلة والأجوبة في {date}. لا أسئلة أو أجوبة جديدة.",
    unansweredClosed: "لم تتم الإجابة قبل موعد إغلاق الأسئلة.",
    yourQuestion: "سؤالك",
    answeredOn: "أُجيب في {date}",
    cameWithChange: "جاءت هذه الإجابة مع تعديل على الطلب (التعديل رقم {n}) — اطّلع على التعديلات أعلاه.",
    publishForAll: "انشر هذا السؤال وإجابته لجميع مقدّمي الخدمة (يبقى السائل مجهولًا)",
    materialHint: "إن غيّرت الإجابة نطاق العمل أو الكميات أو المستندات أو التوقيت أو من يمكنه الرد، فعدّل الطلب نفسه أيضًا (تعديل الطلب المنشور) واختر هذا السؤال هناك.",
    becauseOf: "بسبب سؤال (اختياري)",
    notBecauseOf: "ليس بسبب سؤال",
    attachFiles: "إرفاق ملفات (اختياري، حتى 5: PDF أو صور أو مخططات أو Excel أو Word)",
  },
  service_provider: {
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
      searchPlaceholder: "ابحث بالعنوان أو المنطقة أو نوع العمل أو نطاق العمل…",
      allTrades: "كل التخصصات",
      sortClosest: "الأقرب إغلاقًا",
      sortNewest: "الأحدث أولاً",
      noMatch: "لا توجد فرص مفتوحة تطابق البحث والفلاتر.",
      noOpenProjects: "لا توجد فرص يمكنك الاستجابة لها حاليًا. تظهر الفرص الجديدة هنا فور نشرها.",
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
      heading: "تحقق من حسابك",
      description: "قدّم المستندات أدناه ليتمكن مسؤول الموقع من تفعيل حسابك.",
      companyName: "الاسم الظاهر للملاك (الاسم التجاري)",
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
      drawings: "المستندات",
      downloadZip: "تنزيل الكل كملف .zip",
      noDrawings: "لم يتم رفع أي مخططات لهذا المشروع.",
      biddingClosedNotice: "أُغلق تقديم العروض على هذا المشروع.",
      yourFinalOffer: "عرضك النهائي:",
      awardedTo: "تم الترسية على",
      anotherServiceProvider: "مزوّد خدمة آخر",
      noAwardNotice: "قرر المالك عدم ترسية هذا المشروع.",
      bidAmount: "قيمة عرضك",
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
      drawings: "المخططات والمستندات",
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
      addDrawings: "إضافة مستندات",
      zipHint: "يمكنك أيضًا رفع ملف .zip يحتوي على المخططات.",
      scope: "نطاق العمل",
      lowestBid: "أقل عرض",
      averageBid: "متوسط العروض",
      highestBid: "أعلى عرض",
      sealedBidsReceived: "عرض/عروض سرية مستلمة",
      sealedExplanation:
        "هذا عطاء مغلق (سري) — تبقى هويات مزوّدي الخدمات وقيم عروضهم مخفية عنك حتى يُغلق تقديم العروض. أغلق تقديم العروض لكشفها وتقييمها.",
      noOffersYet: "لا توجد عروض بعد. يمكن لمزوّدي الخدمات تقديم عروض حتى الموعد النهائي أعلاه.",
      serviceProviderCol: "مزوّد الخدمة",
      ratingCol: "التقييم",
      bidCol: "العرض",
      timelineCol: "الجدول الزمني",
      revisedSuffix: "مُعدَّل ×",
      approve: "قبول",
      closeToAwardHint: "أغلق تقديم العروض للترسية",
      rateServiceProvider: "قيّم",
      theServiceProvider: "مزوّد الخدمة",
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
      service_providers: "جميع مزوّدي الخدمات",
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
      service_provider: "مزوّد الخدمة",
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
      serviceProviderCol: "مزوّد الخدمة",
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
      forServiceProviders: "لمزوّدي الخدمات",
      forOwners: "للملاك",
      emptyForScope: "لا توجد متطلبات مُعدة لهذه المجموعة بعد.",
      toggleRequiredFor: "تبديل حالة الإلزام لـ",
      required: "مطلوب",
      optional: "اختياري",
      removeTitle: "إزالة المتطلب",
      namePlaceholder: "اسم المستند، مثال: الهوية المدنية",
      descriptionPlaceholder: "وصف مختصر يظهر لمقدم الطلب",
      addForOwners: "+ إضافة متطلب للملاك",
      addForServiceProviders: "+ إضافة متطلب لمزوّدي الخدمات",
      edit: "تعديل",
      addError: "تعذر إضافة المتطلب.",
      updateError: "تعذر تحديث المتطلب.",
      removeError: "تعذر إزالة المتطلب.",
    },
  },
};
