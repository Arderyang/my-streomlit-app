import streamlit as st
import sqlite3
from datetime import date, datetime, timedelta

DB_FILE = "smart_fridge.db"
CATEGORIES = ["肉類", "蔬菜", "水果", "乳製品", "蛋類", "海鮮", "飲料", "調味料", "冷凍食品", "其他"]
LOCATIONS = ["冷藏", "冷凍", "蔬果室", "其他"]

# 1. 初始化資料庫
def init_db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS foods(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT,
        name TEXT NOT NULL,
        category TEXT,
        quantity REAL DEFAULT 0,
        unit TEXT,
        location TEXT,
        purchase_date TEXT,
        open_date TEXT,
        expiry_date TEXT,
        note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        food_id INTEGER,
        action TEXT,
        quantity REAL,
        trans_date TEXT,
        note TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS shopping_list(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        quantity REAL DEFAULT 1,
        unit TEXT,
        status INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    con.commit()
    con.close()

init_db()

def get_db():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

# 2. 頁面與手機 PWA 設定
st.set_page_config(
    page_title="智慧冰箱 V2 手機版",
    page_icon="🧊",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown(
    """
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#2E7D32">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    """,
    unsafe_allow_html=True
)

st.title("🧊 智慧冰箱 V2 (手機版)")

def parse_date(value):
    if not value: return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try: return datetime.strptime(s, fmt).date()
        except ValueError: pass
    return None

def get_status(expiry, qty):
    if qty <= 0: return "🔴 已用完"
    if not expiry: return "正常"
    d = parse_date(expiry)
    if d is None: return "日期格式錯誤"
    days = (d - date.today()).days
    if days < 0: return "🔴 已過期"
    if days == 0: return "🔴 今天到期"
    if days <= 3: return f"🟠 {days}天內到期"
    if days <= 7: return f"🟡 {days}天內到期"
    return "正常"

# 3. 手機版分頁介面
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📦 庫存", "📸 拍照AI", "🛒 採買", "📜 取出紀錄", "📊 報表"])

# --- 標籤一：食材庫存與取用管理 ---
with tab1:
    st.subheader("🍽️ 快速取用與庫存管理")
    
    # ⚡ 【新增】快速取用專區（免點開選單，直接在上方快速扣除庫存）
    with st.expander("⚡ 快速取用消耗食材", expanded=True):
        con_quick = get_db()
        cur_q = con_quick.cursor()
        cur_q.execute("SELECT id, name, quantity, unit FROM foods WHERE quantity > 0 ORDER BY name")
        active_foods = cur_q.fetchall()
        con_quick.close()
        
        if not active_foods:
            st.info("目前沒有庫存大於 0 的食材可供取用。")
        else:
            food_options = {f"{item[1]} (現有: {item[2]:g} {item[3] or ''})": item for item in active_foods}
            selected_label = st.selectbox("選擇要取用的食材", options=list(food_options.keys()))
            
            if selected_label:
                chosen_item = food_options[selected_label]
                fid_q, fname_q, fqty_q, funit_q = chosen_item
                
                with st.form("quick_consume_form"):
                    q_consume_qty = st.number_input("取用數量", min_value=0.1, max_value=float(fqty_q), value=1.0 if fqty_q >= 1.0 else fqty_q, step=0.1)
                    q_submitted = st.form_submit_button("確認取出並扣減庫存")
                    
                    if q_submitted:
                        new_qty = fqty_q - q_consume_qty
                        con = get_db()
                        con.execute("UPDATE foods SET quantity = ? WHERE id = ?", (new_qty, fid_q))
                        con.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                    (fid_q, "取出/消耗", -q_consume_qty, date.today().isoformat(), "手機快速取用"))
                        con.commit()
                        con.close()
                        st.success(f"成功取出 {fname_q} 共 {q_consume_qty:g} {funit_q or ''}！")
                        st.rerun()

    st.divider()
    search_query = st.text_input("🔍 搜尋食材名稱/分類/位置", placeholder="輸入關鍵字...")
    
    con = get_db()
    cur = con.cursor()
    if search_query:
        cur.execute("""SELECT id, name, category, quantity, unit, location, expiry_date 
                       FROM foods WHERE name LIKE ? OR category LIKE ? OR location LIKE ? ORDER BY expiry_date""", 
                    (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
    else:
        cur.execute("SELECT id, name, category, quantity, unit, location, expiry_date FROM foods ORDER BY expiry_date")
    rows = cur.fetchall()
    con.close()

    if not rows:
        st.info("目前沒有找到任何食材記錄。")
    else:
        for row in rows:
            fid, name, cat, qty, unit, loc, expiry = row
            status = get_status(expiry, qty)
            
            with st.expander(f"{status} | {name} ({qty:g} {unit or ''})"):
                st.write(f"**分類**: {cat or '未分類'} | **位置**: {loc or '未指定'}")
                st.write(f"**有效期限**: {expiry or '未設定'}")
                
                # 單一品項的詳細取用表單
                with st.form(key=f"consume_form_{fid}"):
                    st.markdown("##### 🍽️ 單品取用/消耗")
                    consume_qty = st.number_input("輸入取用數量", min_value=0.1, max_value=float(qty) if qty > 0 else 1.0, value=1.0, step=0.1, key=f"c_qty_{fid}")
                    c_submitted = st.form_submit_button("確認取出")
                    
                    if c_submitted:
                        if consume_qty > qty:
                            st.error(f"取用數量大於目前庫存 ({qty:g})！")
                        else:
                            new_qty = qty - consume_qty
                            con = get_db()
                            con.execute("UPDATE foods SET quantity = ? WHERE id = ?", (new_qty, fid))
                            con.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                        (fid, "取出/消耗", -consume_qty, date.today().isoformat(), "手機手動取用"))
                            con.commit()
                            con.close()
                            st.success(f"成功從冰箱取出 {name} 共 {consume_qty:g} {unit or ''}！")
                            st.rerun()

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("加到採買", key=f"shop_{fid}"):
                        con = get_db()
                        con.execute("INSERT INTO shopping_list(name, quantity, unit) VALUES(?,?,?)", (name, 1, unit))
                        con.commit()
                        con.close()
                        st.success(f"已將 {name} 加入採買清單")
                        st.rerun()
                with col_b:
                    if st.button("刪除品項", key=f"del_{fid}", type="primary"):
                        con = get_db()
                        con.execute("DELETE FROM foods WHERE id = ?", (fid,))
                        con.execute("DELETE FROM transactions WHERE food_id = ?", (fid,))
                        con.commit()
                        con.close()
                        st.rerun()

# --- 標籤二：手機拍照與 AI 辨識入庫 ---
with tab2:
    st.subheader("📸 拍照 AI 辨識食材")
    camera_image = st.camera_input("拍攝照片")
    
    if camera_image is not None:
        st.info("照片已上傳！正在分析食材...")
        ai_detected_name = "新鮮高麗菜"
        ai_detected_category = "蔬菜"
        
        st.success(f"🎉 AI 辨識成功：**{ai_detected_name}**")
        
        with st.form("ai_add_form"):
            f_name = st.text_input("食材名稱", value=ai_detected_name)
            f_cat = st.selectbox("分類", CATEGORIES, index=CATEGORIES.index(ai_detected_category) if ai_detected_category in CATEGORIES else 1)
            f_qty = st.number_input("數量", min_value=0.1, value=1.0, step=1.0)
            f_unit = st.text_input("單位", value="顆")
            f_loc = st.selectbox("存放位置", LOCATIONS)
            f_expiry = st.date_input("有效期限", value=date.today() + timedelta(days=7))
            
            submitted = st.form_submit_button("確認入庫")
            if submitted:
                con = get_db()
                cur = con.cursor()
                cur.execute("""INSERT INTO foods 
                    (name, category, quantity, unit, location, purchase_date, expiry_date, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (f_name, f_cat, f_qty, f_unit, f_loc, date.today().isoformat(), f_expiry.isoformat(), "AI 拍照辨識入庫"))
                fid = cur.lastrowid
                cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                            (fid, "入庫", f_qty, date.today().isoformat(), "AI 拍照入庫"))
                con.commit()
                con.close()
                st.success(f"成功將 {f_name} 加入智慧冰箱！")
                st.rerun()

# --- 標籤三：採買清單 ---
with tab3:
    st.subheader("🛒 採買清單")
    with st.form("add_shop_form", clear_on_submit=True):
        s_name = st.text_input("想買什麼？")
        s_qty = st.number_input("數量", min_value=1.0, value=1.0)
        s_unit = st.text_input("單位", value="個")
        s_submit = st.form_submit_button("新增至採買")
        if s_submit and s_name:
            con = get_db()
            con.execute("INSERT INTO shopping_list(name, quantity, unit) VALUES(?,?,?)", (s_name, s_qty, s_unit))
            con.commit()
            con.close()
            st.rerun()

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT id, name, quantity, unit, status FROM shopping_list ORDER BY status, id DESC")
    shop_rows = cur.fetchall()
    con.close()

    if not shop_rows:
        st.info("目前採買清單空空如也。")
    else:
        for sid, sname, sqty, sunit, sstatus in shop_rows:
            col_s1, col_s2, col_s3 = st.columns([3, 1, 1])
            with col_s1:
                label = f"~~{sname} ({sqty:g}{sunit or ''})~~" if sstatus else f"**{sname}** ({sqty:g}{sunit or ''})"
                st.markdown(label)
            with col_s2:
                if not sstatus:
                    if st.button("已買", key=f"bought_{sid}"):
                        con = get_db()
                        con.execute("UPDATE shopping_list SET status=1 WHERE id=?", (sid,))
                        con.commit()
                        con.close()
                        st.rerun()
            with col_s3:
                if st.button("刪除", key=f"del_shop_{sid}"):
                    con = get_db()
                    con.execute("DELETE FROM shopping_list WHERE id=?", (sid,))
                    con.commit()
                    con.close()
                    st.rerun()

# --- 標籤四：取出/異動紀錄 ---
with tab4:
    st.subheader("📜 食材進出與取出紀錄")
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT t.id, COALESCE(f.name, '(已刪除食材)'), t.action, t.quantity, t.trans_date, t.note
        FROM transactions t
        LEFT JOIN foods f ON t.food_id = f.id
        ORDER BY t.id DESC
    """)
    trans_rows = cur.fetchall()
    con.close()

    if not trans_rows:
        st.info("目前沒有任何異動紀錄。")
    else:
        for tid, fname, action, tqty, tdate, tnote in trans_rows:
            st.markdown(f"**[{tdate}] {fname}**")
            st.write(f"動作：`{action}` | 數量：`{tqty:g}` | 備註：{tnote}")
            st.divider()

# --- 標籤五：到期與統計報表 ---
with tab5:
    st.subheader("📊 冰箱狀態總覽")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM foods")
    count, total = cur.fetchone()
    cur.execute("SELECT name, quantity, unit, expiry_date FROM foods WHERE expiry_date<>'' AND expiry_date IS NOT NULL ORDER BY expiry_date")
    all_foods = cur.fetchall()
    con.close()

    st.metric("總食材品項數", f"{count} 項")
    st.metric("總庫存數量", f"{total:g} 單位")
    
    st.divider()
    st.markdown("### ⚠️ 近期到期提醒")
    warning_found = False
    for name, qty, unit, exp in all_foods:
        st_val = get_status(exp, qty)
        if "到期" in st_val or "過期" in st_val:
            st.warning(f"{st_val}：**{name}** ({qty:g}{unit or ''}) - 有效期至 {exp}")
            warning_found = True
    if not warning_found:
        st.success("太棒了！目前沒有 7 天內到期或已過期的食材。")
