from datetime import date, timedelta
import json
import sqlite3
import time
from google import genai
import streamlit as st

# --- 1. 資料庫初始化設定 ---
def get_db():
    con = sqlite3.connect("fridge.db")
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = get_db()
    cur = con.cursor()
    
    # 冰箱主表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fridges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    
    # 食材主表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fridge_id INTEGER,
            name TEXT NOT NULL,
            category TEXT,
            quantity REAL,
            unit TEXT,
            location TEXT,
            purchase_date TEXT,
            expiry_date TEXT,
            note TEXT
        )
    """)
    
    # 異動紀錄表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_id INTEGER,
            action TEXT,
            quantity REAL,
            trans_date TEXT,
            note TEXT
        )
    """)
    
    # 食譜表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            ingredients TEXT,
            instructions TEXT,
            category TEXT
        )
    """)
    
    # 使用者權限表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)
    
    # 若沒有預設冰箱，建立一個「主冰箱」
    cur.execute("SELECT COUNT(*) FROM fridges")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO fridges (name) VALUES ('主冰箱')")
        
    # 若沒有管理員帳號，預設建立一個 admin (密碼: admin123)
    cur.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
        
    con.commit()
    con.close()

init_db()

# --- 2. 介面全域常數與登入控制 ---
CATEGORIES = ["肉類", "蔬菜", "水果", "乳製品", "蛋類", "海鮮", "飲料", "調味料", "冷凍食品", "其他"]
LOCATIONS = ["冷藏", "冷凍", "常溫"]

st.set_page_config(page_title="智慧冰箱管理系統", page_icon="🧊", layout="centered")

st.title("🧊 智慧冰箱管理系統")

# Session State 初始化登入狀態
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = "user"

# 側邊欄：登入與權限狀態
st.sidebar.subheader("🔐 系統登入與權限")
if not st.session_state.logged_in:
    login_user = st.sidebar.text_input("帳號", key="login_user")
    login_pass = st.sidebar.text_input("密碼", type="password", key="login_pass")
    if st.sidebar.button("登入", type="primary"):
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE username = ? AND password = ?", (login_user.strip(), login_pass.strip()))
        user_row = cur.fetchone()
        con.close()
        
        if user_row:
            st.session_state.logged_in = True
            st.session_state.username = user_row["username"]
            st.session_state.role = user_row["role"]
            st.success("登入成功！")
            st.rerun()
        else:
            st.sidebar.error("帳號或密碼錯誤！")
    
    st.info("提示：預設管理員帳號為 `admin`，密碼為 `admin123`")
    st.stop() # 未登入前不顯示後續主要應用
else:
    st.sidebar.write(f"👤 當前使用者：**{st.session_state.username}**")
    st.sidebar.write(f"🛡️ 身份權限：**{'管理員 (Admin)' if st.session_state.role == 'admin' else '一般使用者 (User)'}**")
    
    # 側邊欄：修改自己的密碼
    with st.sidebar.expander("🔑 修改我的密碼"):
        with st.form("change_password_form"):
            old_p = st.text_input("舊密碼", type="password")
            new_p = st.text_input("新密碼", type="password")
            confirm_p = st.text_input("確認新密碼", type="password")
            change_btn = st.form_submit_button("確認修改")
            
            if change_btn:
                if not old_p or not new_p or not confirm_p:
                    st.warning("請填寫所有欄位！")
                elif new_p != confirm_p:
                    st.error("新密碼與確認密碼不相符！")
                else:
                    con = get_db()
                    cur = con.cursor()
                    cur.execute("SELECT * FROM users WHERE username = ? AND password = ?", (st.session_state.username, old_p))
                    matched = cur.fetchone()
                    if matched:
                        cur.execute("UPDATE users SET password = ? WHERE username = ?", (new_p, st.session_state.username))
                        con.commit()
                        con.close()
                        st.success("密碼修改成功！請重新登入。")
                        time.sleep(1)
                        st.session_state.logged_in = False
                        st.rerun()
                    else:
                        con.close()
                        st.error("舊密碼錯誤！")

    if st.sidebar.button("登出系統"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = "user"
        st.rerun()

# 選擇冰箱
con = get_db()
cur = con.cursor()
cur.execute("SELECT id, name FROM fridges")
fridges = cur.fetchall()
con.close()

fridge_dict = {f["name"]: f["id"] for f in fridges}
selected_fridge_name = st.sidebar.selectbox("選擇目前冰箱", list(fridge_dict.keys()))
current_fridge_id = fridge_dict[selected_fridge_name]

# --- 3. 標籤頁導覽（依權限動態調整） ---
if st.session_state.role == "admin":
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📦 庫存", "📸 拍照AI", "🍳 食譜", "🛒 採買", "📋 取出紀錄", "📊 報表", "⚙️ 系統管理"])
else:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📦 庫存", "📸 拍照AI", "🍳 食譜", "🛒 採買", "📋 取出紀錄", "📊 報表"])

# --- 標籤一：庫存管理（含手動新增與清單） ---
with tab1:
    st.subheader(f"📦 食材庫存管理 ({selected_fridge_name})")
    
    with st.expander("➕ 手動新增食材"):
        with st.form("manual_add_food_form"):
            m_name = st.text_input("食材名稱")
            m_cat = st.selectbox("分類", CATEGORIES, key="m_cat")
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                m_qty = st.number_input("數量", min_value=0.1, value=1.0, step=1.0, key="m_qty")
            with col_q2:
                m_unit = st.text_input("單位（如：個、克、瓶）", value="個", key="m_unit")
            m_loc = st.selectbox("存放位置", LOCATIONS, key="m_loc")
            m_expiry = st.date_input("有效期限", value=date.today() + timedelta(days=14), key="m_expiry")
            m_note = st.text_input("備註說明", key="m_note")
            
            m_submitted = st.form_submit_button("確認新增入庫", type="primary")
            if m_submitted:
                if not m_name.strip():
                    st.warning("請輸入食材名稱！")
                else:
                    con = get_db()
                    cur = con.cursor()
                    cur.execute("""INSERT INTO foods 
                        (fridge_id, name, category, quantity, unit, location, purchase_date, expiry_date, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (current_fridge_id, m_name.strip(), m_cat, m_qty, m_unit, m_loc, date.today().isoformat(), m_expiry.isoformat(), m_note.strip() or "手動新增"))
                    fid = cur.lastrowid
                    cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                (fid, "入庫", m_qty, date.today().isoformat(), "手動新增入庫"))
                    con.commit()
                    con.close()
                    st.success(f"✅ 成功手動新增 {m_qty:g} {m_unit} 的 {m_name.strip()}！")
                    st.rerun()

    st.divider()
    
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM foods WHERE fridge_id = ? AND quantity > 0", (current_fridge_id,))
    foods = cur.fetchall()
    con.close()
    
    if foods:
        st.markdown("##### 現有庫存清單")
        for f in foods:
            expiry_date = date.fromisoformat(f["expiry_date"])
            days_left = (expiry_date - date.today()).days
            
            status_emoji = "🟢"
            if days_left < 0:
                status_emoji = "🔴"
            elif days_left <= 3:
                status_emoji = "🟡"
                
            with st.expander(f"{status_emoji} {f['name']} ({f['quantity']:g} {f['unit']}) - 到期日: {f['expiry_date']}"):
                st.write(f"**分類：** {f['category']} | **位置：** {f['location']}")
                st.write(f"**備註：** {f['note'] or '無'}")
                
                col1, col2 = st.columns(2)
                with col1:
                    use_qty = st.number_input("消耗數量", min_value=0.1, max_value=float(f["quantity"]), value=1.0, step=1.0, key=f"use_{f['id']}")
                    if st.button("消耗/取出", key=f"btn_use_{f['id']}"):
                        con = get_db()
                        cur = con.cursor()
                        new_q = f["quantity"] - use_qty
                        cur.execute("UPDATE foods SET quantity = ? WHERE id = ?", (new_q, f["id"]))
                        cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                    (f["id"], "取出", use_qty, date.today().isoformat(), "手動消耗"))
                        con.commit()
                        con.close()
                        st.success(f"已從庫存扣除 {use_qty:g} {f['unit']} 的 {f['name']}！")
                        st.rerun()
                with col2:
                    if st.button("🗑️ 刪除此項", key=f"del_{f['id']}"):
                        con = get_db()
                        cur = con.cursor()
                        cur.execute("UPDATE foods SET quantity = 0 WHERE id = ?", (f["id"],))
                        cur.execute("INSERT INTO transactions(food_id, action, quantity, trans_date, note) VALUES(?,?,?,?,?)",
                                    (f["id"], "刪除", f["quantity"], date.today().isoformat(), "手動刪除"))
                        con.commit()
                        con.close()
                        st.success("已刪除該食材！")
                        st.rerun()
    else:
        st.info("目前冰箱內沒有食材，您可以透過上方「➕ 手動新增食材」或切換至「📸 拍照AI」加入！")

# --- 標籤二：手機拍照與 Google Gemini AI 辨識入庫 ---
with tab2:
    st.subheader(f"📸 Google AI 智慧拍照辨識入庫 ({selected_fridge_name})")
    
    if "ai_result_name" not in st.session_state:
        st.session_state.ai_result_name = ""
    if "ai_result_cat" not in st.session_state:
        st.session_state.ai_result_cat = "其他"
    if "ai_result_qty" not in st.session_state:
        st.session_state.ai_result_qty = 1.0
    if "ai_result_unit" not in st.session_state:
        st.session_state.ai_result_unit = "個"

    camera_image = st.camera_input("拍攝冰箱內部或單一食材")
    
    if camera_image is not None:
        from PIL import Image
        image = Image.open(camera_image)
        st.image(image, caption="已拍攝的照片", use_container_width=True)
        
        if st.button("🤖 開始讓 Gemini 分析食材"):
            with st.spinner("AI 正在分析影像中的食材與數量，若遇伺服器忙碌將自動重試..."):
                active_key = st.secrets.get("GEMINI_API_KEY", None)
                client = genai.Client(api_key=active_key)
                
                prompt = (
                    "請仔細分析這張照片中的主要食材及其數量。請嚴格依照下列格式回答，不要有其他廢話：\n"
                    "名稱: [食材名稱]\n"
                    "分類: [肉類/蔬菜/水果/乳製品/蛋類/海鮮/飲料/調味料/冷凍食品/其他]\n"
                    "數量: [數字]\n"
                    "單位: [單位]"
                )
                
                success = False
                ai_text = ""
                for attempt in range(3):
                    try:
                        response = client.models.generate_content(
                            model="gemini-2.5-flash", 
                            contents=[image, prompt]
                        )
                        ai_text = response.text.strip()
                        success = True
                        break
                    except Exception as e:
                        if "503" in str(e) and attempt < 2:
                            time.sleep(2)
                            continue
                        else:
                            st.error(f"AI 辨識發生錯誤：{e}")
                            break
                
                if success and ai_text:
                    parsed_any = False
                    for line in ai_text.split("\n"):
                        if "名稱" in line:
                            val = line.split(":")[-1].split("：")[-1].strip().replace("]", "").replace("[", "")
                            if val:
                                st.session_state.ai_result_name = val
                                parsed_any = True
                        elif "分類" in line:
                            cat_val = line.split(":")[-1].split("：")[-1].strip().replace("]", "").replace("[", "")
                            if cat_val in CATEGORIES:
                                st.session_state.ai_result_cat = cat_val
                        elif "數量" in line:
                            try:
                                q_str = line.split(":")[-1].split("：")[-1].strip()
                                import re
                                numbers = re.findall(r"\d+\.?\d*", q_str)
                                if numbers:
                                    st.session_state.ai_result_qty = float(numbers[0])
                            except Exception:
                                pass
                        elif "單位" in line:
                            u_val = line.split(":")[-1].split("：")[-1].strip().replace("]", "").replace("[", "")
                            if u_val:
                                st.session_state.ai_result_unit = u_val
                    
                    if parsed_any:
                        st.success("🎉 AI 分析成功！")
                        st.rerun()
                    else:
                        st.warning(f"AI 回傳內容無法正確解析，原始回應為：\n{ai_text}")

    st.markdown("##### 📝 確認辨識與入庫資訊")
    f_name = st.text_input("食材名稱", value=st.session_state.ai_result_name)
    default_cat_idx = CATEGORIES.index(st.session_state.ai_result_cat) if st.session_state.ai_result_cat in CATEGORIES else 9
    f_cat = st.selectbox("分類", CATEGORIES, index=default_cat_idx)
    f_qty = st.number_input("數量", min_value=0.1, value=float(st.session_state.ai_result_qty), step=1.0)
    f_unit = st.text_input("單位", value=st.session_state.ai_result_unit)
    f_loc = st.selectbox("存放位置", LOCATIONS)
    f_expiry = st.date_input("有效期限", value=date.today() + timedelta(days=14))
    
    if st.button("確認入庫", type="primary", key="btn_ai_submit"):
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

# --- 標籤三：食譜管理與匯入 ---
with tab3:
    st.subheader("🍳 食譜管理與智慧推薦")
    
    con = get_db()
    cur = con.cursor()
    recipe_mode = st.radio("選擇操作模式", ["📜 檢視食譜清單", "✍️ 手動新增食譜", "📥 匯入 JSON 食譜檔案"], horizontal=True)
    
    if recipe_mode == "📜 檢視食譜清單":
        st.markdown(f"##### 現有食譜庫存狀態檢查 ({selected_fridge_name})")
        
        # 取得當前冰箱的所有庫存食材與數量
        cur.execute("SELECT name, quantity FROM foods WHERE fridge_id = ? AND quantity > 0", (current_fridge_id,))
        fridge_foods = {row["name"].strip(): row["quantity"] for row in cur.fetchall()}
        
        cur.execute("SELECT id, title, ingredients, instructions, category FROM recipes")
        recipes = cur.fetchall()
        
        if recipes:
            for r_id, title, ingredients, instructions, category in recipes:
                # 解析食譜所需食材（支援以逗號、頓號或換行分隔）
                import re
                raw_ings = re.split(r'[,，、\n]+', ingredients)
                needed_items = [i.strip() for i in raw_ings if i.strip()]
                
                matched_count = 0
                missing_items = []
                
                for ing in needed_items:
                    # 簡易比對：只要庫存品項名稱包含食譜食材關鍵字，或完全符合
                    found = False
                    for f_name, f_qty in fridge_foods.items():
                        if f_name in ing or ing in f_name:
                            found = True
                            break
                    if found:
                        matched_count += 1
                    else:
                        missing_items.append(ing)
                
                # 計算燈號邏輯
                if not needed_items:
                    status_light = "🟢"
                elif matched_count == len(needed_items):
                    status_light = "🟢"  # 全部符合：亮綠燈
                elif matched_count == 0:
                    status_light = "🔴"  # 全部沒有：亮紅燈
                else:
                    status_light = "🟠"  # 少部分有：亮橘燈
                
                with st.expander(f"{status_light} {title}（分類：{category or '一般'}）"):
                    st.markdown(f"**所需食材：**\n{ingredients}")
                    if missing_items:
                        st.warning(f"⚠️ 缺少的食材：{', '.join(missing_items)}")
                    else:
                        st.success("🎉 目前冰箱庫存皆已備齊！")
                    st.markdown(f"**作法步驟：**\n{instructions}")
                    
                    if st.button("🗑️ 刪除此食譜", key=f"del_recipe_{r_id}"):
                        cur.execute("DELETE FROM recipes WHERE id = ?", (r_id,))
                        con.commit()
                        st.success("已成功刪除食譜！")
                        st.rerun()
        else:
            st.info("目前尚無食譜，請切換至「手動新增食譜」或「匯入 JSON 食譜檔案」加入！")
            
    elif recipe_mode == "✍️ 手動新增食譜":
        st.markdown("##### 📝 填寫新食譜資訊")
        with st.form("add_recipe_form"):
            new_title = st.text_input("食譜名稱")
            new_cat = st.selectbox("料理分類", ["家常菜", "湯品", "點心", "主食", "異國料理", "其他"])
            new_ing = st.text_area("所需食材（例如：雞蛋、番茄、洋蔥）")
            new_inst = st.text_area("作法步驟說明")
            
            submitted = st.form_submit_button("儲存食譜", type="primary")
            if submitted:
                if not new_title.strip():
                    st.warning("請輸入食譜名稱！")
                else:
                    cur.execute("INSERT INTO recipes (title, ingredients, instructions, category) VALUES (?, ?, ?, ?)",
                                (new_title.strip(), new_ing, new_inst, new_cat))
                    con.commit()
                    st.success(f"✅ 成功新增食譜：{new_title.strip()}！")
                    st.rerun()
                    
    elif recipe_mode == "📥 匯入 JSON 食譜檔案":
        st.markdown("""
        ##### 📁 上傳 JSON 格式食譜檔案
        檔案格式範例：
        ```json
        [
          {"title": "番茄炒蛋", "ingredients": "番茄、雞蛋", "instructions": "先炒蛋再炒番茄", "category": "家常菜"},
          {"title": "紫菜蛋花湯", "ingredients": "紫菜、雞蛋", "instructions": "水滾加入紫菜與蛋液", "category": "湯品"}
        ]
        ```
        """)
        
        uploaded_file = st.file_uploader("選擇 JSON 檔案", type=["json"])
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                if isinstance(data, list):
                    count_imported = 0
                    for item in data:
                        title = item.get("title")
                        ingredients = item.get("ingredients", "")
                        instructions = item.get("instructions", "")
                        category = item.get("category", "其他")
                        if title:
                            cur.execute("INSERT INTO recipes (title, ingredients, instructions, category) VALUES (?, ?, ?, ?)",
                                        (title, ingredients, instructions, category))
                            count_imported += 1
                    con.commit()
                    st.success(f"🎉 成功批次匯入 {count_imported} 筆食譜！")
                    st.rerun()
                else:
                    st.error("JSON 格式不正確，最外層必須是陣列格式（List）。")
            except Exception as e:
                st.error(f"解析檔案時發生錯誤：{e}")
                
    con.close()

# --- 標籤四：採買清單 ---
with tab4:
    st.subheader("🛒 採買清單")
    st.info("這裡可以記錄您需要購買的食材清單。")
    
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shopping_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            checked INTEGER DEFAULT 0
        )
    """)
    con.commit()
    
    new_shop = st.text_input("新增欲採買食材")
    if st.button("加入採買清單"):
        if new_shop.strip():
            cur.execute("INSERT INTO shopping_list (name) VALUES (?)", (new_shop.strip(),))
            con.commit()
            st.success(f"已加入：{new_shop.strip()}")
            st.rerun()
            
    cur.execute("SELECT id, name, checked FROM shopping_list")
    shop_items = cur.fetchall()
    
    if shop_items:
        for s_id, s_name, checked in shop_items:
            is_checked = st.checkbox(s_name, value=bool(checked), key=f"shop_{s_id}")
            if is_checked != bool(checked):
                cur.execute("UPDATE shopping_list SET checked = ? WHERE id = ?", (int(is_checked), s_id))
                con.commit()
        
        if st.button("清除已勾選項目"):
            cur.execute("DELETE FROM shopping_list WHERE checked = 1")
            con.commit()
            st.success("已清除勾選項目！")
            st.rerun()
    con.close()

# --- 標籤五：取出紀錄 ---
with tab5:
    st.subheader("📋 冰箱食材異動紀錄")
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT t.trans_date, f.name, t.action, t.quantity, f.unit, t.note
        FROM transactions t
        JOIN foods f ON t.food_id = f.id
        WHERE f.fridge_id = ?
        ORDER BY t.id DESC LIMIT 50
    """, (current_fridge_id,))
    logs = cur.fetchall()
    con.close()
    
    if logs:
        for l_date, name, action, qty, unit, note in logs:
            st.markdown(f"- **{l_date}** | 執行 **{action}** 了 `{qty:g} {unit}` 的 **{name}** （備註：{note}）")
    else:
        st.info("目前尚無異動紀錄。")

# --- 標籤六：報表與統計 ---
with tab6:
    st.subheader(f"📊 冰箱狀態總覽 ({selected_fridge_name})")
    
    con = get_db()
    cur = con.cursor()
    
    cur.execute("SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM foods WHERE fridge_id = ? AND quantity > 0", (current_fridge_id,))
    count, total = cur.fetchone()
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("總食材品項數", f"{count} 項")
    with col_m2:
        st.metric("總庫存數量", f"{total:g} 單位")
        
    st.divider()
    
    st.markdown("##### 🏷️ 依類別統計數量")
    cur.execute("""
        SELECT category, SUM(quantity), COUNT(*) 
        FROM foods 
        WHERE fridge_id = ? AND quantity > 0 
        GROUP BY category 
        ORDER BY SUM(quantity) DESC
    """, (current_fridge_id,))
    cat_rows = cur.fetchall()
    
    if cat_rows:
        for cat, q_sum, c_cnt in cat_rows:
            cat_name = cat or '未分類'
            st.markdown(f"- **{cat_name}**: 共 **{q_sum:g}** 單位（共 {c_cnt} 項品項）")
    else:
        st.info("目前尚無類別統計資料。")
        
    st.divider()
    
    st.markdown("##### 📍 依存放位置統計數量")
    cur.execute("""
        SELECT location, SUM(quantity), COUNT(*) 
        FROM foods 
        WHERE fridge_id = ? AND quantity > 0 
        GROUP BY location 
        ORDER BY SUM(quantity) DESC
    """, (current_fridge_id,))
    loc_rows = cur.fetchall()
    
    if loc_rows:
        for loc, q_sum, c_cnt in loc_rows:
            loc_name = loc or '未指定'
            st.markdown(f"- **{loc_name}**: 共 **{q_sum:g}** 單位（共 {c_cnt} 項品項）")
    else:
        st.info("目前尚無位置統計資料。")
        
    con.close()

# --- 標籤七：管理員專屬 - 系統管理（用戶與冰箱） ---
if st.session_state.role == "admin":
    with tab7:
        st.subheader("⚙️ 系統管理面板")
        
        admin_sub_tab1, admin_sub_tab2 = st.tabs(["🧊 冰箱管理", "👥 用戶權限管理"])
        
        with admin_sub_tab1:
            st.markdown("##### ➕ 新增冰箱")
            with st.form("add_fridge_form"):
                new_f_name = st.text_input("新冰箱名稱（例如：辦公室冰箱）")
                f_submitted = st.form_submit_button("建立冰箱", type="primary")
                if f_submitted:
                    if not new_f_name.strip():
                        st.warning("冰箱名稱不得為空！")
                    else:
                        con = get_db()
                        cur = con.cursor()
                        cur.execute("INSERT INTO fridges (name) VALUES (?)", (new_f_name.strip(),))
                        con.commit()
                        con.close()
                        st.success(f"✅ 成功建立冰箱：{new_f_name.strip()}！")
                        st.rerun()

            st.divider()
            st.markdown("##### 📋 現有冰箱列表與刪除")
            con = get_db()
            cur = con.cursor()
            cur.execute("SELECT id, name FROM fridges")
            all_fridges = cur.fetchall()
            con.close()
            
            if all_fridges:
                for f_row in all_fridges:
                    f_id = f_row["id"]
                    f_name = f_row["name"]
                    col_f1, col_f2 = st.columns([3, 1])
                    with col_f1:
                        st.write(f"**冰箱名稱：** {f_name} (ID: {f_id})")
                    with col_f2:
                        # 至少保留一個冰箱，避免系統完全沒有冰箱
                        if len(all_fridges) > 1:
                            if st.button("🗑️ 刪除", key=f"del_fridge_{f_id}"):
                                con = get_db()
                                cur = con.cursor()
                                # 同時清除該冰箱底下的所有食材
                                cur.execute("DELETE FROM foods WHERE fridge_id = ?", (f_id,))
                                cur.execute("DELETE FROM fridges WHERE id = ?", (f_id,))
                                con.commit()
                                con.close()
                                st.success(f"已刪除冰箱：{f_name}")
                                st.rerun()
                        else:
                            st.write("保留最後一個")
            else:
                st.info("目前無任何冰箱。")

        with admin_sub_tab2:
            st.markdown("##### ➕ 新增系統用戶")
            with st.form("add_user_form"):
                new_u_name = st.text_input("新帳號名稱")
                new_u_pass = st.text_input("密碼", type="password")
                new_u_role = st.selectbox("指派權限", ["user", "admin"])
                u_submitted = st.form_submit_button("建立用戶", type="primary")
                
                if u_submitted:
                    if not new_u_name.strip() or not new_u_pass.strip():
                        st.warning("帳號與密碼不得為空！")
                    else:
                        try:
                            con = get_db()
                            cur = con.cursor()
                            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                                        (new_u_name.strip(), new_u_pass.strip(), new_u_role))
                            con.commit()
                            con.close()
                            st.success(f"✅ 成功建立用戶：{new_u_name.strip()}（權限：{new_u_role}）")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("此帳號名稱已存在，請使用其他名稱。")

            st.divider()
            st.markdown("##### 📋 現有用戶清單與刪除管理")
            con = get_db()
            cur = con.cursor()
            cur.execute("SELECT id, username, role FROM users")
            all_users = cur.fetchall()
            con.close()
            
            if all_users:
                for u_id, u_name, u_role in all_users:
                    col_u1, col_u2, col_u3 = st.columns([2, 2, 1])
                    with col_u1:
                        st.write(f"**帳號：** {u_name}")
                    with col_u2:
                        st.write(f"**權限：** {u_role}")
                    with col_u3:
                        # 不允許刪除自己或預設的 admin 帳號（避免系統失控）
                        if u_name != "admin" and u_name != st.session_state.username:
                            if st.button("🗑️ 刪除", key=f"del_user_{u_id}"):
                                con = get_db()
                                cur = con.cursor()
                                cur.execute("DELETE FROM users WHERE id = ?", (u_id,))
                                con.commit()
                                con.close()
                                st.success(f"已刪除用戶 {u_name}")
                                st.rerun()
                        else:
                            st.write("保護帳號")
            else:
                st.info("目前無其他用戶。")
