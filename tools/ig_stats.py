"""Недельная статистика Instagram @fortex__uae через официальный Graph API (только чтение) -> stats/ig/<дата>.json.
Ничего не публикует и не лайкает. Токен: секрет IG_TOKEN."""
import glob, json, os, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

T = os.environ.get("IG_TOKEN", "")
API = "https://graph.instagram.com/v21.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "stats", "ig")
DUBAI = timezone(timedelta(hours=4))


def get(path, **params):
    params["access_token"] = T
    try:
        return json.load(urllib.request.urlopen(f"{API}/{path}?" + urllib.parse.urlencode(params), timeout=60))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:300]}


def insights(mid, kind):
    want = ["reach", "views", "saved", "shares", "likes", "comments", "total_interactions", "profile_visits", "follows"]
    if kind == "REELS":
        want += ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
    r = get(f"{mid}/insights", metric=",".join(want))
    if "error" in r:  # часть метрик недоступна для этого типа: спрашиваем по одной
        out, errs = {}, []
        for m in want:
            x = get(f"{mid}/insights", metric=m)
            if "data" in x and x["data"]:
                out[m] = x["data"][0]["values"][0]["value"] if x["data"][0].get("values") else x["data"][0].get("total_value", {}).get("value")
            else:
                errs.append(m)
        return out, errs
    return {d["name"]: (d["values"][0]["value"] if d.get("values") else d.get("total_value", {}).get("value")) for d in r.get("data", [])}, []


def src_map():
    """slug и формат наших материалов по ссылке на публикацию."""
    m = {}
    for f in glob.glob(os.path.join(ROOT, "ig", "src", "*.json")) + glob.glob(os.path.join(ROOT, "ig", "reels", "src", "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        res = d.get("result")
        if isinstance(res, str):
            try:
                res = eval(res, {})  # результат сохранён как repr словаря
            except Exception:
                res = {}
        link = (res or {}).get("permalink") or d.get("permalink") or ""
        slug = os.path.basename(f)[:-5]
        info = {"slug": slug, "style": d.get("style") or ("story" if slug.startswith("st-") else ""),
                "format": d.get("format") or ("news" if "reels" in f and d.get("v") == 2 else ""), "test": d.get("test", "")}
        if link:
            m[link.rstrip("/")] = info
    return m


def main():
    if not T:
        print("no IG_TOKEN")
        return
    now = datetime.now(DUBAI)
    me = get("me", fields="username,followers_count,follows_count,media_count")
    acc = {}
    since, until = int((now - timedelta(days=7)).timestamp()), int(now.timestamp())
    for m in ["reach", "views", "accounts_engaged", "total_interactions", "profile_links_taps", "follows_and_unfollows"]:
        r = get("me/insights", metric=m, period="day", metric_type="total_value", since=since, until=until)
        acc[m] = r["data"][0].get("total_value", {}).get("value") if r.get("data") else {"error": r.get("error", "")[:120]}
    r = get("me/insights", metric="follows_and_unfollows", period="day", metric_type="total_value", breakdown="follow_type",
            since=since, until=until)
    if r.get("data"):
        acc["follows_breakdown"] = r["data"][0].get("total_value", {}).get("breakdowns", [])
    media = get("me/media", fields="id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count", limit=50)
    smap = src_map()
    items = []
    for x in media.get("data", []):
        kind = x.get("media_product_type") or x.get("media_type")
        ins, errs = insights(x["id"], kind)
        items.append({"id": x["id"], "at": x["timestamp"], "kind": kind, "type": x.get("media_type"), "link": x.get("permalink"),
                      "caption": (x.get("caption") or "")[:140], "likes": x.get("like_count"), "comments": x.get("comments_count"),
                      "ins": ins, "unavailable": errs, "ours": smap.get((x.get("permalink") or "").rstrip("/"), {})})
        time.sleep(0.3)
    hist_p = os.path.join(OUT, "followers.json")
    hist = json.load(open(hist_p)) if os.path.exists(hist_p) else []
    hist.append({"date": now.date().isoformat(), "followers": me.get("followers_count"), "media": me.get("media_count")})
    os.makedirs(OUT, exist_ok=True)
    json.dump(hist[-60:], open(hist_p, "w"), ensure_ascii=False, indent=1)
    out = {"generated": now.isoformat(timespec="minutes"), "period": "последние 7 дней", "account": me, "account_7d": acc,
           "followers_history": hist[-8:], "media": items, "media_error": media.get("error")}
    json.dump(out, open(os.path.join(OUT, f"{now.date().isoformat()}.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(out, open(os.path.join(OUT, "latest.json"), "w"), ensure_ascii=False, indent=1)
    print("ok", me.get("followers_count"), len(items), "media")


if __name__ == "__main__":
    main()
