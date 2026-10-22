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
st.write("KOBIS(영화관입장권통합전산망) 공식 API를 활용하여 한국 시간 기준 어제의 박스오피스 정보를 불러옵니다.")

# -----------------------------------------------------------------------------
# 1. API 키 불러오기 (Streamlit Secrets 활용)
# -----------------------------------------------------------------------------
# secrets.toml 또는 Streamlit Cloud Secrets 설정에 등록된 API 키를 확인합니다.
if "KOBIS_KEY" not in st.secrets:
    st.error("🔑 API 키(KOBIS_KEY)를 찾을 수 없습니다.")
    st.info("""
    **확인 조치 사항:**
    1. 스트림릿 클라우드 배포 페이지의 **App Settings > Secrets** 메뉴로 이동합니다.
    2. 아래 형식으로 API 키를 추가하고 저장해 주세요:
       ```toml
       KOBIS_KEY = "발급받은_인증키_입력"
       ```
    3. 로컬에서 실행 중이라면 `.streamlit/secrets.toml` 파일을 생성하여 키를 등록해 주세요.
    """)
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# -----------------------------------------------------------------------------
# 2. 한국 시간(KST) 기준 '어제' 날짜 계산하기
# -----------------------------------------------------------------------------
# 배포 서버(Streamlit Cloud)의 시계가 UTC 기준이더라도 정확히 한국 시간 어제를 계산합니다.
kst = pytz.timezone('Asia/Seoul')
now_kst = datetime.now(kst)
yesterday = now_kst - timedelta(days=1)
target_date_str = yesterday.strftime("%Y%m%d") # YYYYMMDD 여덟 자리 형식
formatted_yesterday_display = yesterday.strftime("%Y년 %m월 %d일")

st.caption(f"📅 기준 날짜(어제): **{formatted_yesterday_display}** (targetDt: `{target_date_str}`)")

# -----------------------------------------------------------------------------
# 3. KOBIS API 데이터 요청 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)  # 1시간 동안 API 응답을 캐싱하여 서버 과부하 및 속도 개선
def fetch_boxoffice_data(key, target_dt):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": key,
        "targetDt": target_dt
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        # HTTP 응답 상태 코드 체크 (200이 아닌 경우 예외 발생)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"

# API 호출 실행
data, error_msg = fetch_boxoffice_data(api_key, target_date_str)

# -----------------------------------------------------------------------------
# 4. 예외 및 오류 처리 (안내 문구 출력)
# -----------------------------------------------------------------------------
# 네트워크 연결 실패 시
if error_msg:
    st.error("❌ 데이터를 가져오는 데 실패했습니다.")
    st.info(f"**확인 조치 사항:**\n- 인터넷 연결 상태를 확인해 주세요.\n- 오류 상세 내용: `{error_msg}`")
    st.stop()

# KOBIS API는 키가 잘못되어도 200 응답과 함께 faultInfo 상자를 보냅니다.
if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error("⚠️ KOBIS API 오류 응답을 수신했습니다.")
    st.warning(f"**오류 메시지:** {fault.get('message', '알 수 없는 오류')} (코드: {fault.get('errorCode', 'N/A')})")
    st.info("""
    **확인 조치 사항:**
    1. KOBIS OpenAPI 사이트(kobis.or.kr)에서 발급받은 키가 유효한지 확인하세요.
    2. Streamlit Secrets에 입력한 `KOBIS_KEY` 값에 오타나 공백이 없는지 점검하세요.
    """)
    st.stop()

# 영화 목록 추출 및 빈 데이터 확인
boxoffice_result = data.get("boxOfficeResult", {})
movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

if not movie_list:
    st.warning("📭 조회된 영화 데이터가 없습니다.")
    st.info("""
    **확인 조치 사항:**
    1. 선택한 날짜에 영화관 집계 데이터가 아직 업로드되지 않았을 수 있습니다.
    2. KOBIS 서버 사정으로 집계가 지연되는 경우 잠시 후 다시 시도해 주세요.
    """)
    st.stop()

# -----------------------------------------------------------------------------
# 5. 데이터 가공 (문자열 -> 숫자 변환)
# -----------------------------------------------------------------------------
df = pd.DataFrame(movie_list)

# API 결과는 모든 숫자가 문자열 형태로 제공되므로 수치형 변환을 진행합니다.
numeric_cols = ['rank', 'audiCnt', 'audiAcc', 'scrnCnt', 'showCnt', 'rankInten']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# -----------------------------------------------------------------------------
# 6. 1위 영화 지표 카드 세 장으로 크게 보여주기
# -----------------------------------------------------------------------------
top_movie = df.iloc[0]

st.subheader(f"🥇 1위: {top_movie['movieNm']}")

col1, col2, col3 = st.columns(3)

with col1:
    audi_cnt = int(top_movie['audiCnt'])
    st.metric(
        label="어제 관객수",
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

# 막대그래프용 데이터셋 구성
chart_data = top5_df[['movieNm', 'audiCnt']].set_index('movieNm')
chart_data.columns = ['관객수']

st.bar_chart(chart_data)

st.divider()

# -----------------------------------------------------------------------------
# 8. 박스오피스 전체 순위 표
# -----------------------------------------------------------------------------
st.subheader("📋 전체 박스오피스 순위 표")

# 표시 대상 컬럼 추출 및 가공
display_df = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()

# 보기 좋게 천 단위 쉼표 포맷팅 적용
display_df['rank'] = display_df['rank'].astype(int)
display_df['audiCnt'] = display_df['audiCnt'].apply(lambda x: f"{int(x):,}")
display_df['audiAcc'] = display_df['audiAcc'].apply(lambda x: f"{int(x):,}")
display_df['scrnCnt'] = display_df['scrnCnt'].apply(lambda x: f"{int(x):,}")

# 한국어 컬럼명 변경
display_df.columns = ['순위', '영화명', '개봉일', '관객수(명)', '누적관객(명)', '스크린수(개)']

# 표 출력 (인덱스 열은 숨김)
st.dataframe(display_df, use_container_width=True, hide_index=True)
