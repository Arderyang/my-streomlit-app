import streamlit as st
import sqlite3
from datetime import date, datetime, timedelta
import hashlib

DB_FILE = "smart_fridge.db"
CATEGORIES = ["肉類", "蔬菜", "水果", "乳製品", "蛋類", "海鮮", "飲料", "調味料", "冷凍食品", "其他"]
LOCATIONS = ["冷藏", "冷凍", "蔬果室", "其他"]

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# 1. 初始化資料庫（新增 fridges, users 資料表）
def init_db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = con.cursor()
    
    # 冰箱主表
    cur.execute("""CREATE TABLE IF NOT EXISTS fridges(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # 使用者權限表
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # 預設至少有一台主冰箱
    cur.execute("SELECT COUNT(*) FROM fridges")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO fridges(name) VALUES('主冰箱')")

    # 預設管理者與使用者帳號
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users(username, password, role) VALUES(?, ?, ?)", 
                    ("admin", hash_password("admin123"), "admin"))
        cur.execute("INSERT INTO users(username, password, role) VALUES(?, ?, ?)", 
                    ("user", hash_password("user123"), "user"))

    cur.execute("""CREATE TABLE IF NOT EXISTS foods(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fridge_id INTEGER DEFAULT 1,
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
        fridge_id INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        quantity REAL DEFAULT 1,
        unit TEXT,
        location TEXT,
        expiry_date TEXT,
        status INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # 檢查並補上可能缺少的欄位
    cur.execute("PRAGMA table_info(foods)")
    f_cols = [col[1] for col in cur.fetchall()]
    if "fridge_id" not in f_cols:
        cur.execute("ALTER TABLE foods ADD COLUMN fridge_id INTEGER DEFAULT 1")

    cur.execute("PRAGMA table_info(shopping_list)")
    s_cols = [col[1] for col in cur.fetchall()]
    if "fridge_id" not in s_cols:
        cur.execute("ALTER TABLE shopping_list ADD COLUMN fridge_id INTEGER DEFAULT 1")
    if "location" not in s_cols:
        cur.execute("ALTER TABLE shopping_list ADD COLUMN location TEXT")
    if "expiry_date" not in s_cols:
        cur.execute("ALTER TABLE shopping_list ADD COLUMN expiry_date TEXT")

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

# 初始化 Session State 登入狀態
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "role" not in st.session_state:
    st.session_state.role = ""

# --- 登入畫面檢查 ---
if not st.session_state.logged_in:
    st.title("🔒 智慧冰箱 V2 - 系統登入")
    st.info("請先登入以存取冰箱資料與執行操作。")
    
    with st.form("login_form"):
        input_user = st.text_input("帳號")
        input_pass = st.text_input("密碼", type="password")
        submit_login = st.form_submit_button("登入系統")
        
        if submit_login:
            con = get_db()
            cur = con.cursor()
            cur.execute("SELECT password, role FROM users WHERE username = ?", (input_user.strip(),))
            res = cur.fetchone()
            con.close()
            
            if res and res[0] == hash_password(input_pass):
                st.session_state.logged_in = True
                st.session_state.username = input_user.strip()
                st.session_state.role = res[1]
                st.success("登入成功！正在進入系統...")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤，請重新輸入！")
    
    # 預設帳號提示
    st.markdown("---")
    st.caption("💡 **預設測試帳號**：")
    st.caption("- 管理員：`admin` / 密碼：`admin123`")
    st.caption("- 一般使用者：`user` / 密碼：`user123`")
    st.stop()

# --- 已登入後的介面 ---
st.title("🧊 智慧冰箱 V2 (手機版)")

# 頂部顯示目前登入狀態與登出按鈕
col_top1, col_top2 = st.columns([3, 1])
with col_top1:
    role_display = "👑 管理者" if st.session_state.role == "admin" else "👤 一般使用者"
    st.markdown(f"歡迎回來，**{st.session_state.username}** ({role_display})")
with col_top2:
    if st.button("登出系統"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.rerun()

st.divider()

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

# --- 全局冰箱選擇列 ---
con_f = get_db()
fridges_list = con_f.execute("SELECT id, name FROM fridges ORDER BY id").fetchall()
con_f.close()

fridge_options = {name: fid for fid, name in fridges_list}
selected_fridge_name = st.selectbox("📍 選擇目前操作的冰箱", options=list(fridge_options.keys()))
current_fridge_id = fridge_options[selected_fridge_name]

# 管理冰箱的選單（僅限管理者 admin）
if st.session_state.role == "admin":
    with st.expander("⚙️ 管理冰箱清單 (僅限管理者)"):
        new_fridge_name = st.text_input("新冰箱名稱")
        if st.button("➕ 建立新冰箱"):
            if new_fridge_name.strip():
                try:
                    con = get_db()
                    con.execute("INSERT INTO fridges(name) VALUES(?)", (new_fridge_name.strip(),))
                    con.commit()
                    con.close()
                    st.success(f"成功新增冰箱：{new_fridge_name}")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("該冰箱名稱已存在！")
            else:
                st.warning("請輸入冰箱名稱！")
                
        if len(fridges_list) > 1:
            del_target = st.selectbox("選擇要刪除的冰箱", options=list(fridge_options.keys()), key="del_fridge_sel")
            if st.button("🗑️ 刪除此冰箱及其所有庫存", type="primary"):
                target_id = fridge_options[del_target]
                con = get_db()
                con.execute("DELETE FROM foods WHERE fridge_id = ?", (target_id,))
                con.execute("DELETE FROM shopping_list WHERE fridge_id = ?", (target_id,))
                con.execute("DELETE FROM fridges WHERE id = ?", (target_id,))
                con.commit()
                con.close()
                st.success(f"已刪除冰箱：{del_target}")
                st.rerun()
        else:
            st.info("系統中至少需保留一台冰箱，無法刪除。")

st.divider()

# 3. 手機版分頁介面
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📦 庫存", "📸 拍照AI", "🛒 採買", "📜 取出紀錄", "📊 報表"])

# --- 標籤一：食材庫存與完整 CRUD 管理 ---
with tab1:
    st.subheader(f"📦 [{selected_fridge_name}] 冰箱庫存與管理")
    
    with st.expander("➕ 手動新增食材到庫存"):
        with st.form("manual_add_form"):
            m_name = st.text_input("食材名稱*")
            m_cat = st.selectbox("分類", CATEGORIES)
            m_qty = st.number_input("數量", min_value=0.1, value=1.0, step=0.1)
            m_unit = st.text_input("單位", value="個")
            m_loc = st.selectbox("位置", LOCATIONS)
            m_expiry = st.date_input("有效期限", value=date.today() + timedelta(days=7))
            m_note = st.text_input("備註")
            m_submitted = st.form_submit_button("確認新增")
            
            if m_submitted:
                if not m_name.strip():
                    st.warning("請輸入食材名稱！")
                else:
                    con = get_db()
                    cur = con.cursor()
                    cur.execute("""INSERT INTO foods 
                        (fridge_id, name, category, quantity, unit, location, purchase_date, expiry_date, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (current_fridge_id, m_name, m_cat, m_qty, m_unit, m_loc, date.today().isoformat(), m_expiry.isoformat(), m_note))
                    fid = cur.lastrowid
                    cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                (fid, "入庫", m_qty, date.today().isoformat(), f"[{selected_fridge_name}] 手動新增入庫 ({st.session_state.username})"))
                    con.commit()
                    con.close()
                    st.success(f"成功新增 {m_name} 至 {selected_fridge_name}！")
                    st.rerun()

    with st.expander("⚡ 快速取用消耗食材"):
        con_quick = get_db()
        cur_q = con_quick.cursor()
        cur_q.execute("SELECT id, name, quantity, unit FROM foods WHERE fridge_id = ? AND quantity > 0 ORDER BY name", (current_fridge_id,))
        active_foods = cur_q.fetchall()
        con_quick.close()
        
        if not active_foods:
            st.info(f"[{selected_fridge_name}] 目前沒有庫存大於 0 的食材可供取用。")
        else:
            food_options = {f"{item[1]} (現有: {item[2]:g} {item[3] or ''})": item for item in active_foods}
            selected_label = st.selectbox("選擇要取用的食材", options=list(food_options.keys()))
            
            if selected_label:
                chosen_item = food_options[selected_label]
                fid_q, fname_q, fqty_q, funit_q = chosen_item
                
                with st.form("quick_consume_form"):
                    default_q = min(1.0, fqty_q)
                    q_consume_qty = st.number_input("取用數量", min_value=0.1, max_value=float(fqty_q), value=default_q, step=0.1)
                    q_submitted = st.form_submit_button("確認取出並扣減庫存")
                    
                    if q_submitted:
                        new_qty = fqty_q - q_consume_qty
                        con = get_db()
                        con.execute("UPDATE foods SET quantity = ? WHERE id = ?", (new_qty, fid_q))
                        con.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                    (fid_q, "取出/消耗", -q_consume_qty, date.today().isoformat(), f"[{selected_fridge_name}] 快速取用 ({st.session_state.username})"))
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
                       FROM foods WHERE fridge_id = ? AND (name LIKE ? OR category LIKE ? OR location LIKE ?) ORDER BY expiry_date""", 
                    (current_fridge_id, f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
    else:
        cur.execute("SELECT id, name, category, quantity, unit, location, expiry_date FROM foods WHERE fridge_id = ? ORDER BY expiry_date", (current_fridge_id,))
    rows = cur.fetchall()
    con.close()

    if not rows:
        st.info(f"[{selected_fridge_name}] 目前沒有找到任何食材記錄。")
    else:
        for row in rows:
            fid, name, cat, qty, unit, loc, expiry = row
            status = get_status(expiry, qty)
            
            with st.expander(f"{status} | {name} ({qty:g} {unit or ''})"):
                st.write(f"**分類**: {cat or '未分類'} | **位置**: {loc or '未指定'}")
                st.write(f"**有效期限**: {expiry or '未設定'}")
                
                with st.form(key=f"consume_form_{fid}"):
                    st.markdown("##### 🍽️ 單品取用/消耗")
                    max_c = float(qty) if qty > 0 else 0.1
                    default_c = min(1.0, max_c)
                    consume_qty = st.number_input("輸入取用數量", min_value=0.1, max_value=max_c, value=default_c, step=0.1, key=f"c_qty_{fid}")
                    c_submitted = st.form_submit_button("確認取出")
                    
                    if c_submitted:
                        if consume_qty > qty:
                            st.error(f"取用數量大於目前庫存 ({qty:g})！")
                        else:
                            new_qty = qty - consume_qty
                            con = get_db()
                            con.execute("UPDATE foods SET quantity = ? WHERE id = ?", (new_qty, fid))
                            con.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                        (fid, "取出/消耗", -consume_qty, date.today().isoformat(), f"[{selected_fridge_name}] 手動取用 ({st.session_state.username})"))
                            con.commit()
                            con.close()
                            st.success(f"成功取出 {name} 共 {consume_qty:g} {unit or ''}！")
                            st.rerun()

                with st.form(key=f"edit_form_{fid}"):
                    st.markdown("##### ✏️ 修改食材資料")
                    e_name = st.text_input("食材名稱", value=name, key=f"e_name_{fid}")
                    e_cat = st.selectbox("分類", CATEGORIES, index=CATEGORIES.index(cat) if cat in CATEGORIES else 0, key=f"e_cat_{fid}")
                    e_qty = st.number_input("數量", min_value=0.0, value=float(qty), step=0.1, key=f"e_qty_{fid}")
                    e_unit = st.text_input("單位", value=unit if unit else "", key=f"e_unit_{fid}")
                    e_loc = st.selectbox("位置", LOCATIONS, index=LOCATIONS.index(loc) if loc in LOCATIONS else 0, key=f"e_loc_{fid}")
                    
                    default_expiry = parse_date(expiry) if expiry else date.today()
                    if not default_expiry: default_expiry = date.today()
                    e_expiry = st.date_input("有效期限", value=default_expiry, key=f"e_exp_{fid}")
                    
                    e_submitted = st.form_submit_button("儲存修改")
                    if e_submitted:
                        con = get_db()
                        con.execute("""UPDATE foods SET name=?, category=?, quantity=?, unit=?, location=?, expiry_date=? WHERE id=?""",
                                    (e_name, e_cat, e_qty, e_unit, e_loc, e_expiry.isoformat(), fid))
                        con.commit()
                        con.close()
                        st.success(f"已成功更新 {e_name} 的資料！")
                        st.rerun()

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("加到採買", key=f"shop_{fid}"):
                        con = get_db()
                        con.execute("INSERT INTO shopping_list(fridge_id, name, quantity, unit, location, expiry_date) VALUES(?,?,?,?,?,?)", 
                                    (current_fridge_id, name, 1, unit, loc, expiry))
                        con.commit()
                        con.close()
                        st.success(f"已將 {name} 加入 {selected_fridge_name} 的採買清單")
                        st.rerun()
                with col_b:
                    # 刪除品項：權限檢查（僅限管理員或皆可？這裡設定為管理者或允許一般人刪除，視需求而定，此處保留讓管理者專用或皆可，示範中嚴格限制刪除需為 admin，或者只要登入即可）
                    if st.session_state.role == "admin":
                        if st.button("刪除品項", key=f"del_{fid}", type="primary"):
                            con = get_db()
                            con.execute("DELETE FROM foods WHERE id = ?", (fid,))
                            con.commit()
                            con.close()
                            st.success("已刪除品項，歷史紀錄已保留。")
                            st.rerun()
                    else:
                        st.caption("🔒 刪除品項需要管理者權限")

# --- 標籤二：手機拍照與 AI 辨識入庫 ---
with tab2:
    st.subheader(f"📸 拍照 AI 辨識入庫 ({selected_fridge_name})")
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
                    (fridge_id, name, category, quantity, unit, location, purchase_date, expiry_date, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (current_fridge_id, f_name, f_cat, f_qty, f_unit, f_loc, date.today().isoformat(), f_expiry.isoformat(), f"AI 拍照辨識入庫 ({st.session_state.username})"))
                fid = cur.lastrowid
                cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                            (fid, "入庫", f_qty, date.today().isoformat(), f"[{selected_fridge_name}] AI 拍照入庫"))
                con.commit()
                con.close()
                st.success(f"成功將 {f_name} 加入 {selected_fridge_name}！")
                st.rerun()

# --- 標籤三：採買清單 ---
with tab3:
    st.subheader(f"🛒 採買清單 ({selected_fridge_name})")
    with st.form("add_shop_form", clear_on_submit=True):
        s_name = st.text_input("想買什麼？*")
        s_qty = st.number_input("數量", min_value=0.1, value=1.0, step=0.1)
        s_unit = st.text_input("單位", value="個")
        s_loc = st.selectbox("預計存放位置", LOCATIONS)
        s_expiry = st.date_input("預計有效期限", value=date.today() + timedelta(days=7))
        s_submit = st.form_submit_button("新增至採買")
        
        if s_submit:
            if not s_name.strip():
                st.warning("請輸入想買的食材名稱！")
            else:
                con = get_db()
                con.execute("INSERT INTO shopping_list(fridge_id, name, quantity, unit, location, expiry_date) VALUES(?,?,?,?,?,?)", 
                            (current_fridge_id, s_name, s_qty, s_unit, s_loc, s_expiry.isoformat()))
                con.commit()
                con.close()
                st.rerun()

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT id, name, quantity, unit, location, expiry_date, status FROM shopping_list WHERE fridge_id = ? ORDER BY status, id DESC", (current_fridge_id,))
    shop_rows = cur.fetchall()
    con.close()

    if not shop_rows:
        st.info(f"[{selected_fridge_name}] 目前採買清單空空如也。")
    else:
        for sid, sname, sqty, sunit, sloc, sexp, sstatus in shop_rows:
            with st.expander(f"{'✅ [已買]' if sstatus else '🛒 [待買]'} {sname} ({sqty:g}{sunit or ''})"):
                st.write(f"**預計位置**: {sloc or '未指定'} | **預計到期**: {sexp or '未設定'}")
                
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    if not sstatus:
                        if st.button("📦 已買並加入庫存", key=f"bought_add_{sid}", type="primary"):
                            con = get_db()
                            cur = con.cursor()
                            cur.execute("""INSERT INTO foods 
                                (fridge_id, name, category, quantity, unit, location, purchase_date, expiry_date, note)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (current_fridge_id, sname, "其他", sqty, sunit, sloc or "冷藏", date.today().isoformat(), sexp or date.today().isoformat(), f"從採買清單入庫 ({st.session_state.username})"))
                            fid = cur.lastrowid
                            cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                        (fid, "入庫", sqty, date.today().isoformat(), f"[{selected_fridge_name}] 採買清單轉入"))
                            cur.execute("UPDATE shopping_list SET status=1 WHERE id=?", (sid,))
                            con.commit()
                            con.close()
                            st.success(f"成功將 {sname} 加入 {selected_fridge_name} 庫存！")
                            st.rerun()
                with col_s2:
                    if st.button("🗑️ 刪除項目", key=f"del_shop_{sid}"):
                        con = get_db()
                        con.execute("DELETE FROM shopping_list WHERE id=?", (sid,))
                        con.commit()
                        con.close()
                        st.rerun()

# --- 標籤四：取出/異動紀錄 ---
with tab4:
    st.subheader(f"📜 食材進出與取出紀錄 ({selected_fridge_name})")
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT t.id, COALESCE(f.name, '(已刪除食材)'), t.action, t.quantity, t.trans_date, t.note
        FROM transactions t
        JOIN foods f ON t.food_id = f.id
        WHERE f.fridge_id = ?
        ORDER BY t.id DESC
    """, (current_fridge_id,))
    trans_rows = cur.fetchall()
    con.close()

    if not trans_rows:
        st.info(f"[{selected_fridge_name}] 目前沒有任何異動紀錄。")
    else:
        for tid, fname, action, tqty, tdate, tnote in trans_rows:
            st.markdown(f"**[{tdate}] {fname}**")
            st.write(f"動作：`{action}` | 數量：`{tqty:g}` | 備註：{tnote}")
            st.divider()

# --- 標籤五：到期與統計報表 ---
with tab5:
    st.subheader(f"📊 冰箱狀態總覽 ({selected_fridge_name})")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM foods WHERE fridge_id = ?", (current_fridge_id,))
    count, total = cur.fetchone()
    cur.execute("SELECT name, quantity, unit, expiry_date FROM foods WHERE fridge_id = ? AND expiry_date<>'' AND expiry_date IS NOT NULL ORDER BY expiry_date", (current_fridge_id,))
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
        st.success(f"太棒了！[{selected_fridge_name}] 目前沒有 7 天內到期或已過期的食材。")
