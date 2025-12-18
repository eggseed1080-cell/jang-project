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

# --- [핵심 로직 1] 회원 정보 관리 (수정된 안전 버전) ---
# --- [핵심 로직 1] 회원 정보 관리 (한국 시간 적용) ---
def update_member_info(phone, name, region, address):
    try:
        client = get_google_client()
        sheet = client.open("주문관리").worksheet("회원관리")
        
        # [수정됨] 여기도 9시간을 더해서 한국 날짜로 계산
        now_utc = datetime.datetime.utcnow()
        now_kst = now_utc + datetime.timedelta(hours=9)
        today_kst = now_kst.strftime("%Y-%m-%d")
        
        cell = None
        try:
            cell = sheet.find(phone)
        except:
            cell = None

        if cell:
            # [기존 회원]
            sheet.update_cell(cell.row, 2, name)
            sheet.update_cell(cell.row, 3, region)
            sheet.update_cell(cell.row, 4, address)
            sheet.update_cell(cell.row, 5, today_kst) # 한국 날짜
            return "updated"
        else:
            # [신규 회원]
            sheet.append_row([phone, name, region, address, today_kst, today_kst])
            return "new"
            
    except Exception as e:
        return str(e)

# --- [핵심 로직 2] 주문 내역 저장 (한국 시간 적용) ---
def add_orders(phone, orders_data):
    try:
        client = get_google_client()
        sheet = client.open("주문관리").worksheet("주문내역")
        
        # [수정됨] 서버 시간(UTC)에 9시간을 더해 한국 시간(KST) 만들기
        now_utc = datetime.datetime.utcnow()
        now_kst = now_utc + datetime.timedelta(hours=9)
        now_full = now_kst.strftime("%Y-%m-%d %H:%M:%S")
        
        rows_to_add = []
        for order in orders_data:
            # 주문ID 생성 (한국시간 기준 날짜+시간+번호뒷자리)
            order_id = now_kst.strftime("%y%m%d%H%M%S") + phone[-4:]
            
            # 순서: 주문ID, 전화번호, 배송희망일, 무, 가, 베, 그, 주문일시
            row = [
                order_id, phone, order['date'],
                order['moo'], order['ga'], order['berry'], order['greek'],
                now_full # 한국 시간 저장
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

# --------------------------------------------------------------------------------
# [탭 1] 고객용 주문 화면 (날짜 개별 수정 기능 추가됨)
# --------------------------------------------------------------------------------
# --------------------------------------------------------------------------------
# [탭 1] 고객용 주문 화면 (동기화 기능 강화 버전)
# --------------------------------------------------------------------------------
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
        master_start_date = st.date_input("기준 시작일", datetime.date.today())
    with c_chk:
        st.write("")
        st.write("")
        # [중요] 값이 바뀔 때마다 즉시 새로고침해서 적용하도록 설정
        copy_week1 = st.checkbox("✅ 상품 구성을 4주간 동일하게 적용", value=True)

    weeks_data = []
    
    # [핵심 변경] 1주차 값을 저장할 변수 미리 선언
    w1_moo, w1_ga, w1_berry, w1_greek = 0, 0, 0, 0

    for i in range(4):
        w_num = i + 1
        default_date = master_start_date + datetime.timedelta(weeks=i)
        
        # 1주차(i=0)인 경우와 나머지(i>0)를 명확히 분리
        is_first_week = (i == 0)
        
        # 박스 열기 (첫째주는 무조건, 나머지는 닫아둠)
        with st.expander(f"📦 {w_num}주차 설정", expanded=is_first_week):
            col_d, col_prod = st.columns([1, 3])
            
            # 1. 날짜 선택
            with col_d:
                # 2주차 이상인데 체크박스 켜져있으면 날짜도 살짝 비활성 느낌 줄수있으나
                # 날짜는 개별 수정 가능하게 두는 것이 좋음
                selected_date = st.date_input(
                    f"{w_num}주차 날짜", 
                    value=default_date, 
                    key=f"date_{i}"
                )
                selected_date_str = selected_date.strftime("%Y-%m-%d")

            # 2. 상품 수량 입력
            with col_prod:
                c1, c2, c3, c4 = st.columns(4)
                
                # [로직 1] 1주차인 경우 -> 무조건 입력 받음
                if is_first_week:
                    m = c1.number_input("무가당", min_value=0, key="w1_m")
                    g = c2.number_input("가당", min_value=0, key="w1_g")
                    b = c3.number_input("베리", min_value=0, key="w1_b")
                    k = c4.number_input("그릭", min_value=0, key="w1_k")
                    
                    # 1주차 값을 변수에 저장 (나머지 주차가 갖다 쓰기 위해)
                    w1_moo, w1_ga, w1_berry, w1_greek = m, g, b, k
                
                # [로직 2] 2주차 이상이고 + 체크박스 ON -> 1주차 값 강제 적용 (수정불가)
                elif copy_week1:
                    # key를 다르게 줘서('copy_') 새로 그려지게 함 (그래야 값이 갱신됨)
                    m = c1.number_input(f"무({w_num})", value=w1_moo, disabled=True, key=f"copy_m{i}")
                    g = c2.number_input(f"가({w_num})", value=w1_ga, disabled=True, key=f"copy_g{i}")
                    b = c3.number_input(f"베({w_num})", value=w1_berry, disabled=True, key=f"copy_b{i}")
                    k = c4.number_input(f"그({w_num})", value=w1_greek, disabled=True, key=f"copy_k{i}")
                
                # [로직 3] 2주차 이상이지만 + 체크박스 OFF -> 개별 입력 가능
                else:
                    m = c1.number_input("무가당", min_value=0, value=0, key=f"manual_m{i}")
                    g = c2.number_input("가당", min_value=0, value=0, key=f"manual_g{i}")
                    b = c3.number_input("베리", min_value=0, value=0, key=f"manual_b{i}")
                    k = c4.number_input("그릭", min_value=0, value=0, key=f"manual_k{i}")

            # 리스트에 담기
            weeks_data.append({'date': selected_date_str, 'moo':m, 'ga':g, 'berry':b, 'greek':k})

    st.divider()

    # 저장 버튼
    if st.button("🚀 주문 및 회원정보 저장", type="primary", use_container_width=True):
        if not phone or not name or not address:
            st.error("🚨 전화번호, 이름, 주소는 필수 입력 항목입니다!")
        else:
            with st.spinner("처리 중..."):
                mem_res = update_member_info(phone, name, region, address)
                
                if mem_res not in ["new", "updated"]:
                    st.error(f"🚨 회원 정보 저장 실패: {mem_res}")
                else:
                    valid_orders = []
                    for order in weeks_data:
                        if (order['moo']+order['ga']+order['berry']+order['greek']) > 0:
                            valid_orders.append(order)
                    
                    if not valid_orders:
                        st.warning("🤔 선택된 상품이 없습니다.")
                    else:
                        ord_res = add_orders(phone, valid_orders)
                        if ord_res == True:
                            msg = "🎉 주문이 완료되었습니다!"
                            if mem_res == "new": msg += "\n(✨신규 회원 등록됨)"
                            elif mem_res == "updated": msg += "\n(✅회원 정보 갱신됨)"
                            st.success(msg)
                            st.balloons()
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(f"❌ 주문 저장 실패: {ord_res}")

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






