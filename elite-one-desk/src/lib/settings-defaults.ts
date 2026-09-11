/**
 * Settings defaults, kept in their own module.
 *
 * The seed script and the admin forms both need this shape, and neither runs
 * inside the Next server runtime — importing it from `settings.ts` would drag
 * `server-only` and a database connection into a plain `tsx` process.
 */
export const SETTINGS_DEFAULTS = {
  brand: {
    siteNameEn: "Elite One Desk",
    siteNameAr: "إيليت ون ديسك",
    taglineEn: "Travel. Business. Government Services. One Desk.",
    taglineAr: "سفر. أعمال. خدمات حكومية. مكتب واحد.",
    legalNameEn: "Elite One Desk",
    legalNameAr: "إيليت ون ديسك",
  },
  contact: {
    phone: "",
    phoneDisplay: "",
    email: "",
    addressEn: "",
    addressAr: "",
    cityEn: "",
    cityAr: "",
    countryEn: "Saudi Arabia",
    countryAr: "المملكة العربية السعودية",
    hoursEn: "",
    hoursAr: "",
    /** Google Maps embed src. Validated on save; empty hides the map. */
    mapEmbedUrl: "",
  },
  whatsapp: {
    enabled: false,
    /** Digits only, international format without "+", e.g. 9665XXXXXXXX. */
    number: "",
    defaultMessageEn: "Hello Elite One Desk, I would like to ask about your services.",
    defaultMessageAr: "مرحبًا إيليت ون ديسك، أود الاستفسار عن خدماتكم.",
    floatingEnabled: true,
  },
  analytics: {
    ga4Id: "",
    gtmId: "",
    metaPixelId: "",
  },
  disclaimers: {
    governmentEn:
      "Elite One Desk is an independent service provider offering consultation, documentation and application assistance. We are not a government authority, and final approvals remain subject to the relevant authorities.",
    governmentAr:
      "إيليت ون ديسك مزوّد خدمات مستقل يقدّم الاستشارة وإعداد المستندات والمساعدة في تقديم الطلبات. نحن لسنا جهة حكومية، وتبقى الموافقات النهائية بيد الجهات المختصة.",
    visaEn:
      "Visa approval is decided by the relevant embassy, consulate or authority. Our assistance does not guarantee issuance, and requirements may change without notice.",
    visaAr:
      "قرار منح التأشيرة يعود إلى السفارة أو القنصلية أو الجهة المختصة. لا تضمن مساعدتنا إصدار التأشيرة، وقد تتغير المتطلبات دون إشعار مسبق.",
    showOnServicePages: true,
  },
  seo: {
    defaultTitleEn: "Elite One Desk — Travel, Business Setup and Government Services",
    defaultTitleAr: "إيليت ون ديسك — السفر وتأسيس الأعمال والخدمات الحكومية",
    titleTemplateEn: "%s · Elite One Desk",
    titleTemplateAr: "%s · إيليت ون ديسك",
    defaultDescriptionEn:
      "One destination for travel, business setup, company formation, residency, licensing and government-related support in Saudi Arabia.",
    defaultDescriptionAr:
      "وجهة واحدة للسفر وتأسيس الأعمال وتسجيل الشركات والإقامة والتراخيص والدعم المرتبط بالجهات الحكومية في المملكة.",
    ogImageId: null as number | null,
    twitterHandle: "",
  },
  features: {
    /** Desktop-only pointer companion. Off until an owner opts in. */
    customCursor: true,
    showTestimonials: true,
    showVideos: true,
    showStats: false,
    searchEnabled: true,
    arabicEnabled: true,
  },
  stats: {
    /** Deliberately empty: §47 — no invented numbers until an owner enters them. */
    items: [] as Array<{ value: string; labelEn: string; labelAr: string }>,
  },
} as const;


export type SettingsKey = keyof typeof SETTINGS_DEFAULTS;
export type SiteSettings = {
  -readonly [K in SettingsKey]: {
    -readonly [F in keyof (typeof SETTINGS_DEFAULTS)[K]]: (typeof SETTINGS_DEFAULTS)[K][F];
  };
};
