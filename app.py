import os
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
            videos.append({
                "Titel": sn["title"], "Kanal": sn["channelTitle"], "Aufrufe": aufrufe,
                "Aufrufe/h": round(aufrufe / stunden), "Likes": int(stt.get("likeCount", 0)),
                "Veröffentlicht": pub.strftime("%d.%m.%Y"),
                "Dauer": v["contentDetails"]["duration"].replace("PT", "").lower(),
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
region = c2.selectbox("Region", list(REGIONEN))
anzahl = st.radio("Anzahl Videos", [10, 25, 50, 100], horizontal=True)
sortierung = st.radio("Sortieren nach", ["Gesamtaufrufe", "Aufrufe pro Stunde (echte Viralität)"], horizontal=True)

if st.button("🔍 Scan starten", type="primary", use_container_width=True):
    with st.spinner("Scanne YouTube …"):
        try:
            videos = hole_trends(REGIONEN[region], KATEGORIEN[kategorie], anzahl)
        except Exception as e:
            st.error(f"Fehler beim Abruf: {e}")
            st.stop()
    if sortierung.startswith("Aufrufe pro"):
        videos.sort(key=lambda v: v["Aufrufe/h"], reverse=True)

    st.caption(f"{len(videos)} Videos · {kategorie} · {region} · {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    for i, v in enumerate(videos, 1):
        a, b = st.columns([1, 2])
        a.image(v["Thumbnail"], use_container_width=True)
        b.markdown(f"**{i}. [{v['Titel']}]({v['Link']})**")
        b.caption(f"{v['Kanal']} · {v['Aufrufe']:,} Aufrufe · {v['Aufrufe/h']:,}/h · "
                  f"{v['Likes']:,} Likes · {v['Dauer']} · {v['Veröffentlicht']}")
        st.divider()

    import pandas as pd
    df = pd.DataFrame(videos).drop(columns=["Thumbnail"])
    st.download_button("📥 Als CSV herunterladen", df.to_csv(index=False).encode("utf-8"),
                       "trends.csv", "text/csv", use_container_width=True)
