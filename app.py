import os
import re
from datetime import datetime, timezone

import streamlit as st
from googleapiclient.discovery import build

st.set_page_config(page_title="YouTube Trend-Scanner", page_icon="📈", layout="centered")

API_KEY = st.secrets.get("YOUTUBE_API_KEY", os.environ.get("YOUTUBE_API_KEY", ""))

# Offizielle YouTube-Kategorie-IDs
KATEGORIEN = {
    "Filme & Trailer": "1",
    "Tiere": "15",
    "Sport": "17",
    "Gaming": "20",
    "Lifestyle / Vlogs / Homemade": "22",
    "Comedy": "23",
    "Unterhaltung": "24",
    "Nachrichten & Politik": "25",
    "How-to, Beauty & Style": "26",
    "Bildung / Lernvideos": "27",
    "Wissenschaft & Technik": "28",
    "Musik": "10",
    "Autos & Fahrzeuge": "2",
    "Reisen & Events": "19",
}
REGIONEN = {"Schweiz": "CH", "Deutschland": "DE", "Österreich": "AT", "USA": "US",
            "Grossbritannien": "GB", "Weltweit": None}
SHORTS_MAX_SEK = 180  # YouTube Shorts sind maximal 3 Minuten lang
WELTWEIT_LAENDER = ["US", "GB", "DE", "IN", "BR", "JP", "KR", "FR", "MX", "CH"]


def dauer_in_sekunden(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def dauer_lesbar(sek):
    h, r = divmod(sek, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@st.cache_data(ttl=900, show_spinner=False)
def hole_trends(region, kategorie_id, limit):
    """Holt die meistgesehenen Videos einer Region/Kategorie. Kategorie None = alle."""
    yt = build("youtube", "v3", developerKey=API_KEY)
    videos, token = [], None
    while len(videos) < limit:
        try:
            res = yt.videos().list(
                part="snippet,statistics,contentDetails", chart="mostPopular",
                regionCode=region, videoCategoryId=kategorie_id,
                maxResults=min(50, limit - len(videos)), pageToken=token,
            ).execute()
        except Exception:
            break  # Manche Kategorien sind in manchen Ländern leer -> überspringen
        for v in res.get("items", []):
            sn, stt = v["snippet"], v.get("statistics", {})
            pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            stunden = max((datetime.now(timezone.utc) - pub).total_seconds() / 3600, 1)
            aufrufe = int(stt.get("viewCount", 0))
            sek = dauer_in_sekunden(v["contentDetails"]["duration"])
            kat_name = next((k for k, cid in KATEGORIEN.items() if cid == sn.get("categoryId")), "Sonstiges")
            videos.append({
                "Titel": sn["title"], "Kanal": sn["channelTitle"], "Kategorie": kat_name,
                "Region": region, "Aufrufe": aufrufe,
                "Aufrufe/h": round(aufrufe / stunden), "Likes": int(stt.get("likeCount", 0)),
                "Veröffentlicht": pub.strftime("%d.%m.%Y"),
                "Dauer": dauer_lesbar(sek), "Sekunden": sek,
                "Typ": "Short" if sek <= SHORTS_MAX_SEK else "Video",
                "Link": f"https://www.youtube.com/watch?v={v['id']}",
                "Thumbnail": sn["thumbnails"]["medium"]["url"],
                "_id": v["id"],
            })
        token = res.get("nextPageToken")
        if not token:
            break
    return videos


st.title("📈 YouTube Trend-Scanner")

if not API_KEY:
    st.error("Kein API-Schlüssel hinterlegt. Bitte YOUTUBE_API_KEY in den Secrets setzen.")
    st.stop()

region = st.selectbox("Region", list(REGIONEN), index=0,
                      help="«Weltweit» kombiniert die Trends der 10 grössten YouTube-Märkte.")

alle_kats = st.checkbox("Alle Kategorien", value=True)
if alle_kats:
    gewaehlt = []
else:
    gewaehlt = st.multiselect("Kategorien an-/abwählen", list(KATEGORIEN),
                              default=["Filme & Trailer", "Gaming", "Sport", "Lifestyle / Vlogs / Homemade"])
    if not gewaehlt:
        st.info("Bitte mindestens eine Kategorie wählen oder «Alle Kategorien» anhaken.")

typ = st.radio("Videotyp", ["Alle", "Nur Shorts / Reels (bis 3 Min.)", "Nur normale Videos"], horizontal=True)
anzahl = st.radio("Anzahl Videos", [10, 25, 50, 100], horizontal=True)
sortierung = st.radio("Sortieren nach", ["Gesamtaufrufe", "Aufrufe pro Stunde (echte Viralität)"], horizontal=True)

if st.button("🔍 Scan starten", type="primary", use_container_width=True, disabled=(not alle_kats and not gewaehlt)):
    laender = WELTWEIT_LAENDER if REGIONEN[region] is None else [REGIONEN[region]]
    kat_ids = [None] if alle_kats else [KATEGORIEN[k] for k in gewaehlt]
    # Pro Abfrage genug holen, damit nach Filtern und Zusammenführen genug übrig bleibt
    pro_abfrage = anzahl if (typ == "Alle" and len(laender) == 1 and len(kat_ids) == 1) else min(100, max(25, anzahl))

    videos, gesehen = [], set()
    with st.spinner(f"Scanne {len(laender) * len(kat_ids)} Listen …"):
        for land in laender:
            for kid in kat_ids:
                for v in hole_trends(land, kid, pro_abfrage):
                    if v["_id"] not in gesehen:
                        gesehen.add(v["_id"])
                        videos.append(v)

    if typ.startswith("Nur Shorts"):
        videos = [v for v in videos if v["Typ"] == "Short"]
    elif typ.startswith("Nur normale"):
        videos = [v for v in videos if v["Typ"] == "Video"]
    key = "Aufrufe/h" if sortierung.startswith("Aufrufe pro") else "Aufrufe"
    videos.sort(key=lambda v: v[key], reverse=True)
    videos = videos[:anzahl]

    if not videos:
        st.warning("Keine passenden Videos gefunden. Versuche andere Kategorien oder eine andere Region.")
        st.stop()

    kat_text = "Alle Kategorien" if alle_kats else ", ".join(gewaehlt)
    st.caption(f"{len(videos)} Videos · {region} · {kat_text} · {typ} · {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    for i, v in enumerate(videos, 1):
        a, b = st.columns([1, 2])
        a.image(v["Thumbnail"], use_container_width=True)
        badge = "🎞️ Short" if v["Typ"] == "Short" else "🎬 Video"
        b.markdown(f"**{i}. [{v['Titel']}]({v['Link']})**")
        b.caption(f"{badge} · {v['Kategorie']} · {v['Region']} · {v['Kanal']}")
        b.caption(f"{v['Aufrufe']:,} Aufrufe · {v['Aufrufe/h']:,}/h · {v['Likes']:,} Likes · {v['Dauer']} · {v['Veröffentlicht']}")
        st.divider()

    import pandas as pd
    df = pd.DataFrame(videos).drop(columns=["Thumbnail", "Sekunden", "_id"])
    st.download_button("📥 Als CSV herunterladen", df.to_csv(index=False).encode("utf-8"),
                       "trends.csv", "text/csv", use_container_width=True)
