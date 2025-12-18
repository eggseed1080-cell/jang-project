import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime

# ==========================================
# 1. 구글 시트 연동 설정
# ==========================================
def get_google_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 1. 스트림릿 클라우드의 비밀 금고(secrets)에서 키를 가져옴
    # (로컬에서 실행할 때는 .streamlit/secrets.toml 파일이 필요하거나, 기존 json 방식을 써야 함)
    try:
        # 배포용 코드
        key_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    except:
        # 로컬 테스트용 (내 컴퓨터에서 돌릴 때)
        creds = ServiceAccountCredentials.from_json_keyfile_name("gsheet_key.json", scope)
        
    return gspread.authorize(creds)

def add_batch_to_sheet(rows_data):
    try:
        client = get_google_client()
        sheet = client.open("주문관리").worksheet("택배주문")
        sheet.append_rows(rows_data) # 여러 줄 한방에 저장
        return True
    except Exception as e:
        return str(e)

# ==========================================
# 2. 화면 구성 (UI)
# ==========================================
st.set_page_config(page_title="장건강 프로젝트 정기주문", page_icon="🌿", layout="wide")

st.title("🌿 장건강 정기배송 신청")
st.markdown("시작일만 선택하면 **4주치 스케줄**이 자동으로 생성됩니다!")

# --- [1] 고객 정보 입력 ---
with st.container():
    st.subheader("👤 고객 정보")
    col1, col2 = st.columns(2)
    with col1:
        region = st.text_input("지역 (필수)", placeholder="예: 서울 강남")
        name = st.text_input("이름 (필수)", placeholder="홍길동")
    with col2:
        phone = st.text_input("전화번호", placeholder="010-1234-5678")
        address = st.text_input("상세 주소", placeholder="아파트 동호수까지 정확히")

# --- [2] 스케줄 설정 ---
st.divider()
st.subheader("🗓️ 배송 스케줄 설정")

col_date, col_check = st.columns([1, 2])
with col_date:
    start_date = st.date_input("배송 시작일 선택", datetime.date.today())
with col_check:
    st.write("") 
    st.write("") 
    # 체크박스: 1주차 내용으로 통일하기
    copy_week1 = st.checkbox("✅ 1주차 주문 내용을 4주 내내 동일하게 적용하기", value=True)

# --- [3] 주차별 주문 입력 (4주치) ---
st.divider()
weeks_data = [] # 입력된 데이터를 모을 리스트

# 4주치 루프 돌리기
for i in range(4):
    week_num = i + 1
    # 날짜 자동 계산 (시작일 + 7일씩 증가)
    target_date = start_date + datetime.timedelta(weeks=i)
    target_date_str = target_date.strftime("%Y-%m-%d")
    
    with st.expander(f"📦 {week_num}주차 배송 ({target_date_str})", expanded=(i==0)):
        c1, c2, c3, c4 = st.columns(4)
        
        # 1주차가 아니고 + '동일 적용' 체크되어 있으면 -> 1주차 값을 그대로 보여줌 (비활성화)
        disabled_status = (copy_week1 and i > 0)
        
        # 키(key)를 다르게 줘야 에러가 안 남
        if disabled_status:
            # 1주차(weeks_data[0])의 값을 가져와서 표시만 함
            ref_data = weeks_data[0]
            qty_moo = st.number_input(f"무가당 2L ({week_num}주)", value=ref_data['moo'], disabled=True, key=f"w{i}_moo")
            qty_ga = st.number_input(f"가당 2L ({week_num}주)", value=ref_data['ga'], disabled=True, key=f"w{i}_ga")
            qty_berry = st.number_input(f"베리 500ml ({week_num}주)", value=ref_data['berry'], disabled=True, key=f"w{i}_berry")
            qty_greek = st.number_input(f"그릭 300g ({week_num}주)", value=ref_data['greek'], disabled=True, key=f"w{i}_greek")
        else:
            # 직접 입력
            qty_moo = st.number_input("무가당 2L", min_value=0, value=0, key=f"w{i}_moo")
            qty_ga = st.number_input("가당 2L", min_value=0, value=0, key=f"w{i}_ga")
            qty_berry = st.number_input("베리 500ml", min_value=0, value=0, key=f"w{i}_berry")
            qty_greek = st.number_input("그릭 300g", min_value=0, value=0, key=f"w{i}_greek")

        # 데이터 임시 저장
        weeks_data.append({
            'date': target_date_str,
            'moo': qty_moo, 'ga': qty_ga, 'berry': qty_berry, 'greek': qty_greek
        })

# --- [4] 최종 제출 버튼 ---
st.divider()
submit_btn = st.button("🚀 4주치 스케줄 한 번에 저장하기", type="primary", use_container_width=True)

if submit_btn:
    if not name or not region or not address:
        st.error("🚨 지역, 이름, 주소는 필수 입력 항목입니다!")
    else:
        # 저장할 데이터 리스트 만들기
        final_rows = []
        now_date = datetime.datetime.now().strftime("%Y-%m-%d")
        now_time = datetime.datetime.now().strftime("%H:%M:%S")

        count_total = 0
        
        for data in weeks_data:
            # 수량이 하나라도 있는 주차만 저장
            if (data['moo'] + data['ga'] + data['berry'] + data['greek']) > 0:
                # 엑셀 순서: [작성일, 시간, 배송일, 지역, 이름, 주소, 번호, 무, 가, 베, 그]
                row = [
                    now_date, now_time, data['date'], 
                    region, name, address, phone,
                    data['moo'], data['ga'], data['berry'], data['greek']
                ]
                final_rows.append(row)
                count_total += 1
        
        if count_total == 0:
            st.warning("🤔 선택된 상품이 하나도 없습니다.")
        else:
            with st.spinner("엑셀에 저장 중입니다..."):
                res = add_batch_to_sheet(final_rows)
                
            if res == True:
                st.success(f"🎉 저장 완료! 총 {count_total}건의 주문이 등록되었습니다.")
                st.balloons()
            else:

                st.error(f"저장 실패: {res}")
