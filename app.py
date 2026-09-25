from google import genai
from PIL import Image
import json

# --- 標籤二：手機拍照與 AI 辨識入庫 ---
with tab2:
    st.subheader("📸 拍照 AI 辨識食材")
    st.write("使用手機相機拍攝食材或冰箱內部，AI 將自動辨識品項與分類。")
    
    camera_image = st.camera_input("拍攝照片")
    
    if camera_image is not None:
        st.info("照片已上傳！正在透過 Gemini AI 分析食材...")
        
        try:
            # 初始化 Gemini 客戶端
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            image = Image.open(camera_image)
            
            # 呼叫 Gemini 2.5 Flash 模型進行影像辨識
            prompt = (
                "請辨識這張圖片中的主要食材是什麼。請以 JSON 格式回傳，"
                "包含兩個欄位："
                "1. \"name\" (食材名稱，例如：高麗菜、雞蛋、蘋果)"
                "2. \"category\" (必須從以下類別選擇一個：肉類、蔬菜、水果、乳製品、蛋類、海鮮、飲料、調味料、冷凍食品、其他)"
                "請注意：只需要回傳 JSON 格式文字，不要有其他多餘文字。"
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[image, prompt]
            )
            
            # 解析 AI 回傳的 JSON 結果
            result_text = response.text.strip()
            # 移除可能包住的 markdown 標記
            if result_text.startswith("```json"):
                result_text = result_text[7:-3].strip()
            elif result_text.startswith("```"):
                result_text = result_text[3:-3].strip()
                
            ai_data = json.loads(result_text)
            ai_detected_name = ai_data.get("name", "未知食材")
            ai_detected_category = ai_data.get("category", "其他")
            
            st.success(f"🎉 AI 辨識成功！辨識結果：**{ai_detected_name}**（分類：{ai_detected_category}）")
            
        except Exception as e:
            st.warning(f"AI 自動辨識發生小狀況（{e}），請您直接手動輸入欄位：")
            ai_detected_name = "未命名食材"
            ai_detected_category = "其他"

        # 確認入庫表單
        with st.form("ai_add_form"):
            f_name = st.text_input("食材名稱", value=ai_detected_name)
            f_cat = st.selectbox("分類", CATEGORIES, index=CATEGORIES.index(ai_detected_category) if ai_detected_category in CATEGORIES else 9)
            f_qty = st.number_input("數量", min_value=0.1, value=1.0, step=1.0)
            f_unit = st.text_input("單位", value="個")
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
