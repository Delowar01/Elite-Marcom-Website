/**
 * Extracts a YouTube id from whatever an editor pastes — a watch URL, a share
 * link, an embed URL, a Shorts link, or the bare id. Only an 11-character id
 * made of the characters YouTube actually uses is accepted; anything else is
 * rejected rather than guessed at, because a wrong id renders as a dead player.
 */
const ID = /^[A-Za-z0-9_-]{11}$/;

export function youtubeId(input: string): string | null {
  const value = (input ?? "").trim();
  if (!value) return null;
  if (ID.test(value)) return value;

  let url: URL;
  try {
    url = new URL(value.startsWith("http") ? value : `https://${value}`);
  } catch {
    return null;
  }

  const host = url.hostname.replace(/^www\./, "").toLowerCase();
  const allowed = ["youtube.com", "m.youtube.com", "youtube-nocookie.com", "youtu.be"];
  if (!allowed.includes(host)) return null;

  if (host === "youtu.be") {
    const id = url.pathname.slice(1).split("/")[0] ?? "";
    return ID.test(id) ? id : null;
  }

  const v = url.searchParams.get("v");
  if (v && ID.test(v)) return v;

  const match = /^\/(embed|shorts|v|live)\/([A-Za-z0-9_-]{11})/.exec(url.pathname);
  return match?.[2] && ID.test(match[2]) ? match[2] : null;
}

/** YouTube's own still, used when no custom thumbnail has been uploaded. */
export const youtubePoster = (id: string, quality: "hq" | "max" = "hq") =>
  `https://i.ytimg.com/vi/${id}/${quality === "max" ? "maxresdefault" : "hqdefault"}.jpg`;

export const youtubeWatchUrl = (id: string) => `https://www.youtube.com/watch?v=${id}`;
