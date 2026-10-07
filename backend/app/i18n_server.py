"""The server's own messages in the viewer's language.

Error messages are written in English where they are raised. The language of
the request (the interface sends Accept-Language: en | ar) is held in a
context variable by middleware, and the error handlers translate each
message here before it is sent: whole message first, otherwise sentence by
sentence, so messages assembled from parts (the quality gate, eligibility
reasons, "your offer is missing ...") translate too. Messages carrying
values (names, dates, numbers) are matched by pattern. Anything without a
translation stays as written rather than being dropped.
"""
import re
from contextvars import ContextVar

current_language: ContextVar[str] = ContextVar("current_language", default="en")

GOVERNORATES_AR = {
    "Capital": "العاصمة",
    "Hawalli": "حولي",
    "Farwaniya": "الفروانية",
    "Mubarak Al Kabeer": "مبارك الكبير",
    "Ahmadi": "الأحمدي",
    "Jahra": "الجهراء",
}

AR: dict[str, str] = {
    # --- accounts, sign-in, organizations ---
    "An account with this email already exists.": "يوجد حساب بهذا البريد الإلكتروني بالفعل.",
    "Current password is incorrect.": "كلمة المرور الحالية غير صحيحة.",
    "Invalid email or password.": "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
    "Too many failed login attempts.": "محاولات تسجيل دخول فاشلة كثيرة.",
    "Please try again later.": "يرجى المحاولة لاحقًا.",
    "Try again.": "حاول مرة أخرى.",
    "This reset link is invalid or has expired.": "رابط إعادة التعيين غير صالح أو منتهي الصلاحية.",
    "This verification link is invalid or has expired.": "رابط التحقق غير صالح أو منتهي الصلاحية.",
    "If an account with that email exists, a reset link has been sent.": "إذا كان هناك حساب بهذا البريد، فقد أُرسل رابط إعادة التعيين.",
    "Only owner or service provider accounts can self-register.": "يمكن التسجيل الذاتي لحسابات الملاك ومقدمي الخدمة فقط.",
    "Only owner or service provider accounts represent a stakeholder.": "حسابات الملاك ومقدمي الخدمة فقط تمثل طرفًا في السوق.",
    "Confirm that you are authorized to act for this organization.": "أكد أنك مفوض بالتصرف نيابة عن هذه الجهة.",
    "The organization's legal name is required.": "الاسم القانوني للجهة مطلوب.",
    "Only the organization's authorized representative can change it.": "يمكن للممثل المفوض للجهة فقط تغييره.",
    "Only the organization's authorized representative can manage its members.": "يمكن للممثل المفوض للجهة فقط إدارة أعضائها.",
    "Who this account represents can't be changed while it is under review or after it has been verified.": "لا يمكن تغيير من يمثله هذا الحساب أثناء المراجعة أو بعد التوثيق.",
    "Tell us whether this account represents you personally or an organization before submitting for review.": "أخبرنا ما إذا كان هذا الحساب يمثلك شخصيًا أو يمثل جهة قبل الإرسال للمراجعة.",
    "This account doesn't act for an organization.": "هذا الحساب لا يعمل باسم جهة.",
    "You act for an organization.": "أنت تعمل باسم جهة.",
    "Ask its representative to remove you first.": "اطلب من ممثلها إزالتك أولًا.",
    "No account with that email.": "لا يوجد حساب بهذا البريد.",
    "Ask your colleague to sign up first.": "اطلب من زميلك التسجيل أولًا.",
    "That account is on the other side of the marketplace.": "هذا الحساب على الجانب الآخر من السوق.",
    "That account can't join an organization.": "لا يمكن لهذا الحساب الانضمام إلى جهة.",
    "That account already belongs to an organization.": "هذا الحساب ينتمي إلى جهة بالفعل.",
    "That account already represents someone in its own right, so it can't join.": "هذا الحساب يمثل طرفًا بذاته بالفعل، لذا لا يمكنه الانضمام.",
    "Not a member of this organization.": "ليس عضوًا في هذه الجهة.",
    "You can't remove yourself as the organization's representative.": "لا يمكنك إزالة نفسك بصفتك ممثل الجهة.",
    "This invitation is invalid, has expired or was withdrawn.": "هذه الدعوة غير صالحة أو منتهية أو تم سحبها.",
    "This invitation is for a different email address.": "هذه الدعوة لبريد إلكتروني مختلف.",
    "This invitation is for an account on the other side of the marketplace.": "هذه الدعوة لحساب على الجانب الآخر من السوق.",
    "An invitation to that email is already pending.": "توجد دعوة معلّقة لهذا البريد بالفعل.",
    "That person is already a member.": "هذا الشخص عضو بالفعل.",
    "Invitation not found.": "الدعوة غير موجودة.",
    # --- verification ---
    "Company name is required.": "اسم الشركة مطلوب.",
    "Documents can only be uploaded while your verification is being completed or corrected.": "لا يمكن رفع المستندات إلا أثناء استكمال التوثيق أو تصحيحه.",
    "Document requirement not found for this owner.": "متطلب المستند غير موجود لهذا المالك.",
    "Document requirement not found for this service provider.": "متطلب المستند غير موجود لمقدم الخدمة هذا.",
    "All required documents must be approved before approving this account.": "يجب اعتماد جميع المستندات المطلوبة قبل اعتماد هذا الحساب.",
    "A document can only be approved or sent back for correction.": "يمكن اعتماد المستند أو إعادته للتصحيح فقط.",
    "This document hasn't been uploaded yet.": "لم يُرفع هذا المستند بعد.",
    "Say what needs to be corrected, so the account holder knows what to fix.": "وضّح ما يجب تصحيحه ليعرف صاحب الحساب ما يصلحه.",
    "Give the reason for rejecting this application.": "اذكر سبب رفض هذا الطلب.",
    "Request a correction on a specific document, or say what needs to change.": "اطلب تصحيح مستند محدد، أو وضّح ما يجب تغييره.",
    "Document requirements can only apply to owners or service providers.": "تنطبق متطلبات المستندات على الملاك ومقدمي الخدمة فقط.",
    "Document name is required.": "اسم المستند مطلوب.",
    "Only owner or service provider checklists are public.": "قوائم مستندات الملاك ومقدمي الخدمة فقط عامة.",
    "A reason is required to grant a payment override.": "يلزم ذكر سبب لمنح استثناء الدفع.",
    # --- requirements (projects) ---
    "Project not found.": "المشروع غير موجود.",
    "Requirement not found.": "الطلب غير موجود.",
    "A new project must start as draft or open.": "يجب أن يبدأ المشروع الجديد كمسودة أو مفتوحًا.",
    "Invalid tender type.": "نوع المناقصة غير صالح.",
    "Bid deadline must be in the future.": "يجب أن يكون موعد إغلاق العروض في المستقبل.",
    "Invalid bid deadline.": "موعد إغلاق العروض غير صالح.",
    "Invalid question deadline.": "موعد إغلاق الأسئلة غير صالح.",
    "Use an ISO 8601 date and time, e.g. 2030-01-31T17:00:00Z.": "استخدم تاريخًا ووقتًا بصيغة ISO 8601، مثل 2030-01-31T17:00:00Z.",
    "Title cannot be empty.": "لا يمكن أن يكون العنوان فارغًا.",
    "Location cannot be empty.": "لا يمكن أن يكون الموقع فارغًا.",
    "Address cannot be empty.": "لا يمكن أن يكون العنوان فارغًا.",
    "Unknown governorate.": "محافظة غير معروفة.",
    "Area must be 100 characters or fewer.": "يجب ألا تزيد المنطقة عن 100 حرف.",
    "No changes were provided.": "لم تُقدَّم أي تغييرات.",
    "This project can no longer be amended.": "لم يعد من الممكن تعديل هذا المشروع.",
    "Cannot move the deadline earlier once bids have been submitted.": "لا يمكن تقديم الموعد النهائي بعد تقديم العروض.",
    "Work can't be expected to start before the response deadline.": "لا يمكن أن يبدأ العمل قبل موعد إغلاق العروض.",
    "Work can't be expected to finish before the response deadline.": "لا يمكن أن ينتهي العمل قبل موعد إغلاق العروض.",
    "The expected completion date can't be before the expected start date.": "لا يمكن أن يكون تاريخ الإنجاز المتوقع قبل تاريخ البدء المتوقع.",
    "Give either an expected completion date or a duration, not both.": "أدخل تاريخ إنجاز متوقع أو مدة، وليس كليهما.",
    "The offer deadline must be in the future.": "يجب أن يكون موعد إغلاق العروض في المستقبل.",
    "The offer deadline must be after the question deadline.": "يجب أن يكون موعد إغلاق العروض بعد موعد إغلاق الأسئلة.",
    "The question deadline must be in the future.": "يجب أن يكون موعد إغلاق الأسئلة في المستقبل.",
    "Questions must close before offers close.": "يجب أن تُغلق الأسئلة قبل إغلاق العروض.",
    "Items and the pricing basis can only be changed while the requirement is a draft.": "لا يمكن تغيير البنود وأساس التسعير إلا والطلب مسودة.",
    "Add at least one item to price per item, or ask for one total price.": "أضف بندًا واحدًا على الأقل للتسعير حسب البنود، أو اطلب سعرًا إجماليًا واحدًا.",
    "Response requirements can only be changed while the requirement is a draft.": "لا يمكن تغيير متطلبات العرض إلا والطلب مسودة.",
    "Each declaration must be 1-500 characters.": "يجب أن يكون كل إقرار بين 1 و500 حرف.",
    "Each requested document needs a different name.": "يحتاج كل مستند مطلوب إلى اسم مختلف.",
    "Eligibility can only be changed while the requirement is a draft.": "لا يمكن تغيير شروط الأهلية إلا والطلب مسودة.",
    "Tender rules can only be changed while the requirement is a draft.": "لا يمكن تغيير قواعد المناقصة إلا والطلب مسودة.",
    "Offer visibility can't change once an offer exists.": "لا يمكن تغيير ظهور العروض بعد وجود عرض.",
    "Payment stages must add up to 100%.": "يجب أن يكون مجموع مراحل الدفع 100%.",
    "Give both the retention percentage and how long it is held.": "أدخل نسبة المحتجزات ومدة احتجازها معًا.",
    "Choose qualifications from the platform's list of provider documents.": "اختر المؤهلات من قائمة مستندات مقدمي الخدمة في المنصة.",
    "Choose the type of work from the platform's list before restricting by it.": "اختر نوع العمل من قائمة المنصة قبل التقييد به.",
    "Set the governorate before restricting by it.": "حدد المحافظة قبل التقييد بها.",
    "Choose a type of work from the platform's list.": "اختر نوع عمل من قائمة المنصة.",
    "Choose services from the platform's list.": "اختر الخدمات من قائمة المنصة.",
    "Choose governorates from the list.": "اختر المحافظات من القائمة.",
    "Who can respond depends on the governorate, so it can't be changed after publishing.": "شرط من يمكنه تقديم عرض يعتمد على المحافظة، لذا لا يمكن تغييرها بعد النشر.",
    "Who can respond depends on the type of work, so it can't be changed after publishing.": "شرط من يمكنه تقديم عرض يعتمد على نوع العمل، لذا لا يمكن تغييره بعد النشر.",
    "Who can respond depends on this requirement's type of work, so it can't be changed after publishing.": "شرط من يمكنه تقديم عرض يعتمد على نوع عمل هذا الطلب، لذا لا يمكن تغييره بعد النشر.",
    "Unknown document type.": "نوع مستند غير معروف.",
    "Document not found.": "المستند غير موجود.",
    "Documents can only be removed or re-labelled while the requirement is a draft.": "لا يمكن إزالة المستندات أو إعادة تصنيفها إلا والطلب مسودة.",
    "No drawings on this project.": "لا توجد مخططات في هذا المشروع.",
    "No accessible drawings.": "لا توجد مخططات متاحة.",
    "No file provided.": "لم يُقدَّم ملف.",
    "Archive is too large when extracted.": "الملف المضغوط كبير جدًا عند فكه.",
    # --- drafts ---
    "Only a draft can be discarded.": "يمكن تجاهل المسودة فقط.",
    "This draft has already been discarded.": "تم تجاهل هذه المسودة بالفعل.",
    "This draft was discarded and can no longer be changed.": "تم تجاهل هذه المسودة ولم يعد بالإمكان تغييرها.",
    "This requirement was changed somewhere else (another tab, device or team member) since you opened it.": "تم تغيير هذا الطلب في مكان آخر (علامة تبويب أو جهاز أو عضو فريق آخر) منذ فتحته.",
    "Reload to see the latest version, then make your change again.": "أعد التحميل لرؤية أحدث نسخة، ثم أجرِ تغييرك مرة أخرى.",
    # --- quality gate ---
    "This requirement isn't ready to publish.": "هذا الطلب ليس جاهزًا للنشر.",
    "Give the requirement a title that says what the work is (at least 5 characters).": "أعطِ الطلب عنوانًا يوضح نوع العمل (5 أحرف على الأقل).",
    "Describe the work: what needs doing, where on the site and to what standard.": "صف العمل: ما المطلوب، وأين في الموقع، وبأي مستوى.",
    "A provider can't price a requirement without it.": "لا يمكن لمقدم الخدمة تسعير طلب بدونه.",
    "Give the site address or a description of where the site is.": "أدخل عنوان الموقع أو وصفًا لمكانه.",
    "Choose the governorate, so providers can judge travel and whether they cover the area.": "اختر المحافظة ليتمكن مقدمو الخدمة من تقدير التنقل وتغطية المنطقة.",
    "Set an offer deadline in the future.": "حدد موعدًا مستقبليًا لإغلاق العروض.",
    "The question deadline has passed: move it later, or remove it to take questions until offers close.": "انتهى موعد الأسئلة: أجّله، أو احذفه لاستقبال الأسئلة حتى إغلاق العروض.",
    "The requirement is priced per item but lists no items.": "الطلب مسعّر حسب البنود لكنه لا يتضمن بنودًا.",
    "Add the items, or price it as one total.": "أضف البنود أو اجعله سعرًا إجماليًا واحدًا.",
    "Who can respond depends on the type of work, but none from the platform's list is chosen.": "شرط من يمكنه تقديم عرض يعتمد على نوع العمل، لكن لم يُختر نوع من قائمة المنصة.",
    "Who can respond depends on the governorate, but none is chosen.": "شرط من يمكنه تقديم عرض يعتمد على المحافظة، لكن لم تُختر محافظة.",
    "A required qualification is no longer on the platform's list.": "أحد المؤهلات المطلوبة لم يعد ضمن قائمة المنصة.",
    "Choose again under Who can respond.": "اختر مجددًا في من يمكنه تقديم عرض.",
    "The requirement depends on its documents, but none are uploaded.": "يعتمد الطلب على مستنداته، لكن لم يُرفع أي منها.",
    "Upload them, or untick that providers need them to price.": "ارفعها، أو ألغِ تحديد أن مقدمي الخدمة يحتاجونها للتسعير.",
    "Set a bid deadline in the future before publishing.": "حدد موعدًا مستقبليًا لإغلاق العروض قبل النشر.",
    "Only a draft project can be published.": "يمكن نشر مسودة المشروع فقط.",
    # --- lifecycle ---
    "Only an open project can be closed.": "يمكن إغلاق المشروع المفتوح فقط.",
    "A sealed tender can't be closed early — its bids stay sealed until the deadline.": "لا يمكن إغلاق مناقصة مختومة مبكرًا — تبقى عروضها مختومة حتى الموعد النهائي.",
    "Cancel the tender instead if you no longer want bids.": "ألغِ المناقصة بدلًا من ذلك إذا لم تعد تريد عروضًا.",
    "Only a closed project can enter evaluation.": "يمكن تقييم المشروع المغلق فقط.",
    "Only a closed or under-evaluation project can be marked no-award.": "يمكن وضع علامة عدم الترسية على المشروع المغلق أو قيد التقييم فقط.",
    "This project can no longer be canceled.": "لم يعد من الممكن إلغاء هذا المشروع.",
    "Close bidding before awarding an offer.": "أغلق العروض قبل ترسية عرض.",
    "Only a live bid can be awarded.": "يمكن ترسية عرض قائم فقط.",
    "This project has already been awarded, canceled, or has no award.": "تمت ترسية هذا المشروع أو إلغاؤه أو تقرر عدم الترسية بالفعل.",
    "This offer has been suspended by an admin and cannot be awarded.": "علّق المشرف هذا العرض ولا يمكن ترسيته.",
    "This offer was awarded and has a permanent award record on file.": "تمت ترسية هذا العرض وله سجل ترسية دائم.",
    "A review already exists for this project.": "يوجد تقييم لهذا المشروع بالفعل.",
    "You can only review a project after it's awarded.": "يمكنك تقييم المشروع بعد ترسيته فقط.",
    "This project has not been awarded.": "لم تتم ترسية هذا المشروع.",
    "This project has no award record to review against.": "لا يوجد سجل ترسية لهذا المشروع لتقييمه.",
    # --- offers ---
    "Bidding on this project is closed.": "تقديم العروض على هذا المشروع مغلق.",
    "Bidding on this project has closed.": "أُغلق تقديم العروض على هذا المشروع.",
    "Bidding on this project has closed, so this offer can no longer be withdrawn.": "أُغلق تقديم العروض على هذا المشروع، لذا لا يمكن سحب هذا العرض.",
    "This project has been suspended and is not accepting offers.": "تم تعليق هذا المشروع ولا يقبل العروض.",
    "Enter a valid bid amount.": "أدخل قيمة عرض صحيحة.",
    "Give a rate for every item listed in the requirement, once each.": "أدخل سعر وحدة لكل بند مدرج في الطلب، مرة واحدة لكل بند.",
    "No offer to withdraw.": "لا يوجد عرض لسحبه.",
    "This offer has already been withdrawn.": "تم سحب هذا العرض بالفعل.",
    "This requirement doesn't ask for that document.": "هذا الطلب لا يطلب هذا المستند.",
    "Offer not found.": "العرض غير موجود.",
    "Bids on a sealed tender can't be edited until it has opened.": "لا يمكن تعديل العروض في مناقصة مختومة حتى تُفتح.",
    "This tender has been decided, so its bids are part of the permanent record and can't be edited.": "تم البت في هذه المناقصة، لذا أصبحت عروضها جزءًا من السجل الدائم ولا يمكن تعديلها.",
    "This provider isn't eligible for this requirement, so the bid can't be changed.": "مقدم الخدمة هذا غير مؤهل لهذا الطلب، لذا لا يمكن تغيير العرض.",
    "This requirement is priced per item: correct the item rates and the total follows.": "هذا الطلب مسعّر حسب البنود: صحّح أسعار البنود ويتبعها الإجمالي.",
    "This requirement is priced as one total: correct the amount.": "هذا الطلب مسعّر كمبلغ إجمالي واحد: صحّح المبلغ.",
    "Not available while this tender is sealed and still open.": "غير متاح ما دامت المناقصة مختومة ومفتوحة.",
    # --- eligibility ---
    "You aren't eligible to respond to this requirement.": "أنت غير مؤهل لتقديم عرض لهذا الطلب.",
    "This requirement is open to providers registered as an organization only; your account is registered as an individual.": "هذا الطلب متاح لمقدمي الخدمة المسجلين كجهات فقط؛ حسابك مسجل كفرد.",
    # --- questions ---
    "Only service providers can ask clarification questions.": "يمكن لمقدمي الخدمة فقط طرح أسئلة الاستيضاح.",
    "Enter a question.": "أدخل سؤالًا.",
    "Enter an answer.": "أدخل إجابة.",
    "Question not found.": "السؤال غير موجود.",
    "This question has already been answered.": "تمت الإجابة على هذا السؤال بالفعل.",
    "This requirement doesn't accept questions.": "هذا الطلب لا يقبل الأسئلة.",
    "Questions for this requirement have closed.": "أُغلقت الأسئلة لهذا الطلب.",
    "Questions can only be asked while offers are open.": "يمكن طرح الأسئلة فقط والعروض مفتوحة.",
    "Questions and answers for this requirement have closed.": "أُغلقت الأسئلة والأجوبة لهذا الطلب.",
    # --- categories, admin ---
    "A category with that name already exists.": "توجد فئة بهذا الاسم بالفعل.",
    "Category not found.": "الفئة غير موجودة.",
    "Enter a name.": "أدخل اسمًا.",
    "Owner not found.": "المالك غير موجود.",
    "Service provider not found.": "مقدم الخدمة غير موجود.",
    "Notification not found.": "الإشعار غير موجود.",
    "This owner has posted projects.": "نشر هذا المالك مشاريع.",
    "This project has offers on it.": "يوجد عروض على هذا المشروع.",
    "This service provider has completed projects with reviews on record.": "لمقدم الخدمة هذا مشاريع مكتملة لها تقييمات مسجلة.",
    "Suspend it instead of deleting it.": "علّقه بدلًا من حذفه.",
    "Suspend it instead of deleting it, to keep that bid history intact for the service providers involved.": "علّقه بدلًا من حذفه، للحفاظ على سجل العروض لمقدمي الخدمة المعنيين.",
    "Suspend the account instead of deleting it, to keep that history intact.": "علّق الحساب بدلًا من حذفه للحفاظ على السجل.",
    "Suspend the account instead of deleting it, to keep that project and offer history intact for the service providers involved.": "علّق الحساب بدلًا من حذفه، للحفاظ على سجل المشاريع والعروض لمقدمي الخدمة المعنيين.",
    # --- auth, files, webhooks ---
    "Not authenticated": "لم يتم تسجيل الدخول",
    "Session expired": "انتهت الجلسة",
    "Insufficient permissions": "صلاحيات غير كافية",
    "File not found": "الملف غير موجود",
    "Link expired or invalid": "الرابط منتهي الصلاحية أو غير صالح",
    "Invalid signature": "توقيع غير صالح",
    "Missing signature or webhook secret": "التوقيع أو سر الربط مفقود",
    "Internal error processing webhook": "خطأ داخلي أثناء معالجة الربط",
    "Owner profile not found": "ملف المالك غير موجود",
    "Service provider profile not found": "ملف مقدم الخدمة غير موجود",
    # --- quality warnings ---
    "Add the area (e.g. Salwa), so providers can judge the location without the exact address.": "أضف المنطقة (مثل سلوى) ليتمكن مقدمو الخدمة من تقدير الموقع دون العنوان الدقيق.",
    "Choose the type of work, so the right providers find it.": "اختر نوع العمل ليجده مقدمو الخدمة المناسبون.",
    "No drawings, BOQ or photos are attached.": "لا توجد مخططات أو جدول كميات أو صور مرفقة.",
    "For detailed work, providers usually need them to price accurately.": "في الأعمال التفصيلية يحتاجها مقدمو الخدمة عادةً للتسعير بدقة.",
    "Offers close in under 3 days.": "تُغلق العروض خلال أقل من 3 أيام.",
    "Providers may not have time to visit the site and price properly.": "قد لا يتسع الوقت لمقدمي الخدمة لزيارة الموقع والتسعير بشكل صحيح.",
    "Say roughly when the work should happen (a start date or a duration), so providers can check their availability.": "حدد تقريبًا متى يجب أن يتم العمل (تاريخ بدء أو مدة) ليتحقق مقدمو الخدمة من توفرهم.",
    "The scope is very brief.": "نطاق العمل مختصر جدًا.",
    "Providers price more accurately when they know exactly what's included and what isn't.": "يسعّر مقدمو الخدمة بدقة أكبر عندما يعرفون ما يشمله العمل وما لا يشمله.",
    "The type of work isn't one of the platform's categories, so providers filtering by category won't find it.": "نوع العمل ليس من فئات المنصة، لذا لن يجده من يبحث حسب الفئة.",
    # --- post-publication control (Stage 3.15) ---
    "A change to what providers price needs at least 3 days before offers close.": "يحتاج أي تغيير فيما يسعّره مقدمو الخدمة إلى 3 أيام على الأقل قبل إغلاق العروض.",
    "Extend the deadline in the same change.": "مدّد الموعد النهائي في التغيير نفسه.",
    "No offer to confirm.": "لا يوجد عرض لتأكيده.",
    "Only a paused, still-open requirement can be resumed.": "يمكن استئناف الطلب الموقوف مؤقتًا والمفتوح فقط.",
    "Only an open requirement can be paused.": "يمكن إيقاف الطلب المفتوح مؤقتًا فقط.",
    "The offer deadline has passed, so this requirement can't reopen.": "انتهى موعد إغلاق العروض، لذا لا يمكن إعادة فتح هذا الطلب.",
    "This requirement is already paused.": "هذا الطلب موقوف مؤقتًا بالفعل.",
    "Your offer is already up to date with the requirement.": "عرضك محدّث بالفعل وفق الطلب.",
    "Choose why the requirement is being canceled.": "اختر سبب إلغاء الطلب.",
    "This project can no longer be closed.": "لم يعد من الممكن إغلاق هذا المشروع.",
    # --- billing, misc ---
    "No billing account yet — subscribe first.": "لا يوجد حساب فوترة بعد — اشترك أولًا.",
    "Could not start checkout.": "تعذر بدء الدفع.",
    "Billing isn't configured yet — a Stripe price ID is missing.": "لم يتم إعداد الفوترة بعد — معرّف السعر في Stripe مفقود.",
    "Internal server error.": "خطأ داخلي في الخادم.",
    "Invalid request.": "طلب غير صالح.",
}

_GENERIC_INVALID = {"en": 'Check the value of "{field}".', "ar": "تحقق من قيمة «{field}»."}

_MISSING_PARTS = {
    "a completion period": "مدة الإنجاز",
    "your technical approach": "المنهجية الفنية",
    "acceptance of every declaration": "الموافقة على جميع الإقرارات",
}


def _missing(m: re.Match) -> str:
    parts = []
    for p in m.group(1).split(", "):
        doc = re.fullmatch(r'the "(.+)" document', p)
        parts.append(f'المستند "{doc.group(1)}"' if doc else _MISSING_PARTS.get(p, p))
    return "ينقص عرضك: " + "، ".join(parts) + "."


def _gov(name: str) -> str:
    return GOVERNORATES_AR.get(name, name)


PATTERNS: list[tuple[re.Pattern, object]] = [
    (re.compile(r"^Your offer is missing (.+)\.$"), _missing),
    (re.compile(r'^Item (\d+) \("(.*)"\) has a quantity but no unit\.$'), lambda m: f'البند {m[1]} ("{m[2]}") له كمية بدون وحدة.'),
    (re.compile(r'^Item (\d+) \("(.*)"\) has no quantity, so providers will price it as a lump sum\.$'), lambda m: f'البند {m[1]} ("{m[2]}") بدون كمية، لذا سيسعّره مقدمو الخدمة كمبلغ مقطوع.'),
    (re.compile(r"^Item (\d+) needs a description\.$"), lambda m: f"البند {m[1]} يحتاج إلى وصف."),
    (re.compile(r"^Duration must be between 1 and (\d+) days\.$"), lambda m: f"يجب أن تكون المدة بين 1 و{m[1]} يومًا."),
    (re.compile(r"^The scope of work is too long \(([\d,]+) characters; the limit is ([\d,]+)\)\.$"), lambda m: f"نطاق العمل طويل جدًا ({m[1]} حرفًا؛ الحد {m[2]})."),
    (re.compile(r"^'\.(.+)' is not an allowed file type\. Allowed: (.+)\.$"), lambda m: f"نوع الملف '.{m[1]}' غير مسموح. المسموح: {m[2]}."),
    (re.compile(r"^(.+) requires an expiry date when it is approved\.$"), lambda m: f"يتطلب {m[1]} تاريخ انتهاء عند اعتماده."),
    (re.compile(r"^Request body too large — max (\d+)MB\.$"), lambda m: f"حجم الطلب كبير جدًا — الحد الأقصى {m[1]} ميغابايت."),
    (re.compile(r"^Archive contains too many files \(max (\d+)\)\.$"), lambda m: f"الملف المضغوط يحتوي على ملفات كثيرة جدًا (الحد {m[1]})."),
    (re.compile(r"^Still open: (.+)\.$"), lambda m: f"لا يزال مفتوحًا: {m[1]}."),
    (re.compile(r"^All required documents must be uploaded \(and any correction made\) before submitting for review: (.+)\.$"), lambda m: f"يجب رفع جميع المستندات المطلوبة (وإجراء أي تصحيح) قبل الإرسال للمراجعة: {m[1]}."),
    (re.compile(r'^This requirement needs a platform-approved "(.+)"; your verification doesn\'t include an approved one\.$'), lambda m: f'يتطلب هذا الطلب "{m[1]}" معتمدًا من المنصة؛ لا يتضمن توثيقك مستندًا معتمدًا منه.'),
    (re.compile(r'^This requirement needs a valid "(.+)"; yours expired on (.+)\.$'), lambda m: f'يتطلب هذا الطلب "{m[1]}" ساري المفعول؛ انتهت صلاحية مستندك في {m[2]}.'),
    (re.compile(r'^This requirement is for "(.+)"; your profile doesn\'t list it among your services\.$'), lambda m: f'هذا الطلب لأعمال "{m[1]}"، وهي ليست ضمن الخدمات المدرجة في ملفك.'),
    (re.compile(r"^This requirement is in (.+), which isn't among the governorates your profile says you serve\.$"), lambda m: f"هذا الطلب في محافظة {_gov(m[1])}، وهي ليست ضمن المحافظات التي يذكر ملفك أنك تخدمها."),
    (re.compile(r'^Check the value of "(.+)"\.$'), lambda m: _GENERIC_INVALID["ar"].format(field=m[1])),
]

# Split a composite message into sentences -- but not after "e.g.".
_SENTENCE = re.compile(r"(?<!e\.g)(?<=[.!?])\s+(?=[A-Z\"'(])")


def _one(text: str) -> str | None:
    if text in AR:
        return AR[text]
    for pattern, render in PATTERNS:
        m = pattern.match(text)
        if m:
            return render(m)
    return None


def translate(text: str, language: str | None = None) -> str:
    language = language or current_language.get()
    if language != "ar" or not isinstance(text, str):
        return text
    whole = _one(text)
    if whole is not None:
        return whole
    return " ".join(_one(s) or s for s in _SENTENCE.split(text))


def language_from(accept_language: str | None) -> str:
    return "ar" if (accept_language or "").strip().lower().startswith("ar") else "en"


def generic_invalid(field: str) -> str:
    return _GENERIC_INVALID["en"].format(field=field)
