import os
import re
from datetime import datetime, timezone

import streamlit as st
from googleapiclient.discovery import build

st.set_page_config(page_title="YouTube Trend-Scanner", page_icon="📈", layout="centered")

API_KEY = st.secrets.get("YOUTUBE_API_KEY", os.environ.get("YOUTUBE_API_KEY", ""))

KATEGORIEN = {
    "Alle": None, "Tiere": "15", "Unterhaltung": "24", "Bildung / Lernvideos": "27",
    "Gaming": "20", "Musik": "10", "Comedy": "23", "Sport": "17",
    "How-to & Style": "26", "Wissenschaft & Technik": "28", "Menschen & Blogs": "22",
    "Film & Animation": "1", "Nachrichten": "25",
}
REGIONEN = {"Schweiz": "CH", "Deutschland": "DE", "Österreich": "AT", "USA": "US", "Grossbritannien": "GB"}
SHORTS_MAX_SEK = 180  # YouTube Shorts sind maximal 3 Minuten lang


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
    yt = build("youtube", "v3", developerKey=API_KEY)
    videos, token = [], None
    while len(videos) < limit:
        res = yt.videos().list(
            part="snippet,statistics,contentDetails", chart="mostPopular",
            regionCode=region, videoCategoryId=kategorie_id,
            maxResults=min(50, limit - len(videos)), pageToken=token,
        ).execute()
        for v in res.get("items", []):
            sn, stt = v["snippet"], v.get("statistics", {})
            pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            stunden = max((datetime.now(timezone.utc) - pub).total_seconds() / 3600, 1)
            aufrufe = int(stt.get("viewCount", 0))
            sek = dauer_in_sekunden(v["contentDetails"]["duration"])
            videos.append({
                "Titel": sn["title"], "Kanal": sn["channelTitle"], "Aufrufe": aufrufe,
                "Aufrufe/h": round(aufrufe / stunden), "Likes": int(stt.get("likeCount", 0)),
                "Veröffentlicht": pub.strftime("%d.%m.%Y"),
                "Dauer": dauer_lesbar(sek), "Sekunden": sek,
                "Typ": "Short" if sek <= SHORTS_MAX_SEK else "Video",
                "Link": f"https://www.youtube.com/watch?v={v['id']}",
                "Thumbnail": sn["thumbnails"]["medium"]["url"],
            })
        token = res.get("nextPageToken")
        if not token:
            break
    return videos


st.title("📈 YouTube Trend-Scanner")

if not API_KEY:
    st.error("Kein API-Schlüssel hinterlegt. Bitte YOUTUBE_API_KEY in den Secrets setzen.")
    st.stop()

c1, c2 = st.columns(2)
kategorie = c1.selectbox("Kategorie", list(KATEGORIEN))
region = c2.selectbox("Region", list(REGIONEN), index=0)
typ = st.radio("Videotyp", ["Alle", "Nur Shorts / Reels (bis 3 Min.)", "Nur normale Videos"], horizontal=True)
anzahl = st.radio("Anzahl Videos", [10, 25, 50, 100], horizontal=True)
sortierung = st.radio("Sortieren nach", ["Gesamtaufrufe", "Aufrufe pro Stunde (echte Viralität)"], horizontal=True)

if st.button("🔍 Scan starten", type="primary", use_container_width=True):
    with st.spinner("Scanne YouTube …"):
        try:
            # Bei Typ-Filter mehr holen, damit nach dem Filtern genug übrig bleibt
            hol = anzahl if typ == "Alle" else min(200, anzahl * 3)
            videos = hole_trends(REGIONEN[region], KATEGORIEN[kategorie], hol)
        except Exception as e:
            st.error(f"Fehler beim Abruf: {e}")
            st.stop()

    if typ.startswith("Nur Shorts"):
        videos = [v for v in videos if v["Typ"] == "Short"]
    elif typ.startswith("Nur normale"):
        videos = [v for v in videos if v["Typ"] == "Video"]
    if sortierung.startswith("Aufrufe pro"):
        videos.sort(key=lambda v: v["Aufrufe/h"], reverse=True)
    videos = videos[:anzahl]

    if not videos:
        st.warning("Keine passenden Videos gefunden. Versuche eine andere Kategorie oder Region.")
        st.stop()

    st.caption(f"{len(videos)} Videos · {kategorie} · {region} · {typ} · {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    for i, v in enumerate(videos, 1):
        a, b = st.columns([1, 2])
        a.image(v["Thumbnail"], use_container_width=True)
        badge = "🎞️ Short" if v["Typ"] == "Short" else "🎬 Video"
        b.markdown(f"**{i}. [{v['Titel']}]({v['Link']})**")
        b.caption(f"{badge} · {v['Kanal']} · {v['Aufrufe']:,} Aufrufe · {v['Aufrufe/h']:,}/h · "
                  f"{v['Likes']:,} Likes · {v['Dauer']} · {v['Veröffentlicht']}")
        st.divider()

    import pandas as pd
    df = pd.DataFrame(videos).drop(columns=["Thumbnail", "Sekunden"])
    st.download_button("📥 Als CSV herunterladen", df.to_csv(index=False).encode("utf-8"),
                       "trends.csv", "text/csv", use_container_width=True)
