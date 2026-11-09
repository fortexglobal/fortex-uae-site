"""Недельная статистика Яндекс Метрики -> stats/metrika.json (запускается в GitHub Actions).
Токен: секрет METRIKA_TOKEN (OAuth, только чтение статистики)."""
import json, os, urllib.parse, urllib.request, datetime

C = "113701535"
TOKEN = os.environ.get("METRIKA_TOKEN", "")
API = "https://api-metrika.yandex.net"


def get(path, **params):
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"OAuth {TOKEN}"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def table(dim, metrics="ym:s:visits,ym:s:users", limit=15, d1="7daysAgo", d2="yesterday"):
    r = get("/stat/v1/data", ids=C, metrics=metrics, dimensions=dim, date1=d1, date2=d2, limit=limit, sort="-" + metrics.split(",")[0])
    return [{"name": " / ".join(str(x.get("name")) for x in row["dimensions"]), "values": row["metrics"]} for row in r.get("data", [])]


def main():
    goals = get(f"/management/v1/counter/{C}/goals").get("goals", [])
    gm = ",".join(f"ym:s:goal{g['id']}reaches" for g in goals) or "ym:s:visits"
    tot = get("/stat/v1/data", ids=C, metrics="ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds",
              date1="7daysAgo", date2="yesterday")
    goal_tot = get("/stat/v1/data", ids=C, metrics=gm, date1="7daysAgo", date2="yesterday")
    out = {
        "generated": datetime.datetime.utcnow().isoformat(timespec="minutes") + "Z",
        "period": "последние 7 дней",
        "totals": dict(zip(["визиты", "посетители", "отказы_%", "время_на_сайте_сек"], tot.get("totals", []))),
        "goals": {g["name"]: v for g, v in zip(goals, goal_tot.get("totals", []))},
        "sources": table("ym:s:lastTrafficSource"),
        "source_details": table("ym:s:lastSourceEngine"),
        "utm": table("ym:s:lastUTMSource,ym:s:lastUTMCampaign"),
        "pages": table("ym:s:startURLPath"),
        "goals_by_source": table("ym:s:lastTrafficSource", metrics=gm) if goals else [],
        "goal_names": [g["name"] for g in goals],
    }
    def day(d):
        t = get("/stat/v1/data", ids=C, metrics="ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds", date1=d, date2=d)
        return {
            "totals": dict(zip(["визиты", "посетители", "отказы_%", "время_на_сайте_сек"], t.get("totals", []))),
            "goals": {g["name"]: v for g, v in zip(goals, get("/stat/v1/data", ids=C, metrics=gm, date1=d, date2=d).get("totals", []))},
            "sources": table("ym:s:lastTrafficSource", d1=d, d2=d),
            "source_details": table("ym:s:lastSourceEngine", d1=d, d2=d),
            "utm": table("ym:s:lastUTMSource,ym:s:lastUTMCampaign", d1=d, d2=d),
            "pages": table("ym:s:startURLPath", d1=d, d2=d),
        }
    out["yesterday"] = day("yesterday")
    out["day_before"] = day("2daysAgo")
    out["date_yesterday"] = (datetime.datetime.utcnow() + datetime.timedelta(hours=4) - datetime.timedelta(days=1)).date().isoformat()
    td = get("/stat/v1/data", ids=C, metrics="ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds", date1="today", date2="today")
    out["today"] = {
        "totals": dict(zip(["визиты", "посетители", "отказы_%", "время_на_сайте_сек"], td.get("totals", []))),
        "goals": {g["name"]: v for g, v in zip(goals, get("/stat/v1/data", ids=C, metrics=gm, date1="today", date2="today").get("totals", []))},
        "sources": table("ym:s:lastTrafficSource", d1="today", d2="today"),
        "source_details": table("ym:s:lastSourceEngine", d1="today", d2="today"),
        "utm": table("ym:s:lastUTMSource,ym:s:lastUTMCampaign", d1="today", d2="today"),
        "pages": table("ym:s:startURLPath", d1="today", d2="today"),
    }
    # Аудитория для ретаргетинга (решение Александра 09.11). Пиксель Meta стоит с 09.11,
    # его аудитория примерно = уникальные посетители сайта с этой даты.
    PIXEL_FROM = "2026-11-09"
    def users(d1, flt=None, metric="ym:s:users"):
        kw = dict(ids=C, metrics=metric, date1=d1, date2="today")
        if flt:
            kw["filters"] = flt
        try:
            t = get("/stat/v1/data", **kw).get("totals", [0])
            return int(t[0]) if t else 0
        except Exception as e:
            return None
    aud = {"pixel_from": PIXEL_FROM,
           "since_pixel": users(PIXEL_FROM),
           "d30": users("30daysAgo"), "d90": users("90daysAgo"), "d180": users("180daysAgo")}
    for key, path in (("ipoteka", "/ipoteka/"), ("virtual_work", "/virtual-work/"), ("gid", "/gid/")):
        aud[key + "_30d"] = users("30daysAgo", f"ym:pv:URLPath=@'{path}'", "ym:pv:users")
        aud[key + "_since_pixel"] = users(PIXEL_FROM, f"ym:pv:URLPath=@'{path}'", "ym:pv:users")
    for g in goals:
        if "telegram" in g["name"].lower() or "заявк" in g["name"].lower():
            aud["goal_users_30d:" + g["name"]] = users("30daysAgo", metric=f"ym:s:goal{g['id']}users")
    out["audience"] = aud
    os.makedirs("stats", exist_ok=True)
    json.dump(out, open("stats/metrika.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(out["totals"], ensure_ascii=False), out["goals"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        body = getattr(e, "read", lambda: b"")()[:500]
        os.makedirs("stats", exist_ok=True)
        json.dump({"error": str(e), "body": body.decode("utf-8", "replace"), "token_len": len(TOKEN),
                   "generated": datetime.datetime.utcnow().isoformat(timespec="minutes") + "Z"},
                  open("stats/metrika.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("ERROR", e)
