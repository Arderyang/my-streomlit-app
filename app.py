import streamlit as st

# 設定網頁標題與行動裝置全螢幕參數
st.set_page_config(
    page_title="我的手機版工具",
    page_icon="📱",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 注入 PWA 相關的 Meta 標籤（例如主題色、行動裝置全螢幕支援）
st.markdown(
    """
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#4A90E2">
    """,
    unsafe_allow_html=True
)

st.title("歡迎使用手機版工具")
# 您的其他 Streamlit 程式碼...
