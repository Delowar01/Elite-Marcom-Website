/**
 * The service catalogue as delivered.
 *
 * Everything here is editable in the panel afterwards — this is the starting
 * content, not a fixture. Copy is written to be usable as-is: no lorem ipsum,
 * and nothing that claims a licence, a partnership, an approval rate or a track
 * record the business has not given us (§47).
 *
 * Arabic: category, subcategory and service *names* are translated, because a
 * visitor switching language must still be able to navigate. The longer body
 * copy is left empty so it falls back to English rather than shipping a machine
 * translation the brief explicitly rules out (§21) — an Arabic copywriter fills
 * those fields in the panel.
 */

export type SeedService = {
  title: string;
  titleAr: string;
  intro: string;
  featured?: boolean;
};

export type SeedSubcategory = {
  slug: string;
  title: string;
  titleAr: string;
  summary: string;
  preset: "general" | "travel" | "visa" | "business" | "iqama";
  services: SeedService[];
};

export type SeedCategory = {
  slug: string;
  title: string;
  titleAr: string;
  tagline: string;
  taglineAr: string;
  summary: string;
  summaryAr: string;
  icon: string;
  ctaLabel: string;
  ctaLabelAr: string;
  subcategories: SeedSubcategory[];
};

export const CATALOG: SeedCategory[] = [
  {
    slug: "travel-tourism",
    title: "Travel & Tourism Services",
    titleAr: "خدمات السفر والسياحة",
    tagline: "Flights, stays, tours and visa support",
    taglineAr: "تذاكر وإقامة وجولات ودعم التأشيرات",
    summary:
      "Tickets, hotels, transfers, tours and the visa paperwork that goes with them — arranged by one coordinator who stays with the booking from the first enquiry to the return flight.",
    summaryAr:
      "التذاكر والفنادق والتنقلات والجولات وأوراق التأشيرة المرتبطة بها — ينسّقها شخص واحد يتابع الحجز من أول استفسار حتى رحلة العودة.",
    icon: "plane",
    ctaLabel: "Plan your trip",
    ctaLabelAr: "خطّط لرحلتك",
    subcategories: [
      {
        slug: "travel-holiday",
        title: "Travel & Holiday Services",
        titleAr: "خدمات السفر والعطلات",
        summary: "Booking, transfers, insurance and itineraries for individuals, families and companies.",
        preset: "travel",
        services: [
          { title: "Air Ticket Booking", titleAr: "حجز تذاكر الطيران", intro: "Economy through business class on scheduled carriers, with fare options compared before anything is issued." },
          { title: "Hotel Reservation", titleAr: "حجز الفنادق", intro: "Rooms held in the areas you actually need to be in, with cancellation terms explained before you confirm." },
          { title: "International Tour Packages", titleAr: "برامج سياحية دولية", intro: "Multi-city programmes combining flights, hotels, transfers and guided days into one itinerary." },
          { title: "Holiday Packages", titleAr: "باقات العطلات", intro: "Prepared holiday programmes you can take as they are or adjust to your dates, budget and party size." },
          { title: "Airport Transfer", titleAr: "التنقل من وإلى المطار", intro: "Private arrival and departure transfers arranged with your flight times, so nobody waits at the kerb." },
          { title: "Cruise Booking", titleAr: "حجز الرحلات البحرية", intro: "Cabin selection, sailing dates and the flights and hotel nights either side of the cruise." },
          { title: "Travel Insurance", titleAr: "تأمين السفر", intro: "Cover arranged to match the trip and, where the destination requires it, the visa application." },
          { title: "Customized Travel Itinerary", titleAr: "برنامج سفر مخصص", intro: "A day-by-day plan built around your dates, pace and interests rather than a fixed departure." },
          { title: "Family Tour Packages", titleAr: "برامج سياحية عائلية", intro: "Programmes paced for children and older travellers, with room configurations and transfers to match." },
          { title: "Group Tour Packages", titleAr: "برامج سياحية للمجموعات", intro: "Co-ordinated travel for groups, with a single point of contact and one consolidated itinerary." },
          { title: "Corporate Travel Services", titleAr: "خدمات سفر الشركات", intro: "Business travel handled against your policy, with reporting and consistent handling across bookings." },
          { title: "Attraction & Activity Tickets", titleAr: "تذاكر المعالم والأنشطة", intro: "Entry tickets, tours and activities reserved ahead of arrival so the day is not spent queueing." },
        ],
      },
      {
        slug: "visa-services",
        title: "Visa Services",
        titleAr: "خدمات التأشيرات",
        summary: "Documentation, appointments and application support for tourist and visit visas.",
        preset: "visa",
        services: [
          { title: "Schengen Visa Assistance", titleAr: "المساعدة في تأشيرة شنغن", intro: "Document checklist, appointment booking and application review for Schengen area travel.", featured: true },
          { title: "USA Visit Visa Assistance", titleAr: "المساعدة في تأشيرة زيارة أمريكا", intro: "Form preparation, appointment scheduling and interview preparation for a US visit visa." },
          { title: "UK Visa Assistance", titleAr: "المساعدة في تأشيرة بريطانيا", intro: "Online application support, supporting documents and biometrics appointment for UK travel." },
          { title: "Canada Visa Assistance", titleAr: "المساعدة في تأشيرة كندا", intro: "Application preparation and document assembly for a Canadian temporary resident visa." },
          { title: "Australia Visa Assistance", titleAr: "المساعدة في تأشيرة أستراليا", intro: "Guidance through the online lodgement and the supporting evidence it asks for." },
          { title: "Japan Visa Assistance", titleAr: "المساعدة في تأشيرة اليابان", intro: "Itinerary, guarantor documents and application handling for a Japanese tourist visa." },
          { title: "Tourist Visa Processing", titleAr: "إجراءات التأشيرة السياحية", intro: "End-to-end handling of a tourist visa file for destinations that allow agent submission." },
          { title: "Visit Visa Services", titleAr: "خدمات تأشيرة الزيارة", intro: "Family and friend visit applications, including invitation and sponsorship paperwork." },
          { title: "Visa Documentation Support", titleAr: "دعم مستندات التأشيرة", intro: "A checked, ordered document set — the single most common reason an application is returned." },
          { title: "Visa Appointment Assistance", titleAr: "المساعدة في مواعيد التأشيرة", intro: "Appointment slots monitored and booked at the consulate or visa centre for your travel window." },
          { title: "Visa Application Form Assistance", titleAr: "المساعدة في تعبئة نموذج التأشيرة", intro: "Forms completed with you so the answers match your documents and your travel plan." },
          { title: "Travel Insurance for Visa", titleAr: "تأمين السفر لأغراض التأشيرة", intro: "Policies that meet the cover minimums consulates ask for, issued in the format they accept." },
        ],
      },
      {
        slug: "egypt-tours",
        title: "Egypt Tour Packages",
        titleAr: "برامج مصر السياحية",
        summary: "Cairo, Giza, the Nile and the Red Sea — arranged end to end.",
        preset: "travel",
        services: [
          { title: "Egypt Flight Booking", titleAr: "حجز رحلات مصر", intro: "Direct and connecting flights to Cairo, Sharm El Sheikh and Hurghada." },
          { title: "Cairo Hotel Packages", titleAr: "باقات فنادق القاهرة", intro: "Hotel nights in Cairo and Giza, including pyramid-view options, with transfers included." },
          { title: "Cairo City Tour", titleAr: "جولة مدينة القاهرة", intro: "A guided day through Islamic and Coptic Cairo, Khan el-Khalili and the city's older quarters." },
          { title: "Giza Pyramid Tour", titleAr: "جولة أهرامات الجيزة", intro: "The Giza plateau and the Sphinx with a licensed guide, timed to avoid the worst of the heat." },
          { title: "Egyptian Museum Visit", titleAr: "زيارة المتحف المصري", intro: "A guided visit to the museum collections, arranged with tickets and transfers." },
          { title: "Nile River Cruise", titleAr: "رحلة نيلية", intro: "Luxor-to-Aswan sailings with excursions at each stop and the flights to join the boat." },
          { title: "Sharm El Sheikh Tour", titleAr: "جولة شرم الشيخ", intro: "Red Sea stays with diving, snorkelling and desert excursions arranged around them." },
          { title: "Hurghada Holiday Package", titleAr: "باقة عطلة الغردقة", intro: "Beach resorts on the Red Sea coast with transfers and optional excursions." },
          { title: "Airport Pickup & Drop-off", titleAr: "الاستقبال والتوصيل من المطار", intro: "Meet-and-greet on arrival and a return transfer timed to your departure." },
          { title: "Professional Tour Guide", titleAr: "مرشد سياحي محترف", intro: "Licensed Arabic and English speaking guides for individual days or a full programme." },
          { title: "Group Tour Package", titleAr: "برنامج جماعي لمصر", intro: "Egypt programmes co-ordinated for larger parties travelling together." },
          { title: "Honeymoon Package", titleAr: "باقة شهر العسل", intro: "A quieter itinerary combining Cairo, a Nile cruise and Red Sea nights." },
          { title: "Family Tour Package", titleAr: "باقة عائلية لمصر", intro: "An Egypt programme paced for families, with connecting rooms and shorter touring days." },
          { title: "Customized Egypt Tour Package", titleAr: "برنامج مصر مخصص", intro: "Tell us the dates, the party and what you want to see; we build the itinerary around it.", featured: true },
        ],
      },
    ],
  },
  {
    slug: "business-setup",
    title: "Business Setup",
    titleAr: "تأسيس الأعمال",
    tagline: "Investor licensing and market entry",
    taglineAr: "رخص المستثمرين ودخول السوق",
    summary:
      "Support for investors entering the Saudi market: eligibility, documentation, and assistance through the investor licence application and the steps around it.",
    summaryAr:
      "دعم المستثمرين الراغبين في دخول السوق السعودي: تقييم الأهلية وإعداد المستندات والمساعدة في إجراءات رخصة الاستثمار وما يتصل بها.",
    icon: "briefcase",
    ctaLabel: "Get investor licence support",
    ctaLabelAr: "احصل على دعم رخصة المستثمر",
    subcategories: [
      {
        slug: "investor-business-setup",
        title: "Investor & Business Setup",
        titleAr: "المستثمر وتأسيس الأعمال",
        summary: "From the first eligibility question to a submitted investor licence application.",
        preset: "business",
        services: [
          { title: "Investor License Assistance", titleAr: "المساعدة في رخصة المستثمر", intro: "End-to-end assistance with the investor licence: what is required, what to prepare, and how the application is submitted.", featured: true },
          { title: "Investor License Consultation", titleAr: "استشارة رخصة المستثمر", intro: "A working session on licence type, activity classification and the route that fits your plan.", featured: true },
          { title: "Investor Eligibility Assessment", titleAr: "تقييم أهلية المستثمر", intro: "A clear read on where you stand before any fee is spent — what qualifies, and what would need to change." },
          { title: "Investor Documentation Support", titleAr: "دعم مستندات المستثمر", intro: "Corporate documents, attestations and translations assembled in the order the application expects." },
          { title: "Investor License Application Assistance", titleAr: "المساعدة في تقديم طلب رخصة المستثمر", intro: "The application prepared, checked and followed up until a decision is returned." },
          { title: "Business Setup Consultation", titleAr: "استشارة تأسيس الأعمال", intro: "Structure, activity and sequencing — what to do first, and what can wait." },
          { title: "Transportation Activity Support", titleAr: "دعم النشاط النقلي", intro: "Guidance for investors whose activity falls under the transport sector and its own requirements." },
          { title: "TGA Business Setup Consultation", titleAr: "استشارة تأسيس الأعمال لدى الهيئة العامة للنقل", intro: "How transport-sector licensing shapes a setup plan, and what the authority expects to see." },
          { title: "Business Consultation", titleAr: "استشارة أعمال", intro: "A general session for questions that do not fit a single service." },
        ],
      },
    ],
  },
  {
    slug: "company-formation",
    title: "Company Formation",
    titleAr: "تأسيس الشركات",
    tagline: "Registration and incorporation support",
    taglineAr: "دعم التسجيل والتأسيس",
    summary:
      "Registering a company and preparing what it needs to operate: incorporation documents, registration steps and the paperwork between them.",
    summaryAr:
      "تسجيل الشركة وتجهيز ما تحتاجه لمزاولة نشاطها: وثائق التأسيس وخطوات التسجيل والأوراق المرتبطة بها.",
    icon: "building",
    ctaLabel: "Start your company",
    ctaLabelAr: "ابدأ تأسيس شركتك",
    subcategories: [
      {
        slug: "company-formation-registration",
        title: "Company Formation & Registration",
        titleAr: "تأسيس الشركات والتسجيل",
        summary: "Incorporation paperwork and registration, including transport-sector companies.",
        preset: "business",
        services: [
          { title: "Company Registration Assistance", titleAr: "المساعدة في تسجيل الشركة", intro: "Registration handled step by step, with the documents prepared before each stage rather than after.", featured: true },
          { title: "Transport Company Setup Consultation", titleAr: "استشارة تأسيس شركة نقل", intro: "What a transport company needs in addition to a standard commercial registration." },
          { title: "Company Formation Documentation", titleAr: "وثائق تأسيس الشركة", intro: "Articles, resolutions and supporting documents drafted and assembled for submission." },
          { title: "Business Registration Support", titleAr: "دعم التسجيل التجاري", intro: "Commercial registration and the registrations that follow it, tracked to completion." },
          { title: "Transportation Company Formation", titleAr: "تأسيس شركة نقل", intro: "Formation for transport operators, co-ordinated with the sector licensing it depends on." },
        ],
      },
    ],
  },
  {
    slug: "general-services",
    title: "General Services",
    titleAr: "الخدمات العامة",
    tagline: "Khidamat & Iqama services",
    taglineAr: "الخدمات والإقامة",
    summary:
      "Residency and employee paperwork for individuals and companies: Iqama issuance, renewal and transfer, exit and re-entry, and the government portals around them. This is resident documentation, not international visa work.",
    summaryAr:
      "معاملات الإقامة والموظفين للأفراد والشركات: إصدار الإقامة وتجديدها ونقلها، والخروج والعودة، والبوابات الحكومية المرتبطة بها. هذه معاملات إقامة وليست تأشيرات دولية.",
    icon: "idCard",
    ctaLabel: "Get Iqama support",
    ctaLabelAr: "احصل على دعم الإقامة",
    subcategories: [
      {
        slug: "khidamat-iqama",
        title: "Khidamat & Iqama Services",
        titleAr: "خدمات الإقامة والمعاملات",
        summary: "Residency, dependants and employee documentation, including Muqeem, Qiwa and Absher Business.",
        preset: "iqama",
        services: [
          { title: "Iqama Issuance Assistance", titleAr: "المساعدة في إصدار الإقامة", intro: "First-issue residency permits for new arrivals, with the employer-side steps handled alongside." },
          { title: "Iqama Renewal Assistance", titleAr: "المساعدة في تجديد الإقامة", intro: "Renewals prepared ahead of expiry, so a lapse never becomes a fine.", featured: true },
          { title: "Iqama Transfer / Sponsorship Transfer Support", titleAr: "دعم نقل الكفالة", intro: "Sponsorship transfer between employers, with both sides' requirements checked first." },
          { title: "Profession Change Assistance", titleAr: "المساعدة في تغيير المهنة", intro: "Profession amendments on a residency permit, and what has to be in place before one is accepted." },
          { title: "Exit & Re-Entry Services", titleAr: "خدمات الخروج والعودة", intro: "Single and multiple exit and re-entry permits, timed to your travel." },
          { title: "Final Exit Services", titleAr: "خدمات الخروج النهائي", intro: "Final exit processing and the settlement steps that have to be complete before it is issued." },
          { title: "Family / Dependent Iqama Services", titleAr: "خدمات إقامة المرافقين", intro: "Dependant residency for spouses and children, from first issue through renewal." },
          { title: "Employee Documentation Services", titleAr: "خدمات وثائق الموظفين", intro: "Employee files kept complete and current, for companies without an in-house PRO." },
          { title: "Muqeem Services", titleAr: "خدمات مقيم", intro: "Muqeem portal transactions handled on behalf of the employer." },
          { title: "Qiwa Services", titleAr: "خدمات قوى", intro: "Qiwa platform transactions, including contracts and establishment records." },
          { title: "Absher Business Services", titleAr: "خدمات أبشر أعمال", intro: "Absher Business transactions for establishments and their employees." },
          { title: "Labor-related Documentation Support", titleAr: "دعم وثائق العمل", intro: "Labour paperwork prepared to the format the relevant portal expects." },
          { title: "Passport & Residency Documentation Support", titleAr: "دعم وثائق الجوازات والإقامة", intro: "Passport-related residency documentation, including renewals and record updates." },
        ],
      },
    ],
  },
  {
    slug: "license-renewal",
    title: "License Renewal",
    titleAr: "تجديد التراخيص",
    tagline: "Licences and permits, renewed on time",
    taglineAr: "تراخيص وتصاريح تُجدَّد في وقتها",
    summary:
      "Renewals tracked before they expire — transport licences, operating permits, investor licences and Premium Residency — with the compliance documents prepared in advance.",
    summaryAr:
      "تجديدات تُتابَع قبل انتهائها — تراخيص النقل وتصاريح التشغيل ورخص الاستثمار والإقامة المميزة — مع تجهيز مستندات الامتثال مسبقًا.",
    icon: "refresh",
    ctaLabel: "Renew a licence",
    ctaLabelAr: "جدّد ترخيصًا",
    subcategories: [
      {
        slug: "license-permit-renewal",
        title: "License & Permit Renewal",
        titleAr: "تجديد التراخيص والتصاريح",
        summary: "Transport, operating, investor and residency renewals.",
        preset: "business",
        services: [
          { title: "TGA License Renewal Assistance", titleAr: "المساعدة في تجديد رخصة الهيئة العامة للنقل", intro: "Transport General Authority licence renewals, with the compliance file prepared before submission.", featured: true },
          { title: "Transportation License Renewal", titleAr: "تجديد رخصة النقل", intro: "Renewal of transport activity licences and the records they depend on." },
          { title: "Operating Permit Renewal", titleAr: "تجديد تصريح التشغيل", intro: "Operating permits renewed ahead of expiry so activity is never interrupted." },
          { title: "Compliance Documentation for Renewal", titleAr: "مستندات الامتثال للتجديد", intro: "The evidence a renewal asks for, collected and checked before the application opens." },
          { title: "Investor License Renewal Assistance", titleAr: "المساعدة في تجديد رخصة المستثمر", intro: "Investor licence renewals, including the reporting that has to be current first." },
          { title: "Premium Residency Renewal Assistance", titleAr: "المساعدة في تجديد الإقامة المميزة", intro: "Renewal support for Premium Residency holders and their dependants." },
        ],
      },
    ],
  },
  {
    slug: "government-relations",
    title: "Government Relations Services",
    titleAr: "خدمات العلاقات الحكومية",
    tagline: "Premium Residency and TGA support",
    taglineAr: "الإقامة المميزة ودعم الهيئة العامة للنقل",
    summary:
      "Consultation and documentation support for Saudi Premium Residency and Transport General Authority matters. We prepare and submit; the authorities decide.",
    summaryAr:
      "استشارات ودعم في المستندات لبرنامج الإقامة المميزة وشؤون الهيئة العامة للنقل. نحن نُعدّ ونقدّم، والقرار يعود للجهات المختصة.",
    icon: "landmark",
    ctaLabel: "Talk to an advisor",
    ctaLabelAr: "تحدّث إلى مستشار",
    subcategories: [
      {
        slug: "premium-residency",
        title: "Saudi Premium Residency Services",
        titleAr: "خدمات الإقامة المميزة",
        summary: "Eligibility, documents and application support across the Premium Residency categories.",
        preset: "business",
        services: [
          { title: "Premium Residency Consultation", titleAr: "استشارة الإقامة المميزة", intro: "Which Premium Residency category fits your circumstances, and what it would require of you.", featured: true },
          { title: "Eligibility Assessment", titleAr: "تقييم الأهلية", intro: "An honest assessment against the published criteria before an application is started." },
          { title: "Document Preparation", titleAr: "إعداد المستندات", intro: "Certificates, attestations and translations prepared in the form the programme accepts." },
          { title: "Application Assistance", titleAr: "المساعدة في تقديم الطلب", intro: "The application completed, reviewed and tracked through to a decision." },
          { title: "Investment Residency Guidance", titleAr: "إرشاد الإقامة الاستثمارية", intro: "Guidance for applicants qualifying through investment in the Kingdom." },
          { title: "Business Owner Residency Guidance", titleAr: "إرشاد إقامة أصحاب الأعمال", intro: "Guidance for business owners, including what the entity itself has to show." },
          { title: "Real Estate Owner Residency Guidance", titleAr: "إرشاد إقامة ملّاك العقار", intro: "Guidance for applicants qualifying through property ownership." },
          { title: "Special Talent Residency Guidance", titleAr: "إرشاد إقامة الموهبة الخاصة", intro: "Guidance for specialist and talent categories, and the evidence they ask for." },
          { title: "Family Residency Guidance", titleAr: "إرشاد إقامة العائلة", intro: "How dependants are included, and what changes for them once residency is granted." },
        ],
      },
      {
        slug: "tga-services",
        title: "Saudi TGA Services",
        titleAr: "خدمات الهيئة العامة للنقل",
        summary: "Transport General Authority licensing, vehicles, drivers and compliance.",
        preset: "business",
        services: [
          { title: "TGA License Consultation", titleAr: "استشارة رخصة الهيئة العامة للنقل", intro: "Which transport licence applies to your activity, and what the authority expects with it.", featured: true },
          { title: "Vehicle Registration Guidance", titleAr: "إرشاد تسجيل المركبات", intro: "Registering vehicles against a transport licence and keeping the fleet record current." },
          { title: "Driver Documentation Support", titleAr: "دعم وثائق السائقين", intro: "Driver cards, permits and the employment records tied to them." },
          { title: "Operating Permit Assistance", titleAr: "المساعدة في تصاريح التشغيل", intro: "Operating permits prepared and submitted for the activity you are licensed for." },
          { title: "Compliance Documentation Support", titleAr: "دعم مستندات الامتثال", intro: "The documentation the authority asks to see, kept in order between inspections." },
          { title: "Transportation Activity Government Support", titleAr: "الدعم الحكومي لنشاط النقل", intro: "Ongoing coordination for transport operators across the authority's requirements." },
        ],
      },
    ],
  },
];

export const slugify = (value: string): string =>
  value
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/\//g, " ")
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
