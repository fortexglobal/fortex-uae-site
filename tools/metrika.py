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
    td = get("/stat/v1/data", ids=C, metrics="ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds", date1="today", date2="today")
    out["today"] = {
        "totals": dict(zip(["визиты", "посетители", "отказы_%", "время_на_сайте_сек"], td.get("totals", []))),
        "goals": {g["name"]: v for g, v in zip(goals, get("/stat/v1/data", ids=C, metrics=gm, date1="today", date2="today").get("totals", []))},
        "sources": table("ym:s:lastTrafficSource", d1="today", d2="today"),
        "source_details": table("ym:s:lastSourceEngine", d1="today", d2="today"),
        "utm": table("ym:s:lastUTMSource,ym:s:lastUTMCampaign", d1="today", d2="today"),
        "pages": table("ym:s:startURLPath", d1="today", d2="today"),
    }
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
