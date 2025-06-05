import streamlit as st
import requests
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup
import pandas as pd
import json
import re
import random
import time    

st.title("Kyobo Book 신청 시스템")

def get_book_info_advanced(kyobo_url, max_retries=3, debug=False):
    """개선된 도서 정보 추출 함수"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
    ]
    
    def get_realistic_headers():
        return {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.google.com/",
            "Cache-Control": "max-age=0"
        }
    
    session = requests.Session()
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(random.uniform(2, 5))
            
            headers = get_realistic_headers()
            
            # 쿠키 설정 (교보문고 특화)
            session.cookies.set('PCID', str(random.randint(1000000000, 9999999999)))
            
            response = session.get(kyobo_url, headers=headers, timeout=30, verify=False)
            
            if debug:
                st.write(f"[DEBUG] 시도 {attempt+1}: 상태코드={response.status_code}, 크기={len(response.text)}")
            
            if response.status_code == 200 and len(response.text) > 1000:
                soup = BeautifulSoup(response.text, "html.parser")
                
                # 강화된 추출 함수 사용
                book_info = extract_book_info(soup, debug=debug)
                
                if book_info and any(book_info.values()):
                    # 가격이 없으면 추가 시도
                    if not book_info.get("price"):
                        if debug:
                            st.warning("⚠️ 첫 시도에서 가격을 찾지 못함. 추가 방법 시도 중...")
                        
                        # 페이지 새로고침 후 재시도
                        time.sleep(1)
                        response = session.get(kyobo_url, headers=get_realistic_headers(), timeout=30, verify=False)
                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, "html.parser")
                            price_info = extract_price_advanced(soup, debug=debug)
                            if price_info["price"]:
                                book_info["price"] = price_info["price"]
                                book_info["extraction_method"] = price_info["extraction_method"]
                    
                    return book_info
                    
        except Exception as e:
            if debug:
                st.error(f"[DEBUG] 시도 {attempt+1} 실패: {e}")
            continue
    
    return None

def extract_book_info(soup, debug=False):
    """HTML에서 도서 정보 추출"""
    title = author = publisher = price = ""
    
    # 도서명 추출
    title_tag = soup.find("meta", property="og:title")
    if title_tag:
        title = title_tag.get("content", "").replace(" | 교보문고", "").strip()
    
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text().replace(" | 교보문고", "").strip()
    
    # JSON-LD에서 정보 추출
    json_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_scripts:
        try:
            data = json.loads(script.string)
            
            if not title and "name" in data:
                title = data["name"]
            
            if "author" in data and not author:
                if isinstance(data["author"], list):
                    author = ", ".join([a.get("name", "") for a in data["author"] if isinstance(a, dict)])
                elif isinstance(data["author"], dict):
                    author = data["author"].get("name", "")
            
            if "publisher" in data and not publisher:
                if isinstance(data["publisher"], dict):
                    publisher = data["publisher"].get("name", "")
                else:
                    publisher = str(data["publisher"])
            
            if not price:
                for field in ["price", "lowPrice", "highPrice"]:
                    if field in data:
                        price = str(data[field]).replace(",", "")
                        break
                        
        except:
            continue
    
    return {"title": title, "author": author, "publisher": publisher, "price": price}

# 로그인 후 사용자 정보 저장
if not hasattr(st, "user") or not getattr(st.user, "is_logged_in", False):
    if st.button("Contact with Google"):
        st.login('google')
    st.stop()

# 로그인 후 사용자 정보 저장
if "user" not in st.session_state:
    st.session_state["user"] = st.user.to_dict()
    

# 2. 오늘 날짜, 사용자명, 이메일 표시
seoul = pytz.timezone("Asia/Seoul")
now = datetime.now(seoul)
col1, col2, col3, col4 = st.columns(4)

col1.write(f"**신청시간:** {now.strftime('%Y-%m-%d %H:%M:%S')}")
col2.write(f"**신청자 성명:** {st.session_state['user']['name']}")
col3.write(f"**이메일:** {st.session_state['user']['email']}")
with col4:
    if st.button("🚪 로그아웃"):
        # 세션 상태 모든 키 삭제
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        # 로그아웃 처리
        st.logout()
        # 페이지 새로고침

# 3. Google Spreadsheet 연결
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
SPREADSHEET_ID = "1Jf3KoUk8pUGhY_kRnVK-yIpdQe8DQYjCc0eH4GmNC50"
SERVICE_ACCOUNT_INFO = dict(st.secrets["google_service_account"])
creds = Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, scopes=SCOPE
)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)
worksheet = sh.sheet1

# 4. 신청 내역 불러오기 함수
def get_applications():
    records = worksheet.get_all_records()
    if records:
        df = pd.DataFrame(records)
        # 신청시간 기준 내림차순 정렬 (최신순)
        if '신청시간' in df.columns:
            try:
                df['신청시간'] = pd.to_datetime(df['신청시간'])
                df = df.sort_values('신청시간', ascending=False)
            except Exception:
                # 날짜 변환 실패 시 문자열 기준 정렬
                df = df.sort_values('신청시간', ascending=False)
        return df
    else:
        # 요구사항에 맞는 컬럼 순서
        return pd.DataFrame(columns=["신청시간", "신청자 성명", "저자명", "출판사", "단가", "수량", "구매사이트", "가격"])

# 5. 탭 생성 (신규 신청, 수량 변경, 직접입력)
tab1, tab2, tab3 = st.tabs(["📚 신규 도서 신청", "🔄 수량 변경", "✍️ 직접입력"])

with tab1:
    st.subheader("새로운 도서 신청")
    status_container = st.container()
    
    kyobo_url = st.text_input("교보문고 URL을 입력하세요:")
    
    if kyobo_url:
        with status_container:
            st.info("🔍 도서 정보 추출 중...")
            progress_bar = st.progress(0)
            status_text = st.empty()
        
        try:
            kyobo_url = kyobo_url.lstrip('@').strip()
            
            # 도서 정보를 저장할 변수 초기화
            title = author = publisher = price = ""
            extraction_success = False
            
            # 1단계: 고급 스크래핑 시도
            progress_bar.progress(25)
            status_text.text("1단계: 고급 스크래핑 시도 중...")
            
            book_info = get_book_info_advanced(kyobo_url)
            
            if book_info and any(book_info.values()):
                title = book_info.get("title", "")
                author = book_info.get("author", "")
                publisher = book_info.get("publisher", "")
                price = book_info.get("price", "")
                
                progress_bar.progress(100)
                status_text.text("✅ 도서 정보 추출 완료!")
                extraction_success = True
                
            else:
                # 2단계: 기본 방법으로 재시도
                progress_bar.progress(50)
                status_text.text("2단계: 기본 방법으로 재시도 중...")
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
                    "Referer": "https://www.google.com/"
                }
                
                res = requests.get(kyobo_url, headers=headers, timeout=30)
                
                progress_bar.progress(75)
                status_text.text("3단계: 응답 분석 중...")
                
                if res.status_code == 200 and len(res.text) > 1000:
                    soup = BeautifulSoup(res.text, "html.parser")
                    
                    # 사이트 점검 확인
                    if "임시 점검" in res.text or "점검을 실시합니다" in res.text:
                        st.error("🚫 교보문고가 현재 점검 중입니다. 잠시 후 다시 시도해주세요.")
                    else:
                        # 기본 방법으로 정보 추출
                        extracted_info = extract_book_info(soup)
                        if extracted_info and any(extracted_info.values()):
                            title = extracted_info.get("title", "")
                            author = extracted_info.get("author", "")
                            publisher = extracted_info.get("publisher", "")
                            price = extracted_info.get("price", "")
                            
                            progress_bar.progress(100)
                            status_text.text("✅ 도서 정보 추출 완료! (기본 방법)")
                            extraction_success = True
                
                if not extraction_success:
                    progress_bar.progress(100)
                    status_text.text("❌ 도서 정보 추출 실패")
                    
                    # 디버깅 정보 표시
                    with st.expander("🔧 디버깅 정보"):
                        st.write(f"**상태 코드:** {res.status_code}")
                        st.write(f"**응답 크기:** {len(res.text):,} 문자")
                        st.write(f"**Content-Type:** {res.headers.get('content-type', 'N/A')}")
                        
                        preview = res.text[:500].replace('<', '&lt;').replace('>', '&gt;')
                        st.text_area("응답 미리보기:", preview, height=100)
            
            # 추출 성공 시 정보 표시 및 신청 처리
            if extraction_success and any([title, author, publisher, price]):
                # 수량 및 가격 계산
                qty = 1
                total_price = 0
                price_str = "정보 없음"
                
                if price and price.isdigit():
                    total_price = int(price) * qty
                    price_str = f"{int(price):,}원"
                
                # 추출된 정보 표시
                st.write("### 📖 추출된 도서 정보")
                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.write(f"**도서명:** {title or '정보 없음'}")
                    st.write(f"**저자명:** {author or '정보 없음'}")
                    st.write(f"**출판사:** {publisher or '정보 없음'}")
                with info_col2:
                    st.write(f"**단가:** {price_str}")
                    st.write(f"**수량:** {qty}권")
                    st.write(f"**총 가격:** {total_price:,}원" if total_price > 0 else "가격 정보 없음")
                
                # 신청 버튼
                can_submit = all([title, author, publisher, price])
                
                if can_submit:
                    if st.button("📝 도서 신청하기", type="primary"):
                        try:
                            worksheet.append_row([
                                now.strftime('%Y-%m-%d %H:%M:%S'),
                                st.session_state['user']['name'],
                                title,
                                author,
                                publisher,
                                price,
                                qty,
                                kyobo_url,
                                total_price
                            ])
                            st.success("✅ 도서 신청이 완료되었습니다!")
                            st.balloons()
                        except Exception as e:
                            st.error(f"❌ 신청 중 오류가 발생했습니다: {e}")
                else:
                    st.warning("⚠️ 필수 정보가 부족하여 신청할 수 없습니다.")
                    missing_info = []
                    if not title: missing_info.append("도서명")
                    if not author: missing_info.append("저자명")
                    if not publisher: missing_info.append("출판사")
                    if not price: missing_info.append("가격")
                    st.write(f"**부족한 정보:** {', '.join(missing_info)}")
            
            elif not extraction_success:
                st.error("❌ 도서 정보를 추출할 수 없습니다.")
                st.info("💡 다음 사항을 확인해주세요:")
                st.write("1. 올바른 교보문고 상품 페이지 URL인지 확인")
                st.write("2. 네트워크 연결 상태 확인")
                st.write("3. 잠시 후 다시 시도")
                
        except requests.exceptions.RequestException as e:
            progress_bar.progress(100)
            status_text.text("❌ 네트워크 오류")
            st.error(f"❌ 네트워크 연결 오류: {e}")
            st.info("💡 해결방법:")
            st.write("1. 인터넷 연결을 확인해주세요")
            st.write("2. VPN을 사용 중이라면 해제 후 시도해주세요")
            st.write("3. 잠시 후 다시 시도해주세요")
            
        except Exception as e:
            progress_bar.progress(100)
            status_text.text("❌ 예기치 않은 오류")
            st.error(f"❌ 도서 정보 추출 오류: {e}")
            
            # URL 검증
            if kyobo_url:
                url_issues = []
                if not kyobo_url.startswith("http"):
                    url_issues.append("⚠️ http:// 또는 https://가 없음")
                if "kyobobook.co.kr" not in kyobo_url:
                    url_issues.append("⚠️ 교보문고 도메인이 아님")
                if "/detail/" not in kyobo_url:
                    url_issues.append("⚠️ 상품 상세 페이지 URL이 아님")
                
                if url_issues:
                    st.write("**입력한 URL의 문제점:**")
                    for issue in url_issues:
                        st.write(issue)

with tab2:
    st.subheader("수량 변경")
    
    # 기존 신청 내역 불러오기
    applications_df = get_applications()
    
    if not applications_df.empty:
        st.write("### 📋 현재 신청 내역")
        st.dataframe(applications_df, use_container_width=True)
        
        # 사용자가 신청한 항목만 필터링
        user_applications = applications_df[applications_df['신청자 성명'] == st.session_state['user']['name']]
        
        if not user_applications.empty:
            st.write("### 🔄 내 신청 항목 수량 변경")
            
            # 수정할 항목 선택
            book_options = []
            for idx, row in user_applications.iterrows():
                # 컬럼 순서가 변경되었으므로 저자명을 먼저 표시
                book_info = f"{row['도서명']}(현재 수량: {row['수량']}권)"
                book_options.append((book_info, idx))
            
            if book_options:
                selected_book = st.selectbox(
                    "수량을 변경할 도서를 선택하세요:",
                    options=[option[0] for option in book_options],
                    help="변경하고 싶은 도서를 선택한 후 새로운 수량을 입력하세요."
                )
                
                # 선택된 항목의 실제 인덱스 찾기
                selected_idx = None
                for book_info, idx in book_options:
                    if book_info == selected_book:
                        selected_idx = idx
                        break
                
                if selected_idx is not None:
                    selected_row = user_applications.loc[selected_idx]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**저자명:** {selected_row['저자명']}")
                        st.write(f"**출판사:** {selected_row['출판사']}")
                        st.write(f"**현재 수량:** {selected_row['수량']}권")
                        st.write(f"**단가:** {selected_row['단가']:,}원" if isinstance(selected_row['단가'], (int, float)) else f"**단가:** {selected_row['단가']}")
                        st.write(f"**현재 총 가격:** {selected_row['가격']:,}원" if isinstance(selected_row['가격'], (int, float)) else f"**현재 총 가격:** {selected_row['가격']}")
                    
                    with col2:
                        new_qty = st.number_input(
                            "새로운 수량을 입력하세요:",
                            min_value=1,
                            max_value=100,
                            value=int(selected_row['수량']),
                            step=1
                        )
                        
                        # 새로운 총 가격 계산
                        unit_price = selected_row['단가']
                        if isinstance(unit_price, str) and unit_price.isdigit():
                            new_total_price = int(unit_price) * new_qty
                            st.write(f"**새로운 총 가격:** {new_total_price:,}원")
                        elif isinstance(unit_price, (int, float)):
                            new_total_price = int(unit_price) * new_qty
                            st.write(f"**새로운 총 가격:** {new_total_price:,}원")
                        else:
                            new_total_price = f"={unit_price} * {new_qty}"
                            st.write(f"**새로운 총 가격:** {new_total_price}")
                    
                    if st.button("🔄 수량 변경하기", type="primary"):
                        try:
                            # Google Sheets에서 해당 행 찾기 (행 번호는 1-based, 헤더 고려)
                            sheet_row_num = selected_idx + 2  # +2 는 헤더(1행)와 0-based 인덱스 보정
                            
                            # 새로운 컬럼 순서에 맞게 수정: [신청시간, 신청자 성명, 저자명, 출판사, 단가, 수량, 구매사이트, 가격]
                            worksheet.update_cell(sheet_row_num, 7, new_qty)        # 수량 컬럼 (7번째)
                            worksheet.update_cell(sheet_row_num, 9, new_total_price) # 가격 컬럼 (9번째)
                            
                            st.success(f"✅ 수량이 {selected_row['수량']}권에서 {new_qty}권으로 변경되었습니다!")
                            st.rerun()  # 페이지 새로고침으로 업데이트된 내용 반영
                            
                        except Exception as e:
                            st.error(f"❌ 수량 변경 중 오류가 발생했습니다: {e}")
            else:
                st.info("📝 선택할 수 있는 도서가 없습니다.")
        else:
            st.info("📚 아직 신청한 도서가 없습니다. '신규 도서 신청' 탭에서 도서를 신청해보세요!")
    else:
        st.info("📋 신청 내역이 없습니다. 첫 번째 도서를 신청해보세요!")

with tab3:
    st.subheader("직접 도서 정보 입력")
    # 자동입력 및 수정불가 필드
    st.write(f"**신청시간:** {now.strftime('%Y-%m-%d %H:%M:%S')}")
    st.write(f"**신청자 성명:** {st.session_state['user']['name']}")
    # 입력필드
    book_title = st.text_input("도서명")
    author = st.text_input("저자명")
    publisher = st.text_input("출판사")
    unit_price = st.text_input("단가", value="", placeholder="숫자만 입력")
    qty = st.number_input("수량", min_value=1, max_value=100, value=1, step=1)
    buy_url = st.text_input("구매사이트")
    # 가격 자동계산
    try:
        price_val = int(float(unit_price)) if unit_price else 0
    except Exception:
        price_val = 0
    total_price = price_val * qty
    st.write(f"**가격:** {total_price:,}원" if total_price else "**가격:** 0원")
    # 신청 버튼
    if st.button("📝 직접 도서 신청하기", key="direct_input"):
        if not all([book_title, author, publisher, unit_price, buy_url]):
            st.warning("모든 필드를 입력해 주세요.")
        elif not str(unit_price).isdigit():
            st.warning("단가는 숫자만 입력해 주세요.")
        else:
            try:
                worksheet.append_row([
                    now.strftime('%Y-%m-%d %H:%M:%S'),  # 신청시간
                    st.session_state['user']['name'],   # 신청자 성명
                    book_title,                         # 도서명
                    author,                             # 저자명
                    publisher,                          # 출판사
                    unit_price,                         # 단가
                    qty,                                # 수량
                    buy_url,                            # 구매사이트
                    total_price                         # 가격
                ])
                st.success("✅ 직접 입력 도서 신청이 완료되었습니다!")
                st.balloons()
            except Exception as e:
                st.error(f"❌ 직접 입력 신청 중 오류가 발생했습니다: {e}")

# 전체 신청 내역 표시 (페이지 하단)
st.write("---")
st.subheader("📊 전체 신청 내역")
applications_df = get_applications()
if not applications_df.empty:
    st.dataframe(applications_df, use_container_width=True)
else:
    st.info("아직 신청된 도서가 없습니다.")