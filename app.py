import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pandas as pd
import time
import re

# ==========================================
# 1. 기본 설정 및 인증
# ==========================================
st.set_page_config(page_title="장건강 프로젝트", page_icon="🌿", layout="wide")

# 관리자 비밀번호 (원하는 대로 변경 가능)
ADMIN_PASSWORD = "1234"

def get_google_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # 배포용 (Streamlit Cloud Secrets)
        key_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    except:
        # 로컬 테스트용 (내 컴퓨터)
        creds = ServiceAccountCredentials.from_json_keyfile_name("gsheet_key.json", scope)
    return gspread.authorize(creds)
    
# 전화번호 형식을 010-0000-0000 으로 통일해주는 함수
def normalize_phone(raw_phone):
    # 1. 숫자 외의 모든 문자 제거 (하이픈, 공백 등 다 삭제)
    only_digits = re.sub(r'[^0-9]', '', str(raw_phone))
    
    # 2. 010으로 시작하는 11자리 번호라면 하이픈(-)을 예쁘게 넣어줌
    if len(only_digits) == 11 and only_digits.startswith("010"):
        return f"{only_digits[:3]}-{only_digits[3:7]}-{only_digits[7:]}"
    
    # 그 외(02번호 등)는 그냥 숫자만 반환하거나 그대로 둠
    return only_digits
# ==========================================
# 2. 데이터 처리 함수 (핵심 로직)
# ==========================================

# [로직 1] 회원 정보 관리 (한국 시간 적용 + 안전한 에러 처리)
def update_member_info(phone, name, region, address):
    try:
        client = get_google_client()
        sheet = client.open("주문관리").worksheet("회원관리")
        
        # 한국 시간(KST) 구하기
        now_utc = datetime.datetime.utcnow()
        now_kst = now_utc + datetime.timedelta(hours=9)
        today_kst = now_kst.strftime("%Y-%m-%d")
        
        # 이미 있는 번호인지 찾기
        cell = None
        try:
            cell = sheet.find(phone)
        except:
            # 찾지 못하면(없는 번호면) None으로 처리하고 넘어감
            cell = None

        if cell:
            # [기존 회원] -> 정보 업데이트
            # cell.row는 찾은 행 번호
            sheet.update_cell(cell.row, 2, name)    # 이름
            sheet.update_cell(cell.row, 3, region)  # 지역
            sheet.update_cell(cell.row, 4, address) # 주소
            sheet.update_cell(cell.row, 5, today_kst) # 최근주문일
            return "updated"
        else:
            # [신규 회원] -> 맨 아래에 추가
            # 순서: 전화번호, 이름, 지역, 주소, 최근주문일, 가입일
            sheet.append_row([phone, name, region, address, today_kst, today_kst])
            return "new"
            
    except Exception as e:
        return str(e)

# [로직 2] 주문 내역 저장 (한국 시간 적용 + DB 분리형)
def add_orders(phone, orders_data):
    try:
        client = get_google_client()
        sheet = client.open("주문관리").worksheet("주문내역")
        
        # 한국 시간(KST) 구하기
        now_utc = datetime.datetime.utcnow()
        now_kst = now_utc + datetime.timedelta(hours=9)
        now_full = now_kst.strftime("%Y-%m-%d %H:%M:%S")
        
        rows_to_add = []
        for order in orders_data:
            # 주문ID 생성 (년월일시분초 + 번호뒷자리)
            order_id = now_kst.strftime("%y%m%d%H%M%S") + phone[-4:]
            
            # 순서: 주문ID, 전화번호, 배송희망일, 무, 가, 베, 그, 주문일시
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

# [로직 3] 관리자용 통합 데이터 조회
def get_joined_data():
    try:
        client = get_google_client()
        sheet_orders = client.open("주문관리").worksheet("주문내역")
        sheet_members = client.open("주문관리").worksheet("회원관리")
        
        df_orders = pd.DataFrame(sheet_orders.get_all_values()[1:], columns=sheet_orders.get_all_values()[0])
        df_members = pd.DataFrame(sheet_members.get_all_values()[1:], columns=sheet_members.get_all_values()[0])
        
        if not df_orders.empty and not df_members.empty:
            # 전화번호 기준으로 두 테이블 합치기
            merged_df = pd.merge(df_orders, df_members, on="전화번호", how="left")
            return merged_df
        return df_orders
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame()

# ==========================================
# 3. 화면 구성 (UI)
# ==========================================
tab1, tab2 = st.tabs(["📝 고객 주문하기", "🔒 사장님 전용 (관리자)"])

# --------------------------------------------------------------------------------
# [탭 1] 고객용 주문 화면
# --------------------------------------------------------------------------------
with tab1:
    st.title("🌿 장건강 정기배송 신청")
    st.info("고객님은 주문만 하세요. 회원 정보 관리는 알아서 됩니다!")
    
    # 1. 고객 정보 입력
    with st.container(border=True):
        st.subheader("👤 배송지 정보")
        col1, col2 = st.columns(2)
        with col1:
            region = st.text_input("지역 (필수)", placeholder="예: 서울 강남")
            name = st.text_input("이름 (필수)", placeholder="홍길동")
        with col2:
            phone = st.text_input("전화번호 (필수/ID)", placeholder="010-0000-0000")
            address = st.text_input("상세 주소 (필수)", placeholder="아파트 동호수까지")

    # 2. 스케줄 설정
    st.subheader("🗓️ 배송 스케줄 설정")
    c_date, c_chk = st.columns([1,2])
    with c_date:
        master_start_date = st.date_input("기준 시작일 선택", datetime.date.today())
    with c_chk:
        st.write("")
        st.write("")
        # 값이 바뀔 때마다 앱을 리로딩해서 즉시 적용
        copy_week1 = st.checkbox("✅ 상품 구성을 4주간 동일하게 적용", value=True)

    # 3. 4주치 입력 루프
    weeks_data = []
    
    # 1주차 값을 임시 저장할 변수들
    w1_moo, w1_ga, w1_berry, w1_greek = 0, 0, 0, 0

    for i in range(4):
        w_num = i + 1
        default_date = master_start_date + datetime.timedelta(weeks=i)
        
        # 첫 번째 주차인지 확인
        is_first_week = (i == 0)
        
        with st.expander(f"📦 {w_num}주차 설정", expanded=is_first_week):
            col_d, col_prod = st.columns([1, 3])
            
            # (A) 날짜 선택 (개별 수정 가능)
            with col_d:
                selected_date = st.date_input(
                    f"{w_num}주차 배송일", 
                    value=default_date, 
                    key=f"date_pick_{i}"
                )
                selected_date_str = selected_date.strftime("%Y-%m-%d")

            # (B) 상품 수량 입력
            with col_prod:
                c1, c2, c3, c4 = st.columns(4)
                
                # Case 1: 1주차 -> 입력받고 변수에 저장
                if is_first_week:
                    m = c1.number_input("무가당", min_value=0, key="w1_m")
                    g = c2.number_input("가당", min_value=0, key="w1_g")
                    b = c3.number_input("베리", min_value=0, key="w1_b")
                    k = c4.number_input("그릭", min_value=0, key="w1_k")
                    w1_moo, w1_ga, w1_berry, w1_greek = m, g, b, k
                
                # Case 2: 2주차 이상 + 체크박스 ON -> 1주차 값 강제 적용 (수정불가)
                elif copy_week1:
                    m = c1.number_input(f"무({w_num})", value=w1_moo, disabled=True, key=f"copy_m{i}")
                    g = c2.number_input(f"가({w_num})", value=w1_ga, disabled=True, key=f"copy_g{i}")
                    b = c3.number_input(f"베({w_num})", value=w1_berry, disabled=True, key=f"copy_b{i}")
                    k = c4.number_input(f"그({w_num})", value=w1_greek, disabled=True, key=f"copy_k{i}")
                
                # Case 3: 2주차 이상 + 체크박스 OFF -> 개별 입력
                else:
                    m = c1.number_input("무가당", min_value=0, value=0, key=f"manual_m{i}")
                    g = c2.number_input("가당", min_value=0, value=0, key=f"manual_g{i}")
                    b = c3.number_input("베리", min_value=0, value=0, key=f"manual_b{i}")
                    k = c4.number_input("그릭", min_value=0, value=0, key=f"manual_k{i}")

            # 데이터 리스트에 추가
            weeks_data.append({'date': selected_date_str, 'moo':m, 'ga':g, 'berry':b, 'greek':k})

    st.divider()

   # 4. 저장 버튼
    if st.button("🚀 주문 및 회원정보 저장", type="primary", use_container_width=True):
        if not phone or not name or not address:
            st.error("🚨 전화번호, 이름, 주소는 필수 입력 항목입니다!")
        else:
            # [핵심] 여기서 전화번호를 깨끗하게 정리합니다!
            clean_phone = normalize_phone(phone)
            
            # (만약 번호가 너무 짧거나 이상하면 경고 띄우기 기능 추가 가능)
            if len(clean_phone) < 10:
                 st.error(f"🚨 전화번호가 올바르지 않습니다: {phone}")
            else:
                with st.spinner("처리 중..."):
                    # 이제부터 모든 로직에는 'phone' 대신 'clean_phone'을 사용합니다.
                    
                    # (1) 회원 정보 저장 (정리된 번호로)
                    mem_res = update_member_info(clean_phone, name, region, address)
                    
                    if mem_res not in ["new", "updated"]:
                        st.error(f"🚨 회원 정보 저장 실패: {mem_res}\n(주문이 저장되지 않았습니다)")
                    else:
                        valid_orders = []
                        for order in weeks_data:
                            if (order['moo'] + order['ga'] + order['berry'] + order['greek']) > 0:
                                valid_orders.append(order)
                        
                        if not valid_orders:
                            st.warning("🤔 선택된 상품이 하나도 없습니다.")
                        else:
                            # (3) 주문 저장 (정리된 번호로)
                            ord_res = add_orders(clean_phone, valid_orders)
                            
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

# --------------------------------------------------------------------------------
# [탭 2] 사장님 전용 관리자 페이지
# --------------------------------------------------------------------------------
with tab2:
    st.header("🔒 관리자 통합 조회")
    pwd = st.text_input("비밀번호를 입력하세요", type="password")
    
    if pwd == ADMIN_PASSWORD:
        st.success("로그인 성공!")
        if st.button("🔄 데이터 새로고침"):
            st.rerun()
            
        df = get_joined_data()
        
        if not df.empty:
            st.subheader("📦 전체 주문 목록")
            st.markdown("회원 정보와 주문 내역이 합쳐진 표입니다.")
            st.dataframe(df, use_container_width=True)
            
            st.divider()
            st.info("💡 엑셀 시트는 '회원관리', '주문내역' 2개로 분리되어 저장되고 있습니다.")


