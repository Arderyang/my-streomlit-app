import pandas as pd
import streamlit as st
import yfinance as yf

# 網頁頁面設定
st.set_page_config(
    page_title="上市櫃股票 EPS & 配息查詢", page_icon="📈", layout="centered"
)

st.title("📈 上市櫃股票 EPS & 歷史配息查詢系統")
st.write("輸入台股或美股代號，快速查詢歷年 EPS 及配息紀錄。")

# 1. 密碼/股號輸入框
stock_id = st.text_input(
    "請輸入股票代號（例如：2330、2454 或 AAPL）", value="2330"
).strip()


@st.cache_data(ttl=3600)  # 快取資料 1 小時，避免頻繁重複請求
def load_stock_data(symbol):
    # 自動處理 4 位數台股代碼
    if symbol.isdigit() and len(symbol) == 4:
        ticker_id = f"{symbol}.TW"
    else:
        ticker_id = symbol.upper()

    ticker = yf.Ticker(ticker_id)

    # 擷取 EPS
    eps_data = {}
    financials = ticker.financials
    if financials is not None and not financials.empty:
        basic_eps_rows = [
            row for row in financials.index if "Basic EPS" in row
        ]
        if basic_eps_rows:
            eps_series = financials.loc[basic_eps_rows[0]]
            for date, val in eps_series.items():
                year = str(pd.to_datetime(date).year)
                eps_data[year] = round(val, 2)

    # 擷取配息
    div_data = {}
    div_count = {}
    dividends = ticker.dividends
    if not dividends.empty:
        dividends.index = dividends.index.tz_localize(None)
        yearly_div = dividends.groupby(dividends.index.year).agg(
            ["sum", "count"]
        )
        for year, row in yearly_div.iterrows():
            div_data[str(year)] = round(row["sum"], 2)
            div_count[str(year)] = int(row["count"])

    # 合併年份
    all_years = sorted(
        list(set(eps_data.keys()) | set(div_data.keys())), reverse=True
    )

    if not all_years:
        return None, ticker_id

    # 組成表格 List
    table_data = []
    for year in all_years:
        table_data.append(
            {
                "年度": f"{year} 年",
                "EPS (元)": eps_data.get(year, "N/A"),
                "年度總配息 (元)": div_data.get(year, 0.0),
                "配息次數": div_count.get(year, 0),
            }
        )

    df = pd.DataFrame(table_data)
    return df, ticker_id


# 2. 查詢按鈕觸發
if st.button("查詢資料", type="primary"):
    if stock_id:
        with st.spinner("正在讀取資料，請稍後..."):
            df_result, ticker_id = load_stock_data(stock_id)

        if df_result is not None:
            st.success(f"已成功取得 【{ticker_id}】 的歷史數據！")

            # 顯示重點指標卡片 (最近一年)
            latest_year = df_result.iloc[0]
            col1, col2, col3 = st.columns(3)
            col1.metric("最新年度", latest_year["年度"])
            col2.metric("EPS", f"{latest_year['EPS (元)']} 元")
            col3.metric("總配息", f"{latest_year['年度總配息 (元)']} 元")

            # 顯示互動式表格
            st.subheader("📊 歷年 EPS 與配息彙總表")
            st.dataframe(df_result, use_container_width=True, hide_index=True)

            # 下載 CSV 功能
            csv = df_result.to_csv(index=False, encoding="utf-8-sig").encode(
                "utf-8-sig"
            )
            st.download_button(
                label="📥 下載 CSV 表格",
                data=csv,
                file_name=f"{ticker_id}_EPS_Dividends.csv",
                mime="text/csv",
            )
        else:
            st.error(f"❌ 查無 【{stock_id}】 的財務資料，請檢查代號是否正確。")
    else:
        st.warning("請先輸入股票代號！")