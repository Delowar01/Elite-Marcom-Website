import { SectionHeading } from "@/components/site/section-heading";
import { VideoGallery, type VideoItem } from "@/components/site/video-gallery";
import { num, str, text } from "@/lib/cms/values";
import { pick } from "@/lib/i18n/config";
import { mediaSrc, mediaSrcSet } from "@/lib/media/url";
import type { BlockProps } from "./context";

export function VideoShowcaseBlock({ values, ctx }: BlockProps) {
  const { locale, dict, settings } = ctx;
  if (!settings.features.showVideos) return null;

  const category = str(values, "category");
  const limit = num(values, "limit", 6);

  const rows = ctx.videos
    .filter((v) => (category ? v.category === category : true))
    .slice(0, limit > 0 ? limit : undefined);
  if (!rows.length) return null;

  const videos: VideoItem[] = rows.map((row) => {
    const custom = row.thumbnailId ? ctx.media.get(row.thumbnailId) : null;
    return {
      id: row.id,
      youtubeId: row.youtubeId,
      title: pick(locale, row.titleEn, row.titleAr),
      description: pick(locale, row.descriptionEn, row.descriptionAr),
      // An uploaded still wins; otherwise YouTube's own poster, which costs one
      // image request and still avoids loading the player.
      posterSrc: custom
        ? mediaSrc(custom, custom.derivatives?.[1] ?? undefined)
        : `https://i.ytimg.com/vi/${row.youtubeId}/hqdefault.jpg`,
      posterSrcSet: custom ? mediaSrcSet(custom) : undefined,
      duration: row.durationLabel,
      featured: row.isFeatured,
    };
  });

  return (
    <section className="section">
      <div className="shell shell-wide">
        <SectionHeading
          eyebrow={text(values, "eyebrow", locale) || dict.sections.videosEyebrow}
          title={text(values, "title", locale)}
          intro={text(values, "intro", locale)}
        />
        <div className="mt-10">
          <VideoGallery
            videos={videos}
            labels={{
              play: dict.video.play,
              close: dict.video.close,
              openOnYoutube: dict.video.openOnYoutube,
              loadNotice: dict.video.loadNotice,
            }}
          />
        </div>
      </div>
    </section>
  );
}
