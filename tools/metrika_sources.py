"""Откуда приходят люди на сайт: разбивка за 30 дней по источникам, UTM, рефереру, стране и городу, по дням.
Пишет stats/sources.json. Запускается вместе с tools/metrika.py."""
import datetime, json, os, urllib.parse, urllib.request

TOKEN = os.environ.get("METRIKA_TOKEN", "")
C = "113701535"
API = "https://api-metrika.yandex.net"


def get(**params):
    url = f"{API}/stat/v1/data?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"OAuth {TOKEN}"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def table(dim, d1="30daysAgo", d2="today", limit=40, metrics="ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds"):
    r = get(ids=C, metrics=metrics, dimensions=dim, date1=d1, date2=d2, limit=limit, sort="-ym:s:visits")
    return [{"name": " / ".join(str(x.get("name")) for x in row["dimensions"]), "v": [round(m, 1) for m in row["metrics"]]} for row in r.get("data", [])]


def main():
    out = {"generated": datetime.datetime.utcnow().isoformat(timespec="minutes") + "Z", "cols": ["визиты", "посетители", "отказы_%", "время_сек"],
           "source": table("ym:s:lastTrafficSource"),
           "engine": table("ym:s:lastSourceEngine"),
           "utm": table("ym:s:lastUTMSource,ym:s:lastUTMMedium,ym:s:lastUTMCampaign"),
           "referer": table("ym:s:externalRefererHost"),
           "landing": table("ym:s:startURL", limit=60),
           "country_city": table("ym:s:regionCountry,ym:s:regionCity"),
           "source_city": table("ym:s:lastTrafficSource,ym:s:regionCity"),
           "device": table("ym:s:deviceCategory,ym:s:browser"),
           "by_day_source": table("ym:s:date,ym:s:lastTrafficSource", limit=200),
           "new_vs_return": table("ym:s:isNewUser")}
    os.makedirs("stats", exist_ok=True)
    json.dump(out, open("stats/sources.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("sources ok")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        body = getattr(e, "read", lambda: b"")()[:400]
        json.dump({"error": str(e), "body": body.decode("utf-8", "replace")}, open("stats/sources.json", "w"), ensure_ascii=False)
        print("ERROR", e, body)
