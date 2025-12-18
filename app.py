import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pandas as pd
import time

# ==========================================
# 1. 설정 및 DB 연결 함수
# ==========================================
st.set_page_config(page_title="장건강 프로젝트", page_icon="🌿", layout="wide")

def get_google_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # Streamlit Cloud 배포용
        key_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    except:
        # 로컬 테스트용
        creds = ServiceAccountCredentials.from_json_keyfile_name("gsheet_key.json", scope)
    return gspread.authorize(creds)

# --- [핵심 로직 1] 회원 정보 관리 (저장 및 업데이트) ---
def update_member_info(phone, name, region, address):
    try:
        client = get_google_client()
        sheet = client.open("주문관리").worksheet("회원관리")
        
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 1. 이미 등록된 번호인지 찾기
        try:
            cell = sheet.find(phone) # 전화번호로 검색
            # [기존 회원] -> 주소와 지역, 최근주문일 업데이트
            # cell.row는 찾은 행 번호
            sheet.update_cell(cell.row, 2, name)    # 이름 업데이트 (혹시 개명했을수도 있으니)
            sheet.update_cell(cell.row, 3, region)  # 지역 업데이트
            sheet.update_cell(cell.row, 4, address) # 주소 업데이트 (이사 갔을 수 있음)
            sheet.update_cell(cell.row, 5, now)     # 최근주문일 갱신
            return "updated"
        except gspread.exceptions.CellNotFound:
            # [신규 회원] -> 맨 아래에 추가
            # 순서: 전화번호, 이름, 지역, 주소, 최근주문일, 가입일
            sheet.append_row([phone, name, region, address, now, now])
            return "new"
            
    except Exception as e:
        return str(e)

# --- [핵심 로직 2] 주문 내역 저장 (가볍게 저장) ---
def add_orders(phone, orders_data):
    try:
        client = get_google_client()
        sheet = client.open("주문관리").worksheet("주문내역")
        
        now_full = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        rows_to_add = []
        for order in orders_data:
            # 주문ID 생성 (날짜+시간+번호뒷자리) - 유니크하게 만들기 위함
            order_id = datetime.datetime.now().strftime("%y%m%d%H%M%S") + phone[-4:]
            
            # 순서: 주문ID, 전화번호, 배송희망일, 무, 가, 베, 그, 주문일시
            # (이름, 주소는 저장 안 함! 전화번호로 연결됨)
            row = [
                order_id, phone, order['date'],
                order['moo'], order['ga'], order['berry'], order['greek'],
                now_full
            ]
            rows_to_add.append(row)
            
        sheet.append_rows(rows_to_add)
        return True
    except Exception as e:
        return str(e)

# --- [핵심 로직 3] 관리자용 조회 (조인: 두 시트를 합쳐서 보여줌) ---
def get_joined_data():
    client = get_google_client()
    # 두 시트를 다 가져옴
    sheet_orders = client.open("주문관리").worksheet("주문내역")
    sheet_members = client.open("주문관리").worksheet("회원관리")
    
    df_orders = pd.DataFrame(sheet_orders.get_all_values()[1:], columns=sheet_orders.get_all_values()[0])
    df_members = pd.DataFrame(sheet_members.get_all_values()[1:], columns=sheet_members.get_all_values()[0])
    
    # 전화번호를 기준으로 합치기 (VLOOKUP과 같은 원리)
    # orders 테이블에 members 테이블을 붙임
    if not df_orders.empty and not df_members.empty:
        merged_df = pd.merge(df_orders, df_members, on="전화번호", how="left")
        return merged_df
    return df_orders

# ==========================================
# 2. 화면 구성
# ==========================================
tab1, tab2 = st.tabs(["📝 주문하기", "🔒 관리자(통합조회)"])

with tab1:
    st.title("🌿 장건강 정기배송 (DB분리형)")
    st.info("고객님은 주문만 하세요. 회원 정보 관리는 알아서 됩니다!")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            region = st.text_input("지역", placeholder="예: 서울 강남")
            name = st.text_input("이름", placeholder="홍길동")
        with col2:
            phone = st.text_input("전화번호 (필수/ID)", placeholder="010-0000-0000")
            address = st.text_input("주소 (배송지)", placeholder="상세 주소 입력")

    st.subheader("🗓️ 스케줄 설정")
    c_date, c_chk = st.columns([1,2])
    with c_date:
        start_date = st.date_input("시작일", datetime.date.today())
    with c_chk:
        st.write("")
        st.write("")
        copy_week1 = st.checkbox("✅ 1주차 동일 적용", value=True)

    weeks_data = []
    for i in range(4):
        w_num = i+1
        t_date = (start_date + datetime.timedelta(weeks=i)).strftime("%Y-%m-%d")
        with st.expander(f"{w_num}주차 ({t_date})", expanded=(i==0)):
            c1, c2, c3, c4 = st.columns(4)
            disabled = (copy_week1 and i > 0)
            
            if disabled:
                ref = weeks_data[0]
                m = st.number_input(f"무({w_num})", value=ref['moo'], disabled=True, key=f"d_m{i}")
                g = st.number_input(f"가({w_num})", value=ref['ga'], disabled=True, key=f"d_g{i}")
                b = st.number_input(f"베({w_num})", value=ref['berry'], disabled=True, key=f"d_b{i}")
                k = st.number_input(f"그({w_num})", value=ref['greek'], disabled=True, key=f"d_k{i}")
            else:
                m = st.number_input("무가당", min_value=0, key=f"m{i}")
                g = st.number_input("가당", min_value=0, key=f"g{i}")
                b = st.number_input("베리", min_value=0, key=f"b{i}")
                k = st.number_input("그릭", min_value=0, key=f"k{i}")
            
            weeks_data.append({'date':t_date, 'moo':m, 'ga':g, 'berry':b, 'greek':k})

    if st.button("🚀 주문 및 회원정보 저장", type="primary", use_container_width=True):
        if not phone or not name or not address:
            st.error("전화번호, 이름, 주소는 필수입니다!")
        else:
            with st.spinner("회원 정보 확인 및 주문 저장 중..."):
                # 1. 회원 정보 업데이트 (혹은 신규등록)
                mem_res = update_member_info(phone, name, region, address)
                
                # 2. 주문 데이터 추리기
                valid_orders = []
                for order in weeks_data:
                    if (order['moo']+order['ga']+order['berry']+order['greek']) > 0:
                        valid_orders.append(order)
                
                if not valid_orders:
                    st.warning("상품을 선택해주세요.")
                else:
                    # 3. 주문 저장
                    ord_res = add_orders(phone, valid_orders)
                    
                    if ord_res == True:
                        msg = "🎉 주문 완료!"
                        if mem_res == "new": msg += " (신규회원 등록됨)"
                        elif mem_res == "updated": msg += " (회원정보 갱신됨)"
                        st.success(msg)
                        st.balloons()
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(f"주문 저장 실패: {ord_res}")

with tab2:
    st.header("🔒 관리자 통합 조회")
    pwd = st.text_input("비밀번호", type="password")
    if pwd == "1234": # 비밀번호 설정
        if st.button("🔄 데이터 불러오기"):
            st.rerun()
            
        df = get_joined_data() # 여기서 두 시트를 합쳐서 가져옴
        
        if not df.empty:
            st.subheader("📦 전체 주문 목록 (회원정보 결합됨)")
            st.dataframe(df)
            
            st.info("💡 팁: 실제 엑셀 시트는 '회원관리'와 '주문내역'으로 나뉘어 있지만, 여기서는 합쳐서 보여줍니다.")
