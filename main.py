from datetime import datetime, timedelta
import zoneinfo
import pandas as pd
import requests
import plotly.express as px
import streamlit as st

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 제목 표시
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제의 일별 박스오피스")

# -----------------------------------------------------------------------------
# 2. 한국 시간(KST) 기준 '어제' 날짜 계산
# -----------------------------------------------------------------------------
# 배포 서버의 시계가 UTC 기준이더라도 정확한 한국 시간 기준으로 어제 날짜를 구합니다.
kst = zoneinfo.ZoneInfo("Asia/Seoul")
now_kst = datetime.now(kst)
yesterday = now_kst - timedelta(days=1)

# API 요청에 사용할 YYYYMMDD 형태의 문자열
target_dt = yesterday.strftime("%Y%m%d")
# 화면에 표시할 YYYY-MM-DD 형태의 문자열
display_dt = yesterday.strftime("%Y년 %m월 %d일")

st.caption(f"📅 기준 날짜: **{display_dt}** (한국 시간 기준 어제)")

# -----------------------------------------------------------------------------
# 3. KOBIS API 인증키 불러오기 (st.secrets)
# -----------------------------------------------------------------------------
# Streamlit Cloud의 Secrets에 등록된 KOBIS_KEY 값을 안전하게 읽어옵니다.
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("⚠️ **API 인증키(KOBIS_KEY)를 찾을 수 없습니다.**")
    st.info(
        "**해결 방법:**\n"
        "1. Streamlit Cloud의 앱 설정에서 **Secrets** 메뉴로 이동하세요.\n"
        "2. 아래와 같이 `KOBIS_KEY`를 추가해 주세요:\n"
        "```toml\n"
        'KOBIS_KEY = "발급받은_인증키_입력"\n'
        "```"
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# -----------------------------------------------------------------------------
# 4. 박스오피스 API 데이터 요청 함수 (캐싱 적용)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)  # 동일한 요청은 1시간 동안 결과를 재사용합니다.
def fetch_daily_boxoffice(key: str, date_str: str):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": key,
        "targetDt": date_str
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()  # HTTP 오류가 발생하면 예외를 일으킵니다.
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청에 실패했습니다. (사유: {e})"

data, error_msg = fetch_daily_boxoffice(api_key, target_dt)

# -----------------------------------------------------------------------------
# 5. 응답 예외 및 오류 처리
# -----------------------------------------------------------------------------
# 5-1) 네트워크 요청 자체가 실패한 경우
if error_msg:
    st.error(f"⚠️ {error_msg}")
    st.info("💡 **확인해 보세요:** 인터넷 연결 상태 또는 KOBIS 서버 상태를 확인해 주세요.")
    st.stop()

# 5-2) KOBIS에서 인증키 오류 등의 사유로 faultInfo를 반환한 경우
if "faultInfo" in data:
    fault = data["faultInfo"]
    fault_code = fault.get("errorCode", "알 수 없음")
    fault_msg = fault.get("message", "오류 메시지가 없습니다.")
    
    st.error(f"⚠️ **KOBIS API 오류 발생** (코드: {fault_code})")
    st.warning(f"오류 내용: {fault_msg}")
    st.info(
        "💡 **확인해 보세요:**\n"
        "- Streamlit Secrets에 등록한 `KOBIS_KEY`가 올바른지 확인해 주세요.\n"
        "- KOBIS 오픈API 마이페이지에서 키가 활성화 상태인지 확인해 주세요."
    )
    st.stop()

# 5-3) 결과 목록(dailyBoxOfficeList)이 없거나 비어 있는 경우
box_office_result = data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ **조회된 박스오피스 데이터가 없습니다.**")
    st.info(
        "💡 **확인해 보세요:**\n"
        "- 아직 어제 일자 집계가 완료되지 않았을 수 있습니다.\n"
        "- 잠시 후 다시 시도하거나 날짜 기준을 확인해 주세요."
    )
    st.stop()

# -----------------------------------------------------------------------------
# 6. 데이터 가공 및 수치형 변환
# -----------------------------------------------------------------------------
# API 응답에서 받은 문자열 숫자 데이터를 정수형(int)으로 변환합니다.
df = pd.DataFrame(daily_list)

df["rank"] = df["rank"].astype(int)
df["audiCnt"] = df["audiCnt"].astype(int)
df["audiAcc"] = df["audiAcc"].astype(int)
df["scrnCnt"] = df["scrnCnt"].astype(int)

# -----------------------------------------------------------------------------
# 7. 1위 영화 주요 지표 카드 (Metric 3장)
# -----------------------------------------------------------------------------
top_movie = df.iloc[0]

st.subheader(f"🥇 1위: {top_movie['movieNm']}")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="어제 관객수",
        value=f"{top_movie['audiCnt']:,} 명"
    )

with col2:
    st.metric(
        label="누적 관객수",
        value=f"{top_movie['audiAcc']:,} 명"
    )

with col3:
    st.metric(
        label="상영 스크린수",
        value=f"{top_movie['scrnCnt']:,} 개"
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# 8. 관객수 상위 5편 막대그래프 (Plotly)
# -----------------------------------------------------------------------------
st.subheader("📊 관객수 상위 5편")

top5_df = df.head(5).copy()
# 그래프 시각 시 순위 순서(1위가 맨 위)대로 보이도록 역순 정렬
top5_df = top5_df.sort_values(by="rank", ascending=False)

fig = px.bar(
    top5_df,
    x="audiCnt",
    y="movieNm",
    orientation="h",
    text="audiCnt",
    labels={"audiCnt": "어제 관객수(명)", "movieNm": "영화명"},
    color="audiCnt",
    color_continuous_scale="Blues"
)

# 그래프 텍스트 및 레이아웃 설정
fig.update_traces(
    texttemplate="%{text:,}명",
    textposition="outside"
)
fig.update_layout(
    showlegend=False,
    coloraxis_showscale=False,
    height=350,
    margin=dict(l=20, r=40, t=20, b=20)
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# 9. 전체 박스오피스 순위 표 (DataFrame)
# -----------------------------------------------------------------------------
st.subheader("📋 전체 박스오피스 순위")

# 화면에 표시할 컬럼 정리 및 이름 변경
display_df = df[[
    "rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"
]].copy()

display_df.columns = [
    "순위", "영화명", "개봉일", "어제 관객수", "누적 관객수", "스크린수"
]

# 숫자에 세 자리마다 쉼표(,) 포맷팅을 적용하여 표시
st.dataframe(
    display_df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "순위": st.column_config.NumberColumn("순위", format="%d위"),
        "어제 관객수": st.column_config.NumberColumn("어제 관객수", format="%d명"),
        "누적 관객수": st.column_config.NumberColumn("누적 관객수", format="%d명"),
        "스크린수": st.column_config.NumberColumn("스크린수", format="%d개"),
    }
)
