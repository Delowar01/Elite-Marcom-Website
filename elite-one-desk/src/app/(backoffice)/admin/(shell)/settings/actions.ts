"use server";

import { eq, sql } from "drizzle-orm";
import { revalidatePath } from "next/cache";

import { logActivity } from "@/lib/activity";
import {
  checkbox, fail, field, numberField, ok, optionalId, runAction, type ActionState,
} from "@/lib/admin/actions";
import { guardAction } from "@/lib/auth/guard";
import { TAGS, revalidate } from "@/lib/cache";
import { db } from "@/lib/db";
import { socialLinks } from "@/lib/db/schema";
import { saveSettingsGroup, type SettingsKey } from "@/lib/settings";

const refreshAll = () => {
  revalidate(TAGS.settings, TAGS.social);
  revalidatePath("/admin/settings");
  revalidatePath("/admin/analytics");
};

/** Only an https:// address on a known host is accepted for a map embed. */
function mapEmbed(value: string): string {
  if (!value) return "";
  try {
    const url = new URL(value);
    if (url.protocol !== "https:") return "";
    const host = url.hostname.replace(/^www\./, "");
    return host === "google.com" || host === "maps.google.com" || host.endsWith(".google.com")
      ? url.toString()
      : "";
  } catch {
    return "";
  }
}

const GROUP_LABEL: Record<string, string> = {
  brand: "brand details",
  contact: "contact details",
  whatsapp: "WhatsApp settings",
  disclaimers: "disclaimers",
  seo: "SEO defaults",
  features: "feature switches",
  analytics: "analytics",
};

async function persist(
  group: SettingsKey,
  values: Record<string, unknown>,
  form: FormData,
  permission: "settings.manage" | "analytics.manage" | "seo.manage",
): Promise<ActionState> {
  const session = await guardAction(permission, form);
  await saveSettingsGroup(group, values, session.user.id);
  await logActivity(session, {
    action: "settings.changed",
    entityType: "settings",
    entityId: group,
    summary: `Updated ${GROUP_LABEL[group] ?? group}`,
  });
  refreshAll();
  return ok("Saved.");
}

export async function saveBrand(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("settings-brand", async () =>
    persist(
      "brand",
      {
        siteNameEn: field(form, "siteNameEn", 120),
        siteNameAr: field(form, "siteNameAr", 120),
        taglineEn: field(form, "taglineEn", 190),
        taglineAr: field(form, "taglineAr", 190),
        legalNameEn: field(form, "legalNameEn", 190),
        legalNameAr: field(form, "legalNameAr", 190),
      },
      form,
      "settings.manage",
    ),
  );
}

export async function saveContact(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("settings-contact", async () => {
    const embed = field(form, "mapEmbedUrl", 600);
    const clean = mapEmbed(embed);
    if (embed && !clean) {
      return fail("That map address was not accepted.", {
        mapEmbedUrl: "Paste the https://www.google.com/maps/embed… address from Google Maps.",
      });
    }
    return persist(
      "contact",
      {
        phone: field(form, "phone", 40),
        phoneDisplay: field(form, "phoneDisplay", 40),
        email: field(form, "email", 190),
        addressEn: field(form, "addressEn", 255),
        addressAr: field(form, "addressAr", 255),
        cityEn: field(form, "cityEn", 120),
        cityAr: field(form, "cityAr", 120),
        countryEn: field(form, "countryEn", 120),
        countryAr: field(form, "countryAr", 120),
        hoursEn: field(form, "hoursEn", 255),
        hoursAr: field(form, "hoursAr", 255),
        mapEmbedUrl: clean,
      },
      form,
      "settings.manage",
    );
  });
}

export async function saveWhatsapp(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("settings-whatsapp", async () => {
    const digits = field(form, "number", 40).replace(/\D/g, "");
    const enabled = checkbox(form, "enabled");
    if (enabled && digits.length < 8) {
      return fail("Enter the number in international format before switching WhatsApp on.", {
        number: "Digits only, including the country code — for example 9665XXXXXXXX.",
      });
    }
    return persist(
      "whatsapp",
      {
        enabled,
        number: digits,
        defaultMessageEn: field(form, "defaultMessageEn", 400),
        defaultMessageAr: field(form, "defaultMessageAr", 400),
        floatingEnabled: checkbox(form, "floatingEnabled"),
      },
      form,
      "settings.manage",
    );
  });
}

export async function saveDisclaimers(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("settings-disclaimers", async () =>
    persist(
      "disclaimers",
      {
        governmentEn: field(form, "governmentEn", 2000),
        governmentAr: field(form, "governmentAr", 2000),
        visaEn: field(form, "visaEn", 2000),
        visaAr: field(form, "visaAr", 2000),
        showOnServicePages: checkbox(form, "showOnServicePages"),
      },
      form,
      "settings.manage",
    ),
  );
}

export async function saveFeatures(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("settings-features", async () =>
    persist(
      "features",
      {
        customCursor: checkbox(form, "customCursor"),
        showTestimonials: checkbox(form, "showTestimonials"),
        showVideos: checkbox(form, "showVideos"),
        showStats: checkbox(form, "showStats"),
        searchEnabled: checkbox(form, "searchEnabled"),
        arabicEnabled: checkbox(form, "arabicEnabled"),
      },
      form,
      "settings.manage",
    ),
  );
}

export async function saveSeoDefaults(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("settings-seo", async () =>
    persist(
      "seo",
      {
        defaultTitleEn: field(form, "defaultTitleEn", 190),
        defaultTitleAr: field(form, "defaultTitleAr", 190),
        titleTemplateEn: field(form, "titleTemplateEn", 120),
        titleTemplateAr: field(form, "titleTemplateAr", 120),
        defaultDescriptionEn: field(form, "defaultDescriptionEn", 320),
        defaultDescriptionAr: field(form, "defaultDescriptionAr", 320),
        ogImageId: optionalId(form, "ogImageId"),
        twitterHandle: field(form, "twitterHandle", 40),
      },
      form,
      "seo.manage",
    ),
  );
}

export async function saveAnalytics(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("settings-analytics", async () => {
    const ga4Id = field(form, "ga4Id", 40);
    const gtmId = field(form, "gtmId", 40);
    const metaPixelId = field(form, "metaPixelId", 40);

    if (ga4Id && !/^G-[A-Z0-9]{6,}$/i.test(ga4Id)) {
      return fail("That GA4 id does not look right.", { ga4Id: "It starts with G- — for example G-XXXXXXXXXX." });
    }
    if (gtmId && !/^GTM-[A-Z0-9]{4,}$/i.test(gtmId)) {
      return fail("That Tag Manager id does not look right.", { gtmId: "It starts with GTM-." });
    }
    if (metaPixelId && !/^\d{6,20}$/.test(metaPixelId)) {
      return fail("A Meta Pixel id is a number.", { metaPixelId: "Digits only." });
    }

    return persist("analytics", { ga4Id, gtmId, metaPixelId }, form, "analytics.manage");
  });
}

/* -------------------------------------------------------------------------- */
/* Social links                                                               */
/* -------------------------------------------------------------------------- */

export async function saveSocialLink(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("social-save", async () => {
    const session = await guardAction("settings.manage", form);
    const id = Number(form.get("id")) || 0;
    const platform = field(form, "platform", 32).toLowerCase();
    const url = field(form, "url", 255);

    if (!platform) return fail("Which network is this?", { platform: "Required." });
    // https only — a social profile has no reason to be anything else, and it
    // is the one field most likely to be pasted from an untrusted place.
    let parsed: URL;
    try {
      parsed = new URL(url);
    } catch {
      return fail("That address is not valid.", { url: "Include https:// at the start." });
    }
    if (parsed.protocol !== "https:") {
      return fail("Social links must be https.", { url: "Use the https:// address." });
    }

    const values = {
      platform,
      url: parsed.toString(),
      sortOrder: numberField(form, "sortOrder", 0),
      isPublished: checkbox(form, "isPublished"),
    };

    if (id) {
      await db.update(socialLinks).set({ ...values, updatedAt: new Date() }).where(eq(socialLinks.id, id));
    } else {
      const [last] = await db
        .select({ n: sql<number>`coalesce(max(${socialLinks.sortOrder}), -1)::int` })
        .from(socialLinks);
      await db.insert(socialLinks).values({ ...values, sortOrder: (last?.n ?? -1) + 1 });
    }

    await logActivity(session, {
      action: id ? "social.updated" : "social.created",
      entityType: "social",
      entityId: id || 0,
      summary: `${id ? "Updated" : "Added"} the ${platform} link`,
    });
    refreshAll();
    return ok(id ? "Link saved." : "Link added.");
  });
}

export async function deleteSocialLink(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("social-delete", async () => {
    const session = await guardAction("settings.manage", form);
    const id = Number(form.get("id"));
    const [row] = await db.select().from(socialLinks).where(eq(socialLinks.id, id)).limit(1);
    if (!row) return fail("That link no longer exists.");
    await db.delete(socialLinks).where(eq(socialLinks.id, id));
    await logActivity(session, {
      action: "social.deleted",
      entityType: "social",
      entityId: id,
      summary: `Removed the ${row.platform} link`,
    });
    refreshAll();
    return ok("Link removed.");
  });
}
