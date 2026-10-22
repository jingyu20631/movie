import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz

# -----------------------------------------------------------------------------
# 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="일별 박스오피스 조회",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 일별 박스오피스 순위 조회")
st.write("KOBIS(영화관입장권통합전산망) 공식 API를 활용하여 원하는 날짜의 박스오피스 정보를 불러옵니다.")

# -----------------------------------------------------------------------------
# 1. API 키 불러오기 (Streamlit Secrets 활용)
# -----------------------------------------------------------------------------
if "KOBIS_KEY" not in st.secrets:
    st.error("🔑 API 키(KOBIS_KEY)를 찾을 수 없습니다.")
    st.info("""
    **확인 조치 사항:**
    1. 스트림릿 클라우드 배포 페이지의 **App Settings > Secrets** 메뉴로 이동합니다.
    2. 아래 형식으로 API 키를 추가하고 저장해 주세요:
       ```toml
       KOBIS_KEY = "발급받은_인증키_입력"
       ```
    """)
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# -----------------------------------------------------------------------------
# 2. 날짜 선택기 (한국 시간 KST 기준, 최대 '어제'까지)
# -----------------------------------------------------------------------------
kst = pytz.timezone('Asia/Seoul')
now_kst = datetime.now(kst)
yesterday = (now_kst - timedelta(days=1)).date()

# 달력 선택 UI (최대 선택 가능 날짜는 어제)
selected_date = st.date_input(
    label="📅 조회할 날짜를 선택하세요 (오늘 날짜 이전만 선택 가능)",
    value=yesterday,
    max_value=yesterday
)

# API 요청용 날짜 포맷 (YYYYMMDD)
target_date_str = selected_date.strftime("%Y%m%d")
formatted_selected_display = selected_date.strftime("%Y년 %m월 %d일")

st.caption(f"📅 선택된 날짜: **{formatted_selected_display}** (targetDt: `{target_date_str}`)")

# -----------------------------------------------------------------------------
# 3. KOBIS API 데이터 요청 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)  # 1시간 동안 API 응답 캐싱
def fetch_boxoffice_data(key, target_dt):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": key,
        "targetDt": target_dt
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"

# API 호출
data, error_msg = fetch_boxoffice_data(api_key, target_date_str)

# -----------------------------------------------------------------------------
# 4. 예외 및 오류 처리
# -----------------------------------------------------------------------------
if error_msg:
    st.error("❌ 데이터를 가져오는 데 실패했습니다.")
    st.info(f"**확인 조치 사항:**\n- 인터넷 연결 상태를 확인해 주세요.\n- 오류 상세 내용: `{error_msg}`")
    st.stop()

if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error("⚠️ KOBIS API 오류 응답을 수신했습니다.")
    st.warning(f"**오류 메시지:** {fault.get('message', '알 수 없는 오류')} (코드: {fault.get('errorCode', 'N/A')})")
    st.info("""
    **확인 조치 사항:**
    1. KOBIS OpenAPI 사이트(kobis.or.kr)에서 발급받은 키가 유효한지 확인하세요.
    2. Streamlit Secrets에 입력한 `KOBIS_KEY` 값에 오타가 없는지 점검하세요.
    """)
    st.stop()

boxoffice_result = data.get("boxOfficeResult", {})
movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

# 영화 목록이 빈 경우 안내
if not movie_list:
    st.warning("📭 그날은 아직 집계 전입니다.")
    st.info("선택하신 날짜의 영화관 입장권 집계 데이터가 아직 등록되지 않았거나 집계 중입니다. 다른 날짜를 선택해 보세요.")
    st.stop()

# -----------------------------------------------------------------------------
# 5. 데이터 가공 (수치 변환 및 커스텀 컬럼 추가)
# -----------------------------------------------------------------------------
df = pd.DataFrame(movie_list)

# 수치형 컬럼 변환
numeric_cols = ['rank', 'audiCnt', 'audiAcc', 'scrnCnt', 'showCnt', 'rankInten']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# 1) 순위 변감(rankInten) 화살표 표시 함수
def format_rank_inten(val):
    val = int(val)
    if val > 0:
        return f"🔺 {val}"  # 빨간 위 화살표 (상승)
    elif val < 0:
        return f"🔹 {abs(val)}"  # 파란 아래 화살표 (하강)
    else:
        return "-"  # 변동 없음

df['rankChange'] = df['rankInten'].apply(format_rank_inten)

# 2) 누적관객 100만 이상 시 영화명 옆에 🏆 이모지 추가 함수
def format_movie_title(row):
    title = row['movieNm']
    if row['audiAcc'] >= 1_000_000:
        return f"{title} 🏆"
    return title

df['displayTitle'] = df.apply(format_movie_title, axis=1)

# -----------------------------------------------------------------------------
# 6. 1위 영화 지표 카드 세 장
# -----------------------------------------------------------------------------
top_movie = df.iloc[0]

st.subheader(f"🥇 1위: {top_movie['displayTitle']}")

col1, col2, col3 = st.columns(3)

with col1:
    audi_cnt = int(top_movie['audiCnt'])
    st.metric(
        label="당일 관객수",
        value=f"{audi_cnt:,} 명"
    )

with col2:
    audi_acc = int(top_movie['audiAcc'])
    st.metric(
        label="누적 관객수",
        value=f"{audi_acc:,} 명"
    )

with col3:
    scrn_cnt = int(top_movie['scrnCnt'])
    st.metric(
        label="상영 스크린수",
        value=f"{scrn_cnt:,} 개"
    )

st.divider()

# -----------------------------------------------------------------------------
# 7. 관객수 상위 5편 막대그래프
# -----------------------------------------------------------------------------
st.subheader("📊 관객수 TOP 5")

top5_df = df.head(5).copy()
chart_data = top5_df[['movieNm', 'audiCnt']].set_index('movieNm')
chart_data.columns = ['관객수']

st.bar_chart(chart_data)

st.divider()

# -----------------------------------------------------------------------------
# 8. 박스오피스 전체 순위 표
# -----------------------------------------------------------------------------
st.subheader("📋 전체 박스오피스 순위 표")

# 표에 출력할 컬럼 가공
display_df = df[['rank', 'rankChange', 'displayTitle', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()

# 보기 좋은 포맷팅 (천 단위 쉼표)
display_df['rank'] = display_df['rank'].astype(int)
display_df['audiCnt'] = display_df['audiCnt'].apply(lambda x: f"{int(x):,}")
display_df['audiAcc'] = display_df['audiAcc'].apply(lambda x: f"{int(x):,}")
display_df['scrnCnt'] = display_df['scrnCnt'].apply(lambda x: f"{int(x):,}")

# 열 이름 한글화
display_df.columns = ['순위', '순위변동', '영화명', '개봉일', '관객수(명)', '누적관객(명)', '스크린수(개)']

st.dataframe(display_df, use_container_width=True, hide_index=True)
