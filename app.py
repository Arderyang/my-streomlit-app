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
    
    # 若沒有預設冰箱，建立一個「主冰箱」
    cur.execute("SELECT COUNT(*) FROM fridges")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO fridges (name) VALUES ('主冰箱')")
        
    con.commit()
    con.close()

init_db()

# --- 2. 介面全域常數 ---
CATEGORIES = ["肉類", "蔬菜", "水果", "乳製品", "蛋類", "海鮮", "飲料", "調味料", "冷凍食品", "其他"]
LOCATIONS = ["冷藏", "冷凍", "常溫"]

st.set_page_config(page_title="智慧冰箱管理系統", page_icon="🧊", layout="centered")

st.title("🧊 智慧冰箱管理系統")

# 選擇冰箱
con = get_db()
cur = con.cursor()
cur.execute("SELECT id, name FROM fridges")
fridges = cur.fetchall()
con.close()

fridge_dict = {f["name"]: f["id"] for f in fridges}
selected_fridge_name = st.sidebar.selectbox("選擇目前冰箱", list(fridge_dict.keys()))
current_fridge_id = fridge_dict[selected_fridge_name]

# --- 3. 標籤頁導覽 ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📦 庫存", "📸 拍照AI", "🍳 食譜", "🛒 採買", "📋 取出紀錄", "📊 報表"])

# --- 標籤一：庫存管理 ---
with tab1:
    st.subheader(f"📦 食材庫存管理 ({selected_fridge_name})")
    
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM foods WHERE fridge_id = ? AND quantity > 0", (current_fridge_id,))
    foods = cur.fetchall()
    con.close()
    
    if foods:
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
        st.info("目前冰箱內沒有食材，快使用「拍照AI」或手動新增吧！")

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
                            model="gemini-3.8-flash", 
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
        st.markdown("##### 現有食譜")
        cur.execute("SELECT id, title, ingredients, instructions, category FROM recipes")
        recipes = cur.fetchall()
        
        if recipes:
            for r_id, title, ingredients, instructions, category in recipes:
                with st.expander(f"📖 {title}（分類：{category or '一般'}）"):
                    st.markdown(f"**所需食材：**\n{ingredients}")
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
            new_ing = st.text_area("所需食材（例如：雞蛋 2顆、番茄 1顆）")
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
    
    # 總計數據
    cur.execute("SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM foods WHERE fridge_id = ? AND quantity > 0", (current_fridge_id,))
    count, total = cur.fetchone()
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("總食材品項數", f"{count} 項")
    with col_m2:
        st.metric("總庫存數量", f"{total:g} 單位")
        
    st.divider()
    
    # 1. 依類別統計
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
    
    # 2. 依位置統計
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
