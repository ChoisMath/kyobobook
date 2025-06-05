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

st.title("Kyobo Book 신청 시스템")

def get_book_info_advanced(kyobo_url, max_retries=3):
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
        }
    
    session = requests.Session()
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(random.uniform(2, 5))
            
            headers = get_realistic_headers()
            response = session.get(kyobo_url, headers=headers, timeout=30, verify=False)
            
            if response.status_code == 200 and len(response.text) > 1000:
                soup = BeautifulSoup(response.text, "html.parser")
                book_info = extract_book_info(soup)
                
                if book_info and any(book_info.values()):
                    return book_info
                    
        except Exception as e:
            continue
    
    return None

def extract_book_info(soup):
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
    
    # Kyobo URL 입력
    kyobo_url = st.text_input("교보문고 URL을 입력하세요: https://product.kyobobook.co.kr/detail/(상품번호:S00000xxxxxxx)")
    
    if kyobo_url:
        # 디버깅을 위한 상세 정보 표시 (일반 사용자용 주석처리)
        # debug_container = st.expander("🔧 디버깅 정보 (문제 해결용)", expanded=False)
        
        try:
            kyobo_url = kyobo_url.lstrip('@').strip()
            
            # 다양한 User-Agent 시도
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
            ]
            
            # 헤더 설정
            headers = {
                "User-Agent": user_agents[0],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            # 디버깅 정보 수집 (화면 표시 주석처리, 데이터는 유지)
            # with debug_container:
            #     st.write("**요청 정보:**")
            #     st.write(f"- URL: {kyobo_url}")
            #     st.write(f"- User-Agent: {headers['User-Agent'][:50]}...")
            
            # 웹페이지 요청
            res = requests.get(kyobo_url, headers=headers, timeout=10)
            
            # 응답 정보 수집 (화면 표시 주석처리, 데이터는 유지)
            # with debug_container:
            #     st.write(f"**응답 정보:**")
            #     st.write(f"- 상태 코드: {res.status_code}")
            #     st.write(f"- Content-Type: {res.headers.get('content-type', 'N/A')}")
            #     st.write(f"- 응답 길이: {len(res.text):,} 문자")
            #     
            #     # 응답 내용 미리보기
            #     preview = res.text[:500].replace('<', '&lt;').replace('>', '&gt;')
            #     st.text_area("응답 HTML 미리보기 (처음 500자):", preview, height=100)
            
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 사이트 점검 여부 확인
            site_under_maintenance = False
            if "임시 점검" in res.text or "점검을 실시합니다" in res.text:
                site_under_maintenance = True
                st.error("🚫 교보문고가 현재 점검 중입니다. 잠시 후 다시 시도해주세요.")
                # 디버깅 정보 수집 (화면 표시 주석처리)
                # with debug_container:
                #     st.write("**문제:** 사이트 점검 중")

            # 사이트 점검 중이 아닐 때만 파싱 진행
            if not site_under_maintenance:
                # 1. 도서명 추출 (여러 방법 시도)
                title = ""
                title_sources = []
                
                # 방법 1: og:title
                title_tag = soup.find("meta", property="og:title")
                if title_tag and "content" in title_tag.attrs:
                    title = title_tag["content"].replace(" | 교보문고", "").strip()
                    # re.split로 '|' 앞부분만 추출
                    title = re.split(r'\s*\|\s*', title)[0].strip()
                    title_sources.append("og:title")
                
                # 방법 2: title 태그
                if not title:
                    title_tag = soup.find("title")
                    if title_tag:
                        title = title_tag.get_text().replace(" | 교보문고", "").strip()
                        title = re.split(r'\s*\|\s*', title)[0].strip()
                        title_sources.append("title")
                
                # 방법 3: h1 태그 (상품명)
                if not title:
                    h1_tag = soup.find("h1")
                    if h1_tag:
                        title = h1_tag.get_text(strip=True)
                        title = re.split(r'\s*\|\s*', title)[0].strip()
                        title_sources.append("h1")

                # 2. JSON-LD에서 정보 추출
                author = publisher = price = ""
                json_sources = []
                
                json_ld_scripts = soup.find_all("script", type="application/ld+json")
                # 디버깅 정보 수집 (화면 표시 주석처리)
                # with debug_container:
                #     st.write(f"**발견된 JSON-LD 스크립트:** {len(json_ld_scripts)}개")
                
                for script in json_ld_scripts:
                    try:
                        data = json.loads(script.string)
                        # 디버깅 정보 수집 (화면 표시 주석처리)
                        # with debug_container:
                        #     st.json(data)
                        
                        # 도서명
                        if not title and "name" in data:
                            title = data["name"]
                            title_sources.append("JSON-LD")
                        
                        # 저자
                        if "author" in data and not author:
                            if isinstance(data["author"], list):
                                author = ", ".join([a.get("name", "") for a in data["author"]])
                            elif isinstance(data["author"], dict):
                                author = data["author"].get("name", "")
                            else:
                                author = str(data["author"])
                            json_sources.append("저자")
                        
                        # 출판사
                        if "publisher" in data and not publisher:
                            if isinstance(data["publisher"], dict):
                                publisher = data["publisher"].get("name", "")
                            else:
                                publisher = str(data["publisher"])
                            json_sources.append("출판사")
                        
                        # 가격
                        if not price:
                            # 다양한 가격 필드 시도
                            price_fields = ["price", "lowPrice", "highPrice"]
                            for field in price_fields:
                                if field in data:
                                    price = str(data[field]).replace(",", "")
                                    json_sources.append(f"가격({field})")
                                    break
                            
                            # workExample 구조에서 가격 추출
                            if not price and "workExample" in data:
                                work_examples = data["workExample"]
                                if isinstance(work_examples, list) and len(work_examples) > 0:
                                    work = work_examples[0]
                                    try:
                                        price = str(int(float(
                                            work["potentialAction"]["expectsAcceptanceOf"]["Price"]
                                        )))
                                        json_sources.append("가격(workExample)")
                                    except Exception:
                                        pass
                            
                    except Exception as e:
                        # 디버깅 정보 수집 (화면 표시 주석처리)
                        # with debug_container:
                        #     st.write(f"JSON-LD 파싱 오류: {e}")
                        pass

                # 3. CSS 선택자로 대체 추출 방법들 시도
                css_sources = []
                
                # 다양한 CSS 클래스/선택자 패턴 시도
                if not author:
                    author_selectors = [
                        ".author", ".writer", ".prod_author", ".book-author",
                        "[data-author]", ".author-name", ".creator"
                    ]
                    for selector in author_selectors:
                        element = soup.select_one(selector)
                        if element:
                            author = element.get_text(strip=True)
                            css_sources.append(f"저자({selector})")
                            break
                
                if not publisher:
                    publisher_selectors = [
                        ".company", ".publisher", ".prod_company", ".book-publisher",
                        "[data-publisher]", ".publisher-name"
                    ]
                    for selector in publisher_selectors:
                        element = soup.select_one(selector)
                        if element:
                            publisher = element.get_text(strip=True)
                            css_sources.append(f"출판사({selector})")
                            break
                
                if not price:
                    price_selectors = [
                        ".val", ".price", ".prod_price", ".book-price",
                        "[data-price]", ".price-value", ".current-price"
                    ]
                    for selector in price_selectors:
                        element = soup.select_one(selector)
                        if element:
                            price_text = element.get_text(strip=True).replace(",", "").replace("원", "")
                            # 숫자만 추출
                            price_match = re.search(r'\d+', price_text)
                            if price_match:
                                price = price_match.group()
                                css_sources.append(f"가격({selector})")
                                break


                # 수량은 초기값 1로 고정
                qty = 1
                total_price = int(price) * qty if price.isdigit() else 0

                # 가격 표시용 포맷팅
                if price:
                    try:
                        price_int = int(float(price))
                        price_str = f"{price_int:,}원"
                    except Exception:
                        price_str = price
                else:
                    price_str = "정보 없음"

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
                    st.write(f"**총 가격:** {total_price:,}원" if isinstance(total_price, int) and total_price > 0 else "가격 정보 없음")

                # 신청 버튼 (필수 정보가 있을 때만 활성화)
                can_submit = all([title, author, publisher, price])
                
                if can_submit:
                    if st.button("📝 도서 신청하기", type="primary"):
                        try:
                            # 요구사항에 맞는 올바른 순서로 데이터 입력
                            worksheet.append_row([
                                now.strftime('%Y-%m-%d %H:%M:%S'),  # 신청시간
                                st.session_state['user']['name'],   # 신청자 성명
                                title,                              # 도서명
                                author,                             # 저자명
                                publisher,                          # 출판사
                                price,                              # 단가
                                qty,                                # 수량
                                kyobo_url,                          # 구매사이트
                                total_price                         # 가격
                            ])
                            st.success("✅ 도서 신청이 완료되었습니다!")
                            st.balloons()
                        except Exception as e:
                            st.error(f"❌ 신청 중 오류가 발생했습니다: {e}")
                else:
                    st.warning("⚠️ 필수 정보가 부족하여 신청할 수 없습니다. 위의 디버깅 정보를 확인해주세요.")
                    missing_info = []
                    if not title: missing_info.append("도서명")
                    if not author: missing_info.append("저자명")
                    if not publisher: missing_info.append("출판사")
                    if not price: missing_info.append("가격")
                    st.write(f"**부족한 정보:** {', '.join(missing_info)}")
                    
        except requests.exceptions.RequestException as e:
            st.error(f"❌ 네트워크 연결 오류: {e}")
            st.info("💡 해결방법:")
            st.write("1. 인터넷 연결을 확인해주세요")
            st.write("2. VPN을 사용 중이라면 해제 후 시도해주세요")
            st.write("3. 잠시 후 다시 시도해주세요")
            
        except Exception as e:
            st.error(f"❌ 도서 정보 추출 오류: {e}")
            st.info("💡 문제 해결 가이드:")
            
            col1, col2 = st.columns(2)
            with col1:
                st.write("**URL 확인사항:**")
                st.write("- 올바른 교보문고 URL인가요?")
                st.write("- URL이 완전한가요? (https:// 포함)")
                st.write("- 책이 실제로 존재하나요?")
            
            with col2:
                st.write("**예시 올바른 URL:**")
                st.code("https://product.kyobobook.co.kr/detail/S000001916416")
                st.write("**URL 형태:** product.kyobobook.co.kr/detail/S숫자")
            
            # 사용자가 입력한 URL 검증
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