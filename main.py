import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz

# -----------------------------------------------------------------------------
# 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="어제 박스오피스 순위",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제 일별 박스오피스 순위")
st.write("KOBIS(영화관입장권통합전산망) 및 TMDB API를 활용하여 어제의 박스오피스 순위와 포스터를 불러옵니다.")

# -----------------------------------------------------------------------------
# 1. API 키 불러오기 (Streamlit Secrets 활용)
# -----------------------------------------------------------------------------
# 필수: KOBIS_KEY
if "KOBIS_KEY" not in st.secrets:
    st.error("🔑 필수 API 키(KOBIS_KEY)를 찾을 수 없습니다.")
    st.info("""
    **확인 조치 사항:**
    1. 스트림릿 클라우드 배포 페이지의 **App Settings > Secrets** 메뉴로 이동합니다.
    2. 아래 형식으로 KOBIS API 키를 추가해 주세요:
       ```toml
       KOBIS_KEY = "발급받은_KOBIS_인증키"
       TMDB_KEY = "발급받은_TMDB_API키" # 선택(포스터 표시용)
       ```
    """)
    st.stop()

kobis_key = st.secrets["KOBIS_KEY"]
tmdb_key = st.secrets.get("TMDB_KEY", None) # TMDB 키가 없어도 앱이 튕기지 않도록 처리

# -----------------------------------------------------------------------------
# 2. 한국 시간(KST) 기준 '어제' 날짜 계산하기
# -----------------------------------------------------------------------------
kst = pytz.timezone('Asia/Seoul')
now_kst = datetime.now(kst)
yesterday = now_kst - timedelta(days=1)
target_date_str = yesterday.strftime("%Y%m%d") # YYYYMMDD 포맷
formatted_yesterday_display = yesterday.strftime("%Y년 %m월 %d일")

st.caption(f"📅 기준 날짜(어제): **{formatted_yesterday_display}** (targetDt: `{target_date_str}`)")

# -----------------------------------------------------------------------------
# 3. KOBIS & TMDB API 데이터 요청 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)  # 1시간 동안 KOBIS 데이터 캐싱
def fetch_boxoffice_data(key, target_dt):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": key, "targetDt": target_dt}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"

@st.cache_data(ttl=86400) # 24시간 동안 포스터 이미지 URL 캐싱
def get_movie_poster(movie_title, api_key):
    """TMDB API를 사용하여 영화 제목으로 포스터 이미지 URL을 검색합니다."""
    if not api_key:
        return None
    
    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": api_key,
        "query": movie_title,
        "language": "ko-KR"
    }
    try:
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            results = data.get("results", [])
            if results and results[0].get("poster_path"):
                # TMDB 이미지 서버 URL + 이미지 경로 조합
                return f"https://image.tmdb.org/t/p/w500{results[0]['poster_path']}"
    except Exception:
        pass
    return None

# KOBIS 데이터 불러오기
data, error_msg = fetch_boxoffice_data(kobis_key, target_date_str)

# -----------------------------------------------------------------------------
# 4. 예외 및 오류 처리
# -----------------------------------------------------------------------------
if error_msg:
    st.error("❌ 데이터를 가져오는 데 실패했습니다.")
    st.info(f"**확인 조치 사항:**\n- 인터넷 연결 상태를 확인해 주세요.\n- 오류 상세 내용: `{error_msg}`")
    st.stop()

if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error("⚠️ KOBIS API 오류 응답을 수신했습니다 (인증키 문제 등).")
    st.warning(f"**오류 메시지:** {fault.get('message', '알 수 없는 오류')} (코드: {fault.get('errorCode', 'N/A')})")
    st.info("""
    **확인 조치 사항:**
    1. KOBIS OpenAPI 사이트(kobis.or.kr)에서 발급받은 키가 유효한지 확인하세요.
    2. Secrets에 입력한 `KOBIS_KEY` 값에 오타가 없는지 점검하세요.
    """)
    st.stop()

boxoffice_result = data.get("boxOfficeResult", {})
movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

if not movie_list:
    st.warning("📭 조회된 영화 데이터가 없습니다.")
    st.info("""
    **확인 조치 사항:**
    1. 선택한 날짜에 영화관 집계 데이터가 아직 업로드되지 않았을 수 있습니다.
    2. 잠시 후 다시 시도해 주세요.
    """)
    st.stop()

# -----------------------------------------------------------------------------
# 5. 데이터 가공
# -----------------------------------------------------------------------------
df = pd.DataFrame(movie_list)

# 수치형 변환
numeric_cols = ['rank', 'audiCnt', 'audiAcc', 'scrnCnt', 'showCnt', 'rankInten']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# -----------------------------------------------------------------------------
# 6. 1위 영화 하이라이트 (포스터 + 지표 카드)
# -----------------------------------------------------------------------------
top_movie = df.iloc[0]
top_poster_url = get_movie_poster(top_movie['movieNm'], tmdb_key)

st.subheader(f"🥇 1위: {top_movie['movieNm']}")

col_poster, col_metrics = st.columns([1, 3])

with col_poster:
    if top_poster_url:
        st.image(top_poster_url, caption=f"{top_movie['movieNm']} 포스터", use_container_width=True)
    else:
        st.info("🖼️ 포스터 이미지를 제공할 수 없습니다.\n(TMDB_KEY 설정 필요)")

with col_metrics:
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        st.metric(label="어제 관객수", value=f"{int(top_movie['audiCnt']):,} 명")
    with m_col2:
        st.metric(label="누적 관객수", value=f"{int(top_movie['audiAcc']):,} 명")
    with m_col3:
        st.metric(label="상영 스크린수", value=f"{int(top_movie['scrnCnt']):,} 개")

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
# 8. TOP 10 영화 포스터 갤러리 (카드 형태)
# -----------------------------------------------------------------------------
st.subheader("🖼️ TOP 10 영화 포스터")

# 5개씩 2줄로 배치
for row_idx in range(0, 10, 5):
    cols = st.columns(5)
    for i, col in enumerate(cols):
        movie_idx = row_idx + i
        if movie_idx < len(df):
            movie = df.iloc[movie_idx]
            poster_url = get_movie_poster(movie['movieNm'], tmdb_key)
            
            with col:
                if poster_url:
                    st.image(poster_url, use_container_width=True)
                else:
                    # 포스터가 없을 때 빈 영역 대체
                    st.markdown("🖼️ **포스터 없음**")
                
                st.markdown(f"**{int(movie['rank'])}위. {movie['movieNm']}**")
                st.caption(f"관객수: {int(movie['audiCnt']):,}명")

st.divider()

# -----------------------------------------------------------------------------
# 9. 박스오피스 전체 순위 표
# -----------------------------------------------------------------------------
st.subheader("📋 전체 박스오피스 순위 표")

display_df = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()

# 포맷팅
display_df['rank'] = display_df['rank'].astype(int)
display_df['audiCnt'] = display_df['audiCnt'].apply(lambda x: f"{int(x):,}")
display_df['audiAcc'] = display_df['audiAcc'].apply(lambda x: f"{int(x):,}")
display_df['scrnCnt'] = display_df['scrnCnt'].apply(lambda x: f"{int(x):,}")

display_df.columns = ['순위', '영화명', '개봉일', '관객수(명)', '누적관객(명)', '스크린수(개)']

st.dataframe(display_df, use_container_width=True, hide_index=True)
