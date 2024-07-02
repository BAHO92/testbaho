import streamlit as st
import pandas as pd
import requests
import lxml.html
from tqdm import tqdm
import urllib3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException

urllib3.disable_warnings()


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    return driver


def trimed(text):
    return text.replace("\t", "").replace("\r", "").replace("\n", "")


def find_element_with_multiple_selectors(driver, selectors, by_type=By.CSS_SELECTOR):
    for selector in selectors:
        try:
            element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((by_type, selector))
            )
            return element
        except TimeoutException:
            continue
    return None


def extract_article_url(href):
    href_value = href.get_attribute('href')
    if href_value:
        return f'https://sillok.history.go.kr{href_value}'
    return None


def crawl_sillok(query, page_type):
    driver = setup_driver()
    articles = []
    article_urls = []
    page = 1

    with st.spinner(f'{page_type} 검색 결과를 수집 중입니다...'):
        progress_bar = st.progress(0)
        while True:
            url = f'https://sillok.history.go.kr/search/searchResultList.do?topSearchWord={query}&pageIndex={page}'
            driver.get(url)

            st.text(f"현재 URL: {driver.current_url}")

            # 탭 선택
            tab_selectors = {
                "국역": [
                    "#cont_area > div.cont_in_left > div.tab.clear2.responsive.tab_result > ul > li:nth-child(1) > a",
                    "#cont_area > div.cont_in_left > div.tab.clear2.responsive.tab_result > ul > li:nth-child(1)",
                    "//*[@id='cont_area']/div[1]/div[2]/ul/li[1]/a",
                    "//*[@id='cont_area']/div[1]/div[2]/ul/li[1]"
                ],
                "원문": [
                    "#cont_area > div.cont_in_left > div.tab.clear2.responsive.tab_result > ul > li:nth-child(2) > a",
                    "#cont_area > div.cont_in_left > div.tab.clear2.responsive.tab_result > ul > li:nth-child(2)",
                    "//*[@id='cont_area']/div[1]/div[2]/ul/li[2]/a",
                    "//*[@id='cont_area']/div[1]/div[2]/ul/li[2]"
                ]
            }

            tab = find_element_with_multiple_selectors(driver, tab_selectors[page_type])
            if tab:
                st.text(f"선택된 탭: {tab.text}")
                tab.click()
            else:
                st.warning(f"페이지 {page}에서 {page_type} 탭을 찾을 수 없습니다. 페이지 소스를 확인합니다.")
                st.code(driver.page_source)
                break

            # 기사 목록 찾기
            article_list_selectors = [
                "#cont_area > div.cont_in_left > ul.search_result.mt_15",
                "//*[@id='cont_area']/div[1]/ul[2]",
                "/html/body/div[2]/div[2]/form/div/div[1]/ul[2]"
            ]
            article_list = find_element_with_multiple_selectors(driver, article_list_selectors)

            if article_list:
                hrefs = article_list.find_elements(By.TAG_NAME, 'a')
                st.text(f"페이지 {page}에서 찾은 링크 수: {len(hrefs)}")
            else:
                st.warning(f"페이지 {page}에서 기사 목록을 찾을 수 없습니다. 페이지 소스를 확인합니다.")
                st.code(driver.page_source)
                break

            if not hrefs:
                st.warning(f"페이지 {page}에서 링크를 찾을 수 없습니다. 크롤링을 종료합니다.")
                break

            for href in hrefs:
                try:
                    article_url = extract_article_url(href)
                    if article_url:
                        article_urls.append(article_url)
                    else:
                        st.warning(f"링크에서 URL을 추출할 수 없습니다: {href.get_attribute('outerHTML')}")
                except (NoSuchElementException, StaleElementReferenceException) as e:
                    st.warning(f"링크 처리 중 오류 발생: {str(e)}")
                    continue

            st.text(f"{len(article_urls)} 개의 결과를 찾았습니다.")
            if len(article_urls) == 0:
                st.warning("결과를 찾지 못했습니다. 크롤링을 종료합니다.")
                break

            page += 1
            progress_bar.progress(min(1.0, len(article_urls) / 1000))

    with st.spinner('기사 내용을 수집 중입니다...'):
        progress_bar = st.progress(0)
        for i, article_url in enumerate(article_urls):
            try:
                res = requests.get(article_url, verify=False)
                root = lxml.html.fromstring(res.text)
                articles.append((
                    ' '.join("권수 : " + trimed(span.text_content()).replace("기사", "기사 / 연차 : ") for span in
                             root.cssselect('.tit_loc')),
                    ' '.join(trimed(p.text_content()) for p in root.cssselect('.paragraph')),
                    article_url
                ))
            except Exception as e:
                st.warning(f"기사 URL {article_url}의 내용을 가져오는 데 실패했습니다. 오류: {str(e)}")
            progress_bar.progress((i + 1) / len(article_urls))

    driver.quit()
    return pd.DataFrame(articles, columns=['권수와 연차', '내용', 'URL'])


def main():
    st.title("조선왕조실록 크롤러")

    query = st.text_input("검색어를 입력하세요")
    page_type = st.radio("페이지 선택", ("국역", "원문"))

    if st.button("검색 및 크롤링"):
        if not query:
            st.warning("검색어를 입력해주세요.")
        else:
            df = crawl_sillok(query, page_type)
            st.success(f"총 {len(df)}개의 결과를 찾았습니다.")

            st.subheader("검색 결과")
            st.dataframe(df)

            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="CSV로 다운로드",
                data=csv,
                file_name=f"실록_검색어_{query}_{page_type}.csv",
                mime="text/csv",
            )

            html_string = f'''
            <html>
              <head><title>조선왕조실록</title></head>
              <body>
                {df.to_html(classes='mystyle').replace(query, f"<span style='font-size:medium; font-weight:bold; text-decoration: underline;'>{query}</span>")}
              </body>
            </html>
            '''
            st.download_button(
                label="HTML로 다운로드",
                data=html_string,
                file_name=f"실록_검색어_{query}_{page_type}.html",
                mime="text/html",
            )


if __name__ == "__main__":
    main()
