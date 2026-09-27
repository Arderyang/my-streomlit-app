import streamlit as st
import sqlite3
from datetime import date, datetime, timedelta
import hashlib
from google import genai
from PIL import Image

DB_FILE = "smart_fridge.db"
CATEGORIES = ["肉類", "蔬菜", "水果", "乳製品", "蛋類", "海鮮", "飲料", "調味料", "冷凍食品", "其他"]
LOCATIONS = ["冷藏", "冷凍", "蔬果室", "其他"]

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# 1. 初始化資料庫
def init_db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = con.cursor()
    
    cur.execute("""CREATE TABLE IF NOT EXISTS fridges(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS recipes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        category TEXT,
        ingredients TEXT, 
        instructions TEXT, 
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    
    cur.execute("SELECT COUNT(*) FROM fridges")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO fridges(name) VALUES('主冰箱')")

    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users(username, password, role) VALUES(?, ?, ?)", 
                    ("admin", hash_password("admin123"), "admin"))
        cur.execute("INSERT INTO users(username, password, role) VALUES(?, ?, ?)", 
                    ("user", hash_password("user123"), "user"))

    cur.execute("SELECT COUNT(*) FROM recipes")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO recipes(name, category, ingredients, instructions) VALUES(?, ?, ?, ?)",
                    ("高麗菜炒豬肉", "家常菜", "高麗菜:0.5, 豬肉片:200, 蒜頭:2", "1. 熱鍋下油爆香蒜頭。\n2. 加入豬肉片炒至半熟。\n3. 放入高麗菜拌炒至熟軟即完成。"))
        cur.execute("INSERT INTO recipes(name, category, ingredients, instructions) VALUES(?, ?, ?, ?)",
                    ("番茄炒蛋", "家常菜", "番茄:2, 雞蛋:3, 蔥:1", "1. 雞蛋先打散炒熟備用。\n2. 番茄切塊下鍋炒出汁。\n3. 加入炒好的雞蛋拌勻調味。"))

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
    
    st.markdown("---")
    st.caption("💡 **預設測試帳號**：")
    st.caption("- 管理員：`admin` / 密碼：`admin123`")
    st.caption("- 一般使用者：`user` / 密碼：`user123`")
    st.stop()

# --- 已登入後的介面 ---
st.title("🧊 智慧冰箱 V2 (手機版)")

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

with st.expander("🔑 修改個人密碼"):
    with st.form("change_password_form"):
        old_pass = st.text_input("輸入舊密碼", type="password")
        new_pass1 = st.text_input("輸入新密碼", type="password")
        new_pass2 = st.text_input("再次確認新密碼", type="password")
        submit_pw = st.form_submit_button("確認修改密碼")
        
        if submit_pw:
            if not old_pass or not new_pass1 or not new_pass2:
                st.warning("所有欄位皆必須填寫！")
            elif new_pass1 != new_pass2:
                st.error("兩次輸入的新密碼不相符！")
            else:
                con = get_db()
                cur = con.cursor()
                cur.execute("SELECT password FROM users WHERE username = ?", (st.session_state.username,))
                db_pass = cur.fetchone()[0]
                
                if db_pass != hash_password(old_pass):
                    st.error("舊密碼輸入錯誤！")
                else:
                    cur.execute("UPDATE users SET password = ? WHERE username = ?", 
                                (hash_password(new_pass1), st.session_state.username))
                    con.commit()
                    con.close()
                    st.success("密碼修改成功！下次登入請使用新密碼。")

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

con_f = get_db()
fridges_list = con_f.execute("SELECT id, name FROM fridges ORDER BY id").fetchall()
con_f.close()

fridge_options = {name: fid for fid, name in fridges_list}
selected_fridge_name = st.selectbox("📍 選擇目前操作的冰箱", options=list(fridge_options.keys()))
current_fridge_id = fridge_options[selected_fridge_name]

if st.session_state.role == "admin":
    with st.expander("⚙️ 系統帳號與權限管理 (僅限管理者)"):
        st.markdown("#### ➕ 新增系統成員")
        with st.form("add_user_form"):
            new_u_name = st.text_input("新使用者帳號")
            new_u_pass = st.text_input("新使用者密碼", type="password")
            new_u_role = st.selectbox("權限角色", options=["user", "admin"], format_func=lambda x: "一般使用者 (user)" if x=="user" else "管理者 (admin)")
            submit_new_user = st.form_submit_button("建立新帳號")
            
            if submit_new_user:
                if not new_u_name.strip() or not new_u_pass.strip():
                    st.warning("帳號與密碼皆不可為空白！")
                else:
                    try:
                        con = get_db()
                        con.execute("INSERT INTO users(username, password, role) VALUES(?, ?, ?)",
                                    (new_u_name.strip(), hash_password(new_u_pass.strip()), new_u_role))
                        con.commit()
                        con.close()
                        st.success(f"成功新增成員：{new_u_name.strip()}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("該帳號名稱已存在！")
        
        st.markdown("#### 👥 現有成員列表")
        con_u = get_db()
        all_users = con_u.execute("SELECT id, username, role, created_at FROM users ORDER BY id").fetchall()
        con_u.close()
        for uid, uname, urole, udate in all_users:
            r_str = "👑 管理者" if urole == "admin" else "👤 一般使用者"
            st.text(f"ID: {uid} | 帳號: {uname} | 權限: {r_str}")

        st.divider()
        st.markdown("#### 🧊 冰箱清單管理")
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

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📦 庫存", "📸 拍照AI", "🛒 採買", "🍳 食譜", "📜 取出紀錄", "📊 報表"])

# --- 標籤一：庫存 ---
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
                        (current_fridge_id, m_name.strip(), m_cat, m_qty, m_unit, m_loc, date.today().isoformat(), m_expiry.isoformat(), m_note))
                    fid = cur.lastrowid
                    cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                (fid, "入庫", m_qty, date.today().isoformat(), f"[{selected_fridge_name}] 手動新增入庫"))
                    con.commit()
                    con.close()
                    st.success(f"成功新增 {m_name.strip()}！")
                    st.rerun()

    search_query = st.text_input("🔍 搜尋食材名稱/分類/位置", placeholder="輸入關鍵字...")
    con = get_db()
    cur = con.cursor()
    # 僅查詢數量大於 0 的食材，數量為 0 時自動不顯示在頁面上
    if search_query:
        cur.execute("""SELECT id, name, category, quantity, unit, location, expiry_date 
                       FROM foods WHERE fridge_id = ? AND quantity > 0 AND (name LIKE ? OR category LIKE ? OR location LIKE ?) ORDER BY expiry_date""", 
                    (current_fridge_id, f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
    else:
        cur.execute("SELECT id, name, category, quantity, unit, location, expiry_date FROM foods WHERE fridge_id = ? AND quantity > 0 ORDER BY expiry_date", (current_fridge_id,))
    rows = cur.fetchall()
    con.close()

    if not rows:
        st.info(f"[{selected_fridge_name}] 目前沒有找到任何庫存食材記錄。")
    else:
        for row in rows:
            fid, name, cat, qty, unit, loc, expiry = row
            status = get_status(expiry, qty)
            with st.expander(f"{status} | {name} ({qty:g} {unit or ''})"):
                st.write(f"**分類**: {cat or '未分類'} | **位置**: {loc or '未指定'}")
                st.write(f"**有效期限**: {expiry or '未設定'}")
                
                if qty > 0:
                    with st.form(key=f"consume_form_{fid}"):
                        consume_qty = st.number_input("輸入取用數量", min_value=0.1, max_value=float(qty), value=min(1.0, float(qty)), step=0.1)
                        if st.form_submit_button("確認取出"):
                            if consume_qty > qty:
                                st.error("取用數量大於目前庫存！")
                            else:
                                con = get_db()
                                con.execute("UPDATE foods SET quantity = ? WHERE id = ?", (qty - consume_qty, fid))
                                con.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                            (fid, "取出/消耗", -consume_qty, date.today().isoformat(), "手動取用"))
                                con.commit()
                                con.close()
                                st.success("取出成功！")
                                st.rerun()

# --- 標籤二：手機拍照與 Google Gemini AI 辨識入庫 ---
with tab2:
    st.subheader(f"📸 Google AI 智慧拍照辨識入庫 ({selected_fridge_name})")
    
    for key, val in [("ai_name", "雞蛋"), ("ai_cat", "蛋類"), ("ai_qty", 1.0), ("ai_unit", "顆")]:
        if key not in st.session_state:
            st.session_state[key] = val

    camera_image = st.camera_input("拍攝冰箱內部或單一食材 (例如：1顆雞蛋)")
    
    if camera_image is not None:
        image = Image.open(camera_image)
        st.image(image, caption="已拍攝的照片", use_container_width=True)
        
        if st.button("🤖 開始讓 Gemini 分析食材"):
            with st.spinner("AI 正在分析影像中的食材與數量，請稍候..."):
                try:
                    active_key = ""
                    try:
                        if "GEMINI_API_KEY" in st.secrets:
                            active_key = st.secrets["GEMINI_API_KEY"]
                    except Exception:
                        pass
                    
                    client = genai.Client(api_key=active_key if active_key else None)
                    
                    prompt = (
                        "請仔細分析這張照片中的主要食材及其數量。請嚴格依照下列格式回答，不要有其他廢話：\n"
                        "名稱: [食材名稱，例如 雞蛋]\n"
                        "分類: [肉類/蔬菜/水果/乳製品/蛋類/海鮮/飲料/調味料/冷凍食品/其他]\n"
                        "數量: [數字，例如 1]\n"
                        "單位: [單位，例如 顆/個/盒]"
                    )
                    
                    # 嘗試呼叫模型，若遇到 503 暫時忙碌可自動切換備用模型
                    response = None
                    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash"]
                    
                    for m in models_to_try:
                        try:
                            response = client.models.generate_content(
                                model=m, 
                                contents=[image, prompt]
                            )
                            if response and response.text:
                                break
                        except Exception:
                            continue
                            
                    if response and response.text:
                        ai_text = response.text.strip()
                        st.success("🎉 AI 分析成功！")
                        
                        for line in ai_text.split("\n"):
                            if "名稱" in line:
                                st.session_state.ai_name = line.split(":")[-1].split("：")[-1].strip().replace("]", "").replace("[", "")
                            elif "分類" in line:
                                cat_val = line.split(":")[-1].split("：")[-1].strip().replace("]", "").replace("[", "")
                                if cat_val in CATEGORIES:
                                    st.session_state.ai_cat = cat_val
                            elif "數量" in line:
                                try:
                                    q_str = line.split(":")[-1].split("：")[-1].strip()
                                    import re
                                    numbers = re.findall(r"\d+\.?\d*", q_str)
                                    if numbers:
                                        st.session_state.ai_qty = float(numbers[0])
                                except Exception:
                                    pass
                            elif "單位" in line:
                                st.session_state.ai_unit = line.split(":")[-1].split("：")[-1].strip().replace("]", "").replace("[", "")
                    else:
                        st.error("目前 AI 伺服器繁忙，請稍候幾秒鐘後再點擊一次按鈕。")

                except Exception as e:
                    st.error(f"AI 辨識發生錯誤：{e}")

    # 確認辨識與入庫資訊表單
    st.markdown("##### 📝 確認辨識與入庫資訊")
    f_name = st.text_input("食材名稱", value=st.session_state.ai_name, key="input_ai_name")
    f_cat = st.selectbox("分類", CATEGORIES, index=CATEGORIES.index(st.session_state.ai_cat) if st.session_state.ai_cat in CATEGORIES else 4, key="input_ai_cat")
    f_qty = st.number_input("數量", min_value=0.1, value=float(st.session_state.ai_qty), step=1.0, key="input_ai_qty")
    f_unit = st.text_input("單位", value=st.session_state.ai_unit, key="input_ai_unit")
    f_loc = st.selectbox("存放位置", LOCATIONS, key="input_ai_loc")
    f_expiry = st.date_input("有效期限", value=date.today() + timedelta(days=14), key="input_ai_expiry")
    
    if st.button("確認入庫", type="primary"):
        if not f_name.strip():
            st.warning("請輸入食材名稱！")
        else:
            con = get_db()
            cur = con.cursor()
            cur.execute("""INSERT INTO foods 
                (fridge_id, name, category, quantity, unit, location, purchase_date, expiry_date, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (current_fridge_id, f_name.strip(), f_cat, f_qty, f_unit, f_loc, date.today().isoformat(), f_expiry.isoformat(), "AI 拍照辨識入庫"))
            fid = cur.lastrowid
            cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                        (fid, "入庫", f_qty, date.today().isoformat(), "AI 拍照入庫"))
            con.commit()
            con.close()
            
            st.success(f"✅ 成功將 {f_qty:g} {f_unit} 的 {f_name.strip()} 加入冰箱！")
            st.session_state.ai_name = "雞蛋"
            st.session_state.ai_qty = 1.0
            
# --- 標籤三：採買 ---
with tab3:
    st.subheader(f"🛒 採買清單 ({selected_fridge_name})")
    with st.form("add_shop_form", clear_on_submit=True):
        s_name = st.text_input("想買什麼？*")
        s_qty = st.number_input("數量", min_value=0.1, value=1.0, step=0.1)
        s_unit = st.text_input("單位", value="個")
        s_loc = st.selectbox("預計存放位置", LOCATIONS)
        s_expiry = st.date_input("預計有效期限", value=date.today() + timedelta(days=7))
        if st.form_submit_button("新增至採買"):
            if s_name.strip():
                con = get_db()
                con.execute("INSERT INTO shopping_list(fridge_id, name, quantity, unit, location, expiry_date) VALUES(?,?,?,?,?,?)", 
                            (current_fridge_id, s_name.strip(), s_qty, s_unit, s_loc, s_expiry.isoformat()))
                con.commit()
                con.close()
                st.rerun()

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT id, name, quantity, unit, location, expiry_date, status FROM shopping_list WHERE fridge_id = ? ORDER BY status, id DESC", (current_fridge_id,))
    shop_rows = cur.fetchall()
    con.close()
    if shop_rows:
        for sid, sname, sqty, sunit, sloc, sexp, sstatus in shop_rows:
            with st.expander(f"{'✅ [已買]' if sstatus else '🛒 [待買]'} {sname} ({sqty:g}{sunit or ''})"):
                col1, col2 = st.columns(2)
                with col1:
                    if not sstatus and st.button("✅ [已買並加入庫存]", key=f"b_{sid}"):
                        con = get_db()
                        cur = con.cursor()
                        cur.execute("""INSERT INTO foods (fridge_id, name, category, quantity, unit, location, purchase_date, expiry_date, note)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (current_fridge_id, sname, "其他", sqty, sunit, sloc or "冷藏", date.today().isoformat(), sexp or date.today().isoformat(), "採買入庫"))
                        fid = cur.lastrowid
                        cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                    (fid, "入庫", sqty, date.today().isoformat(), "採買清單轉入"))
                        cur.execute("UPDATE shopping_list SET status=1 WHERE id=?", (sid,))
                        con.commit()
                        con.close()
                        st.rerun()
                with col2:
                    if st.button("🗑️ 刪除", key=f"d_{sid}"):
                        con = get_db()
                        con.execute("DELETE FROM shopping_list WHERE id=?", (sid,))
                        con.commit()
                        con.close()
                        st.rerun()

# --- 標籤四：食譜 ---
with tab4:
    st.subheader("🍳 食譜清單與冰箱食材比對")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT name, quantity FROM foods WHERE fridge_id = ? AND quantity > 0", (current_fridge_id,))
    fridge_foods = {row[0].strip(): row[1] for row in cur.fetchall()}
    cur.execute("SELECT id, name, category, ingredients, instructions FROM recipes ORDER BY id DESC")
    recipes = cur.fetchall()
    con.close()

    if recipes:
        for rid, rname, rcat, ringredients, rinstructions in recipes:
            missing_items = []
            has_all = True
            for item in ringredients.split(","):
                if ":" in item:
                    iname = item.split(":")[0].strip()
                    found_match = any(iname == fname or (len(iname) >= 2 and iname in fname) for fname in fridge_foods.keys())
                    if not found_match:
                        has_all = False
                        missing_items.append(iname)
            badge = "🟢 材料齊全可烹調" if has_all else f"🟠 缺少材料 ({len(missing_items)}樣)"
            with st.expander(f"{badge} | {rname} ({rcat or '未分類'})"):
                st.markdown(f"**所需食材**：`{ringredients}`")
                st.markdown(f"**烹調步驟**：\n{rinstructions or '無步驟說明'}")
                if not has_all and st.button("🛒 將缺少的食材加入採買", key=f"m_{rid}"):
                    con = get_db()
                    for m_item in missing_items:
                        con.execute("INSERT INTO shopping_list(fridge_id, name, quantity, unit, location, expiry_date) VALUES(?,?,?,?,?,?)",
                                    (current_fridge_id, m_item, 1, "個", "冷藏", (date.today() + timedelta(days=7)).isoformat()))
                    con.commit()
                    con.close()
                    st.success("已加入採買清單！")
                    st.rerun()

# --- 標籤五：紀錄 ---
with tab5:
    st.subheader(f"📜 異動紀錄 ({selected_fridge_name})")
    con = get_db()
    cur = con.cursor()
    cur.execute("""SELECT t.id, COALESCE(f.name, '(已刪除)'), t.action, t.quantity, t.trans_date, t.note
                   FROM transactions t JOIN foods f ON t.food_id = f.id WHERE f.fridge_id = ? ORDER BY t.id DESC""", (current_fridge_id,))
    trans_rows = cur.fetchall()
    con.close()
    if trans_rows:
        for tid, fname, action, tqty, tdate, tnote in trans_rows:
            st.markdown(f"**[{tdate}] {fname}** - `{action}` ({tqty:g}) | {tnote}")

# --- 標籤六：報表 ---
with tab6:
    st.subheader(f"📊 冰箱狀態總覽 ({selected_fridge_name})")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM foods WHERE fridge_id = ? AND quantity > 0", (current_fridge_id,))
    count, total = cur.fetchone()
    cur.execute("SELECT name, quantity, unit, expiry_date FROM foods WHERE fridge_id = ? AND quantity > 0 AND expiry_date<>'' AND expiry_date IS NOT NULL ORDER BY expiry_date", (current_fridge_id,))
    all_foods = cur.fetchall()
    con.close()
    st.metric("總食材品項數", f"{count} 項")
    st.metric("總庫存數量", f"{total:g} 單位")
