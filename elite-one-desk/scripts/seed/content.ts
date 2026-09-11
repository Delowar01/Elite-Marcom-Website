/**
 * Starting content for the homepage and the standing pages.
 *
 * Each entry is a section row: a block type from `lib/cms/blocks.ts` and the
 * values for its declared fields. Localised fields are `{ en, ar }`; Arabic is
 * written where it is short and load-bearing (headlines, buttons, labels) and
 * left empty on long body copy so it falls back to English until a translator
 * fills it in.
 */

type L = { en: string; ar: string };
const t = (en: string, ar = ""): L => ({ en, ar });

export type SeedSection = {
  blockType: string;
  animation?: string;
  values: Record<string, unknown>;
};

export const HOME_SECTIONS: SeedSection[] = [
  {
    blockType: "hero",
    values: {
      eyebrow: t("Riyadh · Saudi Arabia", "الرياض · المملكة العربية السعودية"),
      words: [
        { label: t("Travel.", "سفر.") },
        { label: t("Business.", "أعمال.") },
        { label: t("Government Services.", "خدمات حكومية.") },
      ],
      headline: t("One Desk.", "مكتب واحد."),
      lead: t(
        "One destination for travel, business setup, company formation, residency, licensing and government-related support.",
        "وجهة واحدة للسفر وتأسيس الأعمال وتسجيل الشركات والإقامة والتراخيص والدعم المرتبط بالجهات الحكومية.",
      ),
      primaryCtaLabel: t("Request a Service", "اطلب خدمة"),
      primaryCtaHref: "/contact",
      secondaryCtaLabel: t("Explore Services", "استعرض الخدمات"),
      secondaryCtaHref: "/services",
      backgroundImage: null,
    },
  },
  {
    blockType: "quick-links",
    values: {
      title: t("Start where you need us", "ابدأ من حيث تحتاجنا"),
      intro: t("", ""),
      links: [
        { label: t("Plan a Trip", "خطّط لرحلة"), href: "/services/travel-tourism", icon: "plane" },
        { label: t("Visa Assistance", "المساعدة في التأشيرات"), href: "/services/travel-tourism/schengen-visa-assistance", icon: "passport" },
        { label: t("Investor Licence", "رخصة المستثمر"), href: "/services/business-setup/investor-license-assistance", icon: "briefcase" },
        { label: t("Start a Company", "تأسيس شركة"), href: "/services/company-formation", icon: "building" },
        { label: t("Iqama & Khidamat", "الإقامة والمعاملات"), href: "/services/general-services", icon: "idCard" },
        { label: t("Renew a Licence", "تجديد ترخيص"), href: "/services/license-renewal", icon: "refresh" },
        { label: t("Premium Residency", "الإقامة المميزة"), href: "/services/government-relations/premium-residency-consultation", icon: "shield" },
        { label: t("TGA Services", "خدمات النقل"), href: "/services/government-relations/tga-license-consultation", icon: "route" },
      ],
    },
  },
  {
    blockType: "one-desk",
    values: {
      eyebrow: t("The idea", "الفكرة"),
      title: t("One Desk. Multiple Solutions.", "مكتب واحد. حلول متعددة."),
      body: t(
        "Most people dealing with travel, a company and a residency file end up dealing with three different offices — and repeating themselves to each of them. Elite One Desk is the other arrangement: travel, business, residency, licensing and government-related work co-ordinated through one professional point of contact who already knows your file.",
        "من يتعامل مع السفر وشركة وملف إقامة ينتهي به الأمر غالبًا إلى ثلاثة مكاتب مختلفة — ويعيد شرح وضعه لكل منها. إيليت ون ديسك هو الترتيب الآخر: السفر والأعمال والإقامة والتراخيص والمعاملات الحكومية تُنسَّق عبر نقطة تواصل مهنية واحدة تعرف ملفك مسبقًا.",
      ),
      paths: [
        { label: t("Travel & tourism", "السفر والسياحة") },
        { label: t("Business setup", "تأسيس الأعمال") },
        { label: t("Company formation", "تأسيس الشركات") },
        { label: t("Iqama & khidamat", "الإقامة والمعاملات") },
        { label: t("Licence renewal", "تجديد التراخيص") },
        { label: t("Government relations", "العلاقات الحكومية") },
      ],
      ctaLabel: t("About Elite One Desk", "عن إيليت ون ديسك"),
      ctaHref: "/about",
    },
  },
  {
    blockType: "service-grid",
    values: {
      eyebrow: t("What we do", "ما نقدمه"),
      title: t("Six categories, one point of contact", "ست فئات، ونقطة تواصل واحدة"),
      intro: t(
        "Each category has its own specialists. You still speak to one person.",
        "لكل فئة مختصوها. ومع ذلك تتحدث أنت إلى شخص واحد.",
      ),
      limit: 6,
      showCounts: true,
    },
  },
  {
    blockType: "featured-service",
    values: {
      eyebrow: t("Investor licence assistance", "المساعدة في رخصة المستثمر"),
      title: t("Start your investment journey in Saudi Arabia.", "ابدأ رحلتك الاستثمارية في المملكة."),
      body: t(
        "An investor licence is the step everything else depends on — the company, the residency, the bank account. We assess eligibility first, tell you plainly where you stand, then prepare and submit the file.",
        "رخصة المستثمر هي الخطوة التي يعتمد عليها كل ما بعدها — الشركة والإقامة والحساب البنكي. نبدأ بتقييم الأهلية ونوضح لك موقعك بصراحة، ثم نُعدّ الملف ونقدّمه.",
      ),
      points: [
        { label: t("Investor licence assistance", "المساعدة في رخصة المستثمر") },
        { label: t("Investor licence consultation", "استشارة رخصة المستثمر") },
        { label: t("Investor eligibility assessment", "تقييم أهلية المستثمر") },
        { label: t("Investor documentation support", "دعم مستندات المستثمر") },
        { label: t("Application assistance and follow-up", "المساعدة في التقديم والمتابعة") },
        { label: t("Licence renewal when it comes due", "التجديد عند استحقاقه") },
      ],
      ctaLabel: t("Talk to a Business Setup Advisor", "تحدّث إلى مستشار تأسيس أعمال"),
      ctaHref: "/services/business-setup/investor-license-assistance",
      image: null,
    },
  },
  {
    blockType: "travel-feature",
    values: {
      eyebrow: t("Travel & tourism", "السفر والسياحة"),
      title: t("Travel arranged by someone who answers the phone", "سفر يُنسّقه شخص يردّ على الهاتف"),
      body: t(
        "Flights, hotels, transfers, tours and the visa paperwork underneath them — booked by a coordinator who stays with the trip from the first enquiry to the return flight.",
        "التذاكر والفنادق والتنقلات والجولات وأوراق التأشيرة المرتبطة بها — يحجزها منسّق يبقى مع الرحلة من أول استفسار حتى العودة.",
      ),
      capabilities: [
        { label: t("Flights", "تذاكر الطيران") },
        { label: t("Hotels", "الفنادق") },
        { label: t("International tours", "الجولات الدولية") },
        { label: t("Holiday packages", "باقات العطلات") },
        { label: t("Visa assistance", "المساعدة في التأشيرات") },
        { label: t("Corporate travel", "سفر الشركات") },
        { label: t("Cruises", "الرحلات البحرية") },
        { label: t("Custom itineraries", "برامج مخصصة") },
      ],
      ctaLabel: t("Explore travel services", "استعرض خدمات السفر"),
      ctaHref: "/services/travel-tourism",
      image: null,
    },
  },
  {
    blockType: "egypt-feature",
    values: {
      eyebrow: t("Destination", "وجهة"),
      title: t("Discover Egypt", "اكتشف مصر"),
      body: t(
        "Cairo, the Giza plateau, a Nile sailing and the Red Sea — as a prepared programme or built around your own dates.",
        "القاهرة وهضبة الجيزة ورحلة نيلية والبحر الأحمر — كبرنامج جاهز أو مُعدّ حسب تواريخك.",
      ),
      destinations: [
        { label: t("Cairo", "القاهرة"), note: t("Islamic and Coptic quarters, Khan el-Khalili", "القاهرة الإسلامية والقبطية وخان الخليلي") },
        { label: t("Giza Pyramids", "أهرامات الجيزة"), note: t("The plateau and the Sphinx with a licensed guide", "الهضبة وأبو الهول مع مرشد مرخّص") },
        { label: t("Egyptian Museum", "المتحف المصري"), note: t("Guided visit, tickets arranged", "زيارة مع مرشد وتذاكر مُرتّبة") },
        { label: t("Nile Cruise", "رحلة نيلية"), note: t("Luxor to Aswan, excursions at each stop", "من الأقصر إلى أسوان مع جولات في كل محطة") },
        { label: t("Sharm El Sheikh", "شرم الشيخ"), note: t("Diving, snorkelling and desert days", "غوص وسنوركل ورحلات صحراوية") },
        { label: t("Hurghada", "الغردقة"), note: t("Red Sea resorts with transfers", "منتجعات البحر الأحمر مع التنقلات") },
      ],
      primaryCtaLabel: t("View Egypt packages", "عرض برامج مصر"),
      primaryCtaHref: "/packages",
      secondaryCtaLabel: t("Request a custom package", "اطلب برنامجًا مخصصًا"),
      secondaryCtaHref: "/contact",
      image: null,
    },
  },
  {
    blockType: "video-showcase",
    values: {
      eyebrow: t("Watch", "شاهد"),
      title: t("Elite One Desk on video", "إيليت ون ديسك بالفيديو"),
      intro: t(
        "Short films about the destinations we send people to and the services we handle.",
        "مقاطع قصيرة عن الوجهات التي نرسل إليها والخدمات التي نتولاها.",
      ),
      category: "",
      limit: 6,
    },
  },
  {
    blockType: "process",
    values: {
      eyebrow: t("How it works", "كيف نعمل"),
      title: t("Five steps, and one person who knows where yours is", "خمس خطوات، وشخص واحد يعرف أين وصل ملفك"),
      steps: [
        { label: t("Choose your service", "اختر خدمتك"), text: t("Tell us what you need — or describe the situation and let us tell you which service it is.", "أخبرنا بما تحتاجه — أو اشرح وضعك ودعنا نحدد الخدمة المناسبة.") },
        { label: t("Speak with our team", "تحدّث مع فريقنا"), text: t("A short conversation to confirm what applies to you and what it will involve.", "محادثة قصيرة لتأكيد ما ينطبق عليك وما يتطلبه الأمر.") },
        { label: t("Submit your requirements", "قدّم متطلباتك"), text: t("We send a checklist. You send documents once, not to three different offices.", "نرسل لك قائمة بالمطلوب. ترسل مستنداتك مرة واحدة، لا إلى ثلاثة مكاتب.") },
        { label: t("We coordinate the process", "ننسّق الإجراءات"), text: t("Preparation, submission and follow-up with the relevant parties on your behalf.", "الإعداد والتقديم والمتابعة مع الجهات المعنية نيابةً عنك.") },
        { label: t("Track and complete", "المتابعة والإنجاز"), text: t("You get updates as the file moves, and a named contact to ask.", "تصلك التحديثات مع تقدّم الملف، ولديك جهة اتصال محددة تسألها.") },
      ],
    },
  },
  {
    blockType: "why-us",
    values: {
      eyebrow: t("Why Elite One Desk", "لماذا إيليت ون ديسك"),
      title: t("What actually changes when it is all one desk", "ما الذي يتغيّر فعلًا حين يكون كل شيء في مكتب واحد"),
      intro: t("", ""),
      points: [
        { label: t("One point of contact", "نقطة تواصل واحدة"), text: t("The same person across your travel, your company and your residency file.", "الشخص نفسه لسفرك وشركتك وملف إقامتك.") },
        { label: t("Multiple service categories", "فئات خدمات متعددة"), text: t("Six categories under one roof, so a request rarely has to go elsewhere.", "ست فئات تحت سقف واحد، فنادرًا ما يحتاج طلبك إلى جهة أخرى.") },
        { label: t("Professional coordination", "تنسيق مهني"), text: t("Documents prepared before a step opens, not after it has been rejected.", "المستندات تُجهَّز قبل بدء الخطوة، لا بعد رفضها.") },
        { label: t("Saudi market knowledge", "معرفة بالسوق السعودي"), text: t("Familiar with the portals, the sequencing and what each authority expects to see.", "إلمام بالبوابات وترتيب الخطوات وما تتوقعه كل جهة.") },
        { label: t("Travel and business together", "السفر والأعمال معًا"), text: t("An investor who also needs flights and a family visa is one conversation here.", "المستثمر الذي يحتاج أيضًا إلى تذاكر وتأشيرة عائلية هو محادثة واحدة هنا.") },
        { label: t("Corporate and individual", "للشركات والأفراد"), text: t("A single traveller and a company with fifty employees are both served properly.", "المسافر الفرد والشركة بخمسين موظفًا يُخدمان بالجودة نفسها.") },
      ],
    },
  },
  {
    blockType: "testimonials",
    values: {
      eyebrow: t("Clients", "عملاؤنا"),
      title: t("In their words", "بكلماتهم"),
      limit: 8,
    },
  },
  {
    blockType: "faq",
    values: {
      eyebrow: t("Questions", "أسئلة"),
      title: t("Before you get in touch", "قبل أن تتواصل معنا"),
      scope: "global",
      limit: 8,
    },
  },
  {
    blockType: "final-cta",
    values: {
      title: t("Whatever you need. Start at one desk.", "مهما كان ما تحتاجه. ابدأ من مكتب واحد."),
      body: t(
        "Tell us what you are trying to do and we will tell you which service it is, what it needs and how long it usually takes.",
        "أخبرنا بما تحاول إنجازه وسنخبرك بالخدمة المناسبة ومتطلباتها والمدة المعتادة لها.",
      ),
      primaryCtaLabel: t("Request a Service", "اطلب خدمة"),
      primaryCtaHref: "/contact",
      showWhatsapp: true,
    },
  },
];

export const PAGE_SECTIONS: Record<string, SeedSection[]> = {
  about: [
    {
      blockType: "page-hero",
      values: {
        eyebrow: t("About us", "من نحن"),
        title: t("One contact. Multiple solutions.", "جهة تواصل واحدة. حلول متعددة."),
        lead: t(
          "Elite One Desk exists because travel, business and government paperwork are almost never separate problems — and almost always handled as if they were.",
          "وُجد إيليت ون ديسك لأن السفر والأعمال والمعاملات الحكومية نادرًا ما تكون مشكلات منفصلة — ومع ذلك تُعالَج دائمًا وكأنها كذلك.",
        ),
        backgroundImage: null,
      },
    },
    {
      blockType: "rich-text",
      values: {
        eyebrow: t("Who we are", "من نحن"),
        title: t("An independent service provider, based in Saudi Arabia", "مزوّد خدمات مستقل مقره المملكة العربية السعودية"),
        body: t(
          "<p>Elite One Desk co-ordinates travel, business setup, company formation, residency and licensing work for individuals and companies in the Kingdom. We are an independent service provider: we prepare, submit and follow up on your behalf. We are not a government authority, and every approval rests with the relevant one.</p><p>What we offer is coordination. One person who has your file, knows which step comes next, and can answer the question you were about to ask three different offices.</p>",
          "",
        ),
      },
    },
    {
      blockType: "image-text",
      values: {
        eyebrow: t("Mission", "رسالتنا"),
        title: t("Make one desk enough", "أن يكون مكتب واحد كافيًا"),
        body: t(
          "<p>Our mission is narrow on purpose: to be the single point of contact that makes the rest unnecessary. A client should be able to describe a situation once — a move, an investment, a trip, a renewal — and have the parts that follow handled without repeating themselves.</p><h3>Vision</h3><p>To be the first call for anyone arriving in Saudi Arabia to visit, to invest or to build something — and for anyone already here who would rather deal with one desk than six.</p>",
          "",
        ),
        image: null,
        imageSide: "start",
        ctaLabel: t("See our services", "اطّلع على خدماتنا"),
        ctaHref: "/services",
      },
    },
    {
      blockType: "why-us",
      values: {
        eyebrow: t("Values", "قيمنا"),
        title: t("How we work", "كيف نعمل"),
        intro: t("", ""),
        points: [
          { label: t("Say what is actually possible", "نقول ما هو ممكن فعلًا"), text: t("If a file is unlikely to succeed, you hear that before you spend money on it.", "إذا كان الملف غير مرجّح النجاح، ستعرف ذلك قبل أن تنفق عليه.") },
          { label: t("Prepare before submitting", "التجهيز قبل التقديم"), text: t("Most rejections are document problems. Those get solved first.", "معظم حالات الرفض سببها المستندات. نعالجها أولًا.") },
          { label: t("One file, one owner", "ملف واحد ومسؤول واحد"), text: t("Your request has a named person, not a shared inbox.", "لطلبك شخص محدد، لا بريد مشترك.") },
          { label: t("No guarantees we cannot give", "لا ضمانات لا نملكها"), text: t("Government and consular decisions are theirs. We do not promise otherwise.", "قرارات الجهات الحكومية والقنصلية تعود إليها. ولا نعد بغير ذلك.") },
        ],
      },
    },
    { blockType: "stats", values: { title: t("", ""), items: [] } },
    {
      blockType: "final-cta",
      values: {
        title: t("Start with a conversation", "ابدأ بمحادثة"),
        body: t("Describe what you are trying to do. We will tell you what it involves.", "اشرح ما تحاول إنجازه، وسنوضح لك ما يتطلبه."),
        primaryCtaLabel: t("Request a Service", "اطلب خدمة"),
        primaryCtaHref: "/contact",
        showWhatsapp: true,
      },
    },
  ],
  contact: [
    {
      blockType: "page-hero",
      values: {
        eyebrow: t("Contact", "تواصل معنا"),
        title: t("Tell us what you need", "أخبرنا بما تحتاجه"),
        lead: t(
          "Send the form and an advisor will come back to you, or reach us directly on WhatsApp, phone or email.",
          "أرسل النموذج وسيعاود أحد المستشارين التواصل معك، أو راسلنا مباشرةً عبر واتساب أو الهاتف أو البريد.",
        ),
        backgroundImage: null,
      },
    },
    {
      blockType: "contact-details",
      values: {
        title: t("Get in touch", "ابقَ على تواصل"),
        intro: t("", ""),
        showMap: true,
        showForm: true,
      },
    },
    {
      blockType: "faq",
      values: {
        eyebrow: t("Questions", "أسئلة"),
        title: t("Common questions", "أسئلة متكررة"),
        scope: "global",
        limit: 6,
      },
    },
  ],
  privacy: [
    {
      blockType: "page-hero",
      values: {
        eyebrow: t("Legal", "قانوني"),
        title: t("Privacy Policy", "سياسة الخصوصية"),
        lead: t("How we handle the information you send us.", "كيف نتعامل مع المعلومات التي ترسلها إلينا."),
        backgroundImage: null,
      },
    },
    {
      blockType: "rich-text",
      values: {
        eyebrow: t("", ""),
        title: t("", ""),
        body: t(
          "<p>This page describes how Elite One Desk handles personal information submitted through this website. It is a starting draft: review it with your legal adviser and edit it in the admin panel before launch.</p><h3>What we collect</h3><p>When you send an enquiry we collect the name, contact details and the description of what you need that you choose to give us, together with the page you sent it from and, where present, the campaign parameters in the address. We do not ask for identity documents, passport numbers or payment details through this website.</p><h3>Why we hold it</h3><p>Enquiry details are used to answer your request and to follow up about it. They are not sold, and they are not shared with third parties except where doing so is part of delivering the service you asked for.</p><h3>Analytics</h3><p>Where an analytics service is configured by the site owner, it is loaded only after the page has become interactive and is used to understand which pages are useful. IP anonymisation is enabled where the service supports it.</p><h3>Retention and your rights</h3><p>Enquiries are retained while the request is open and for a reasonable period afterwards. To ask what we hold about you, or to ask us to delete it, contact us using the details on the contact page.</p>",
          "",
        ),
      },
    },
  ],
  terms: [
    {
      blockType: "page-hero",
      values: {
        eyebrow: t("Legal", "قانوني"),
        title: t("Terms of Use", "شروط الاستخدام"),
        lead: t("The basis on which this website and our services are offered.", "الأساس الذي يُقدَّم عليه هذا الموقع وخدماتنا."),
        backgroundImage: null,
      },
    },
    {
      blockType: "rich-text",
      values: {
        eyebrow: t("", ""),
        title: t("", ""),
        body: t(
          "<p>This page is a starting draft. Review it with your legal adviser and edit it in the admin panel before launch.</p><h3>What this website is</h3><p>This website describes services offered by Elite One Desk and allows you to enquire about them. Submitting an enquiry does not create a contract; engagement begins when it is agreed in writing between us.</p><h3>Information on this site</h3><p>Service descriptions, requirements and timelines are indicative and change as authorities change their own. Nothing here is legal, immigration or financial advice.</p><h3>Third-party services</h3><p>Where travel, accommodation or insurance is arranged, the supplier's own terms apply alongside ours.</p><h3>Liability</h3><p>We take care over the information published here but do not warrant that it is complete or current at the moment you read it.</p>",
          "",
        ),
      },
    },
  ],
  disclaimer: [
    {
      blockType: "page-hero",
      values: {
        eyebrow: t("Legal", "قانوني"),
        title: t("Disclaimer", "إخلاء المسؤولية"),
        lead: t(
          "What Elite One Desk is, and what remains with the relevant authorities.",
          "ما هو إيليت ون ديسك، وما الذي يبقى بيد الجهات المختصة.",
        ),
        backgroundImage: null,
      },
    },
    {
      blockType: "rich-text",
      values: {
        eyebrow: t("", ""),
        title: t("", ""),
        body: t(
          "<p><strong>Elite One Desk is an independent service provider.</strong> We offer consultation, documentation and application assistance. We are not a government authority, we are not an embassy or consulate, and we do not represent one.</p><h3>Government-related services</h3><p>Applications for licences, permits and residency are decided by the relevant Saudi authorities. Our role is to prepare, submit and follow up. Final approvals, timelines and fees remain with those authorities and can change without notice.</p><h3>Visa services</h3><p>Visa approval is decided by the relevant embassy, consulate or immigration authority. Our assistance does not guarantee that a visa will be issued, and requirements may change between the date you apply and the date a decision is made.</p><h3>No guarantees</h3><p>We do not publish approval rates and we do not promise outcomes. Anyone offering a guaranteed government or visa approval is not describing how these processes work.</p>",
          "",
        ),
      },
    },
  ],
};

/**
 * The header groups nine destinations under six entries: every page named in
 * the brief is present and one click away, but a nine-item bar plus a CTA, a
 * search control and a language switch does not survive 1280px. All of it is
 * editable under Navigation, so flattening it is a drag away.
 */
export const NAVIGATION: Array<{
  menu: "header" | "footer_services" | "footer_company" | "footer_legal";
  label: L;
  href: string;
  children?: Array<{ label: L; href: string }>;
}> = [
  { menu: "header", label: t("Home", "الرئيسية"), href: "/" },
  { menu: "header", label: t("Travel & Tourism", "السفر والسياحة"), href: "/services/travel-tourism" },
  {
    menu: "header",
    label: t("Business", "الأعمال"),
    href: "/services/business-setup",
    children: [
      { label: t("Business Setup", "تأسيس الأعمال"), href: "/services/business-setup" },
      { label: t("Company Formation", "تأسيس الشركات"), href: "/services/company-formation" },
    ],
  },
  {
    menu: "header",
    label: t("Government Services", "الخدمات الحكومية"),
    href: "/services/general-services",
    children: [
      { label: t("General Services", "الخدمات العامة"), href: "/services/general-services" },
      { label: t("License Renewal", "تجديد التراخيص"), href: "/services/license-renewal" },
      { label: t("Government Relations", "العلاقات الحكومية"), href: "/services/government-relations" },
    ],
  },
  { menu: "header", label: t("About Us", "من نحن"), href: "/about" },
  { menu: "header", label: t("Contact", "تواصل"), href: "/contact" },

  { menu: "footer_services", label: t("Travel & Tourism", "السفر والسياحة"), href: "/services/travel-tourism" },
  { menu: "footer_services", label: t("Business Setup", "تأسيس الأعمال"), href: "/services/business-setup" },
  { menu: "footer_services", label: t("Company Formation", "تأسيس الشركات"), href: "/services/company-formation" },
  { menu: "footer_services", label: t("General Services", "الخدمات العامة"), href: "/services/general-services" },
  { menu: "footer_services", label: t("License Renewal", "تجديد التراخيص"), href: "/services/license-renewal" },
  { menu: "footer_services", label: t("Government Relations", "العلاقات الحكومية"), href: "/services/government-relations" },

  { menu: "footer_company", label: t("About Us", "من نحن"), href: "/about" },
  { menu: "footer_company", label: t("All Services", "جميع الخدمات"), href: "/services" },
  { menu: "footer_company", label: t("Travel Packages", "البرامج السياحية"), href: "/packages" },
  { menu: "footer_company", label: t("Contact", "تواصل"), href: "/contact" },

  { menu: "footer_legal", label: t("Privacy Policy", "سياسة الخصوصية"), href: "/privacy" },
  { menu: "footer_legal", label: t("Terms", "الشروط"), href: "/terms" },
  { menu: "footer_legal", label: t("Disclaimer", "إخلاء المسؤولية"), href: "/disclaimer" },
];

export const FAQS: Array<{ q: L; a: L }> = [
  {
    q: t("Is Elite One Desk a government office?", "هل إيليت ون ديسك جهة حكومية؟"),
    a: t(
      "<p>No. Elite One Desk is an independent service provider. We prepare documents, submit applications and follow them up on your behalf. Every approval is decided by the relevant authority, embassy or consulate.</p>",
      "<p>لا. إيليت ون ديسك مزوّد خدمات مستقل. نُعدّ المستندات ونقدّم الطلبات ونتابعها نيابةً عنك. وكل موافقة تصدر عن الجهة أو السفارة أو القنصلية المختصة.</p>",
    ),
  },
  {
    q: t("Can you guarantee my visa or licence will be approved?", "هل تضمنون الموافقة على التأشيرة أو الرخصة؟"),
    a: t(
      "<p>No, and nobody legitimately can. What we can do is tell you honestly whether an application is likely to succeed before you spend on it, and make sure the file that goes in is complete and correctly presented.</p>",
      "<p>لا، ولا يستطيع أحد ذلك بشكل مشروع. ما نستطيع فعله هو إخبارك بصراحة باحتمالية نجاح الطلب قبل أن تنفق عليه، وضمان أن الملف المقدَّم مكتمل ومعروض بشكل صحيح.</p>",
    ),
  },
  {
    q: t("Do you work with individuals, or only companies?", "هل تتعاملون مع الأفراد أم الشركات فقط؟"),
    a: t(
      "<p>Both. A single traveller booking a trip and a company setting up in the Kingdom are handled by the same desk, with the same follow-up.</p>",
      "<p>الاثنان معًا. المسافر الفرد الذي يحجز رحلة، والشركة التي تؤسس في المملكة، يتعامل معهما المكتب نفسه وبالمتابعة نفسها.</p>",
    ),
  },
  {
    q: t("How long does an investor licence take?", "كم تستغرق رخصة المستثمر؟"),
    a: t(
      "<p>It depends on the activity, the shareholding structure and how quickly the corporate documents can be attested. We give you a realistic range for your specific case at the consultation rather than a headline figure here.</p>",
      "<p>يعتمد ذلك على النشاط وهيكل الملكية وسرعة تصديق وثائق الشركة. نعطيك نطاقًا واقعيًا لحالتك تحديدًا خلال الاستشارة بدلًا من رقم عام هنا.</p>",
    ),
  },
  {
    q: t("What is the difference between General Services and visa services?", "ما الفرق بين الخدمات العامة وخدمات التأشيرات؟"),
    a: t(
      "<p>General Services — khidamat and Iqama — is residency and employee paperwork inside Saudi Arabia: issuing and renewing an Iqama, transfers, exit and re-entry, Muqeem and Qiwa. Visa services under Travel &amp; Tourism are about travelling abroad: Schengen, UK, US and other visit visas.</p>",
      "<p>الخدمات العامة — الخدمات والإقامة — هي معاملات الإقامة والموظفين داخل المملكة: إصدار الإقامة وتجديدها ونقل الكفالة والخروج والعودة ومقيم وقوى. أما خدمات التأشيرات ضمن السفر والسياحة فتخص السفر إلى الخارج: شنغن وبريطانيا وأمريكا وغيرها.</p>",
    ),
  },
  {
    q: t("How do I know what my request will cost?", "كيف أعرف تكلفة طلبي؟"),
    a: t(
      "<p>We quote after we understand the case, because the government fees involved differ by activity, nationality and category. Send an enquiry with a short description and you will get a written breakdown rather than a number over the phone.</p>",
      "<p>نقدّم عرض السعر بعد فهم الحالة، لأن الرسوم الحكومية تختلف باختلاف النشاط والجنسية والفئة. أرسل استفسارًا مع وصف موجز وستصلك تفاصيل مكتوبة بدلًا من رقم عبر الهاتف.</p>",
    ),
  },
];
